"""
Business Logic Handler
Encapsulates all data processing and business logic as a bridge between model and UI
"""
import os
import math
from copy import deepcopy
import tempfile
import traceback
import re
import random
from contextlib import contextmanager
from typing import Optional, Dict, Any, Tuple, List, Union

import torch
import torchaudio
import soundfile as sf
import time
from tqdm import tqdm
from loguru import logger
import warnings

from transformers import AutoTokenizer, AutoModel, AutoModelForCausalLM
from transformers.generation.streamers import BaseStreamer
from diffusers.models import AutoencoderOobleck


warnings.filterwarnings("ignore")


SFT_GEN_PROMPT = """# Instruction
{}

# Caption
{}

# Metas
{}<|endoftext|>
"""

class AceStepHandler:
    """ACE-Step Business Logic Handler"""
    
    def __init__(self):
        self.model = None
        self.config = None
        self.device = "cpu"
        self.dtype = torch.float32  # Will be set based on device in initialize_service
        self.temp_dir = tempfile.mkdtemp()
        
        # VAE for audio encoding/decoding
        self.vae = None
        
        # Text encoder and tokenizer
        self.text_encoder = None
        self.text_tokenizer = None
        
        # Silence latent for initialization
        self.silence_latent = None
        
        # Sample rate
        self.sample_rate = 48000
        
        # Reward model (temporarily disabled)
        self.reward_model = None
        
        # Batch size
        self.batch_size = 2
        
        # Custom layers config
        self.custom_layers_config = {
            2: [6, 7],
            3: [10, 11],
            4: [3],
            5: [8, 9, 11],
            6: [8]
        }
        self.offload_to_cpu = False
        self.offload_dit_to_cpu = False
        self.current_offload_cost = 0.0
    
    def get_available_checkpoints(self) -> str:
        """Return project root directory path"""
        # Get project root (handler.py is in acestep/, so go up two levels to project root)
        current_file = os.path.abspath(__file__)
        project_root = os.path.dirname(os.path.dirname(current_file))
        # default checkpoints
        checkpoint_dir = os.path.join(project_root, "checkpoints")
        if os.path.exists(checkpoint_dir):
            return [checkpoint_dir]
        else:
            return []
    
    def get_available_acestep_v15_models(self) -> List[str]:
        """Scan and return all model directory names starting with 'acestep-v15-'"""
        # Get project root
        current_file = os.path.abspath(__file__)
        project_root = os.path.dirname(os.path.dirname(current_file))
        checkpoint_dir = os.path.join(project_root, "checkpoints")
        
        models = []
        if os.path.exists(checkpoint_dir):
            # Scan all directories starting with 'acestep-v15-' in checkpoints folder
            for item in os.listdir(checkpoint_dir):
                item_path = os.path.join(checkpoint_dir, item)
                if os.path.isdir(item_path) and item.startswith("acestep-v15-"):
                    models.append(item)
        
        # Sort by name
        models.sort()
        return models
    
    def is_flash_attention_available(self) -> bool:
        """Check if flash attention is available on the system"""
        try:
            import flash_attn
            return True
        except ImportError:
            return False
    
    def initialize_service(
        self, 
        project_root: str,
        config_path: str,
        device: str = "auto",
        use_flash_attention: bool = False,
        compile_model: bool = False,
        offload_to_cpu: bool = False,
        offload_dit_to_cpu: bool = False,
        quantization: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """
        Initialize DiT model service
        
        Args:
            project_root: Project root path (may be checkpoints directory, will be handled automatically)
            config_path: Model config directory name (e.g., "acestep-v15-turbo")
            device: Device type
            use_flash_attention: Whether to use flash attention (requires flash_attn package)
            compile_model: Whether to use torch.compile to optimize the model
            offload_to_cpu: Whether to offload models to CPU when not in use
            offload_dit_to_cpu: Whether to offload DiT model to CPU when not in use (only effective if offload_to_cpu is True)
        
        Returns:
            (status_message, enable_generate_button)
        """
        try:
            if device == "auto":
                if hasattr(torch, 'xpu') and torch.xpu.is_available():
                    device = "xpu"
                elif torch.cuda.is_available():
                    device = "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    device = "mps"
                else:
                    device = "cpu"

            status_msg = ""
            
            self.device = device
            self.offload_to_cpu = offload_to_cpu
            self.offload_dit_to_cpu = offload_dit_to_cpu
            # Set dtype based on device: bfloat16 for cuda, float32 for cpu
            self.dtype = torch.bfloat16 if device in ["cuda","xpu"] else torch.float32
            self.quantization = quantization
            if self.quantization is not None:
                assert compile_model, "Quantization requires compile_model to be True"
                try:
                    import torchao
                except ImportError:
                    raise ImportError("torchao is required for quantization but is not installed. Please install torchao to use quantization features.")
                

            # Auto-detect project root (independent of passed project_root parameter)
            current_file = os.path.abspath(__file__)
            actual_project_root = os.path.dirname(os.path.dirname(current_file))
            checkpoint_dir = os.path.join(actual_project_root, "checkpoints")

            # 1. Load main model
            # config_path is relative path (e.g., "acestep-v15-turbo"), concatenate to checkpoints directory
            acestep_v15_checkpoint_path = os.path.join(checkpoint_dir, config_path)
            if os.path.exists(acestep_v15_checkpoint_path):
                # Determine attention implementation
                if use_flash_attention and self.is_flash_attention_available():
                    attn_implementation = "flash_attention_2"
                    self.dtype = torch.bfloat16
                else:
                    attn_implementation = "sdpa"

                try:
                    logger.info(f"Attempting to load model with attention implementation: {attn_implementation}")
                    self.model = AutoModel.from_pretrained(
                        acestep_v15_checkpoint_path, 
                        trust_remote_code=True, 
                        attn_implementation=attn_implementation,
                        dtype="bfloat16"
                    )
                except Exception as e:
                    logger.warning(f"Failed to load model with {attn_implementation}: {e}")
                    if attn_implementation == "sdpa":
                        logger.info("Falling back to eager attention")
                        attn_implementation = "eager"
                        self.model = AutoModel.from_pretrained(
                            acestep_v15_checkpoint_path, 
                            trust_remote_code=True, 
                            attn_implementation=attn_implementation
                        )
                    else:
                        raise e

                self.model.config._attn_implementation = attn_implementation
                self.config = self.model.config
                # Move model to device and set dtype
                if not self.offload_to_cpu:
                    self.model = self.model.to(device).to(self.dtype)
                else:
                    # If offload_to_cpu is True, check if we should keep DiT on GPU
                    if not self.offload_dit_to_cpu:
                        logger.info(f"Keeping main model on {device} (persistent)")
                        self.model = self.model.to(device).to(self.dtype)
                    else:
                        self.model = self.model.to("cpu").to(self.dtype)
                self.model.eval()
                
                if compile_model:
                    self.model = torch.compile(self.model)
                    
                    if self.quantization is not None:
                        from torchao.quantization import quantize_
                        if self.quantization == "int8_weight_only":
                            from torchao.quantization import Int8WeightOnlyConfig
                            quant_config = Int8WeightOnlyConfig()
                        elif self.quantization == "fp8_weight_only":
                            from torchao.quantization import Float8WeightOnlyConfig
                            quant_config = Float8WeightOnlyConfig()
                        elif self.quantization == "w8a8_dynamic":
                            from torchao.quantization import Int8DynamicActivationInt8WeightConfig, MappingType
                            quant_config = Int8DynamicActivationInt8WeightConfig(act_mapping_type=MappingType.ASYMMETRIC)
                        else:
                            raise ValueError(f"Unsupported quantization type: {self.quantization}")
                        
                        quantize_(self.model, quant_config)
                        logger.info(f"DiT quantized with: {self.quantization}")
                    
                    
                silence_latent_path = os.path.join(acestep_v15_checkpoint_path, "silence_latent.pt")
                if os.path.exists(silence_latent_path):
                    self.silence_latent = torch.load(silence_latent_path).transpose(1, 2)
                    # If DiT is on GPU, silence_latent should also be on GPU
                    if not self.offload_to_cpu or not self.offload_dit_to_cpu:
                        self.silence_latent = self.silence_latent.to(device).to(self.dtype)
                    else:
                        self.silence_latent = self.silence_latent.to("cpu").to(self.dtype)
                else:
                    raise FileNotFoundError(f"Silence latent not found at {silence_latent_path}")
            else:
                raise FileNotFoundError(f"ACE-Step V1.5 checkpoint not found at {acestep_v15_checkpoint_path}")
            
            # 2. Load VAE
            vae_checkpoint_path = os.path.join(checkpoint_dir, "vae")
            if os.path.exists(vae_checkpoint_path):
                self.vae = AutoencoderOobleck.from_pretrained(vae_checkpoint_path)
                # Use bfloat16 for VAE on GPU, otherwise use self.dtype (float32 on CPU)
                vae_dtype = torch.bfloat16 if device in ["cuda", "xpu"] else self.dtype
                if not self.offload_to_cpu:
                    self.vae = self.vae.to(device).to(vae_dtype)
                else:
                    self.vae = self.vae.to("cpu").to(vae_dtype)
                self.vae.eval()
            else:
                raise FileNotFoundError(f"VAE checkpoint not found at {vae_checkpoint_path}")

            if compile_model:
                self.vae = torch.compile(self.vae)
            
            # 3. Load text encoder and tokenizer
            text_encoder_path = os.path.join(checkpoint_dir, "Qwen3-Embedding-0.6B")
            if os.path.exists(text_encoder_path):
                self.text_tokenizer = AutoTokenizer.from_pretrained(text_encoder_path)
                self.text_encoder = AutoModel.from_pretrained(text_encoder_path)
                if not self.offload_to_cpu:
                    self.text_encoder = self.text_encoder.to(device).to(self.dtype)
                else:
                    self.text_encoder = self.text_encoder.to("cpu").to(self.dtype)
                self.text_encoder.eval()
            else:
                raise FileNotFoundError(f"Text encoder not found at {text_encoder_path}")

            # Determine actual attention implementation used
            actual_attn = getattr(self.config, "_attn_implementation", "eager")
            
            status_msg = f"✅ Model initialized successfully on {device}\n"
            status_msg += f"Main model: {acestep_v15_checkpoint_path}\n"
            status_msg += f"VAE: {vae_checkpoint_path}\n"
            status_msg += f"Text encoder: {text_encoder_path}\n"
            status_msg += f"Dtype: {self.dtype}\n"
            status_msg += f"Attention: {actual_attn}\n"
            status_msg += f"Compiled: {compile_model}\n"
            status_msg += f"Offload to CPU: {self.offload_to_cpu}\n"
            status_msg += f"Offload DiT to CPU: {self.offload_dit_to_cpu}"
            
            return status_msg, True
            
        except Exception as e:
            error_msg = f"❌ Error initializing model: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            return error_msg, False
    
    @contextmanager
    def _load_model_context(self, model_name: str):
        """
        Context manager to load a model to GPU and offload it back to CPU after use.
        
        Args:
            model_name: Name of the model to load ("text_encoder", "vae", "model")
        """
        if not self.offload_to_cpu:
            yield
            return

        # If model is DiT ("model") and offload_dit_to_cpu is False, do not offload
        if model_name == "model" and not self.offload_dit_to_cpu:
            # Ensure it's on device if not already (should be handled by init, but safe to check)
            model = getattr(self, model_name, None)
            if model is not None:
                # Check if model is on CPU, if so move to device (one-time move if it was somehow on CPU)
                # We check the first parameter's device
                try:
                    param = next(model.parameters())
                    if param.device.type == "cpu":
                        logger.info(f"Moving {model_name} to {self.device} (persistent)")
                        model.to(self.device).to(self.dtype)
                        if hasattr(self, "silence_latent"):
                            self.silence_latent = self.silence_latent.to(self.device).to(self.dtype)
                except StopIteration:
                    pass
            yield
            return

        model = getattr(self, model_name, None)
        if model is None:
            yield
            return

        # Load to GPU
        logger.info(f"Loading {model_name} to {self.device}")
        start_time = time.time()
        if model_name == "vae":
            vae_dtype = torch.bfloat16 if self.device in ["cuda", "xpu"] else self.dtype
            model.to(self.device).to(vae_dtype)
        else:
            model.to(self.device).to(self.dtype)
        
        if model_name == "model" and hasattr(self, "silence_latent"):
             self.silence_latent = self.silence_latent.to(self.device).to(self.dtype)
        
        load_time = time.time() - start_time
        self.current_offload_cost += load_time
        logger.info(f"Loaded {model_name} to {self.device} in {load_time:.4f}s")

        try:
            yield
        finally:
            # Offload to CPU
            logger.info(f"Offloading {model_name} to CPU")
            start_time = time.time()
            model.to("cpu")
            
            if model_name == "model" and hasattr(self, "silence_latent"):
                 self.silence_latent = self.silence_latent.to("cpu")
            
            torch.cuda.empty_cache()
            offload_time = time.time() - start_time
            self.current_offload_cost += offload_time
            logger.info(f"Offloaded {model_name} to CPU in {offload_time:.4f}s")

    def process_target_audio(self, audio_file) -> Optional[torch.Tensor]:
        """Process target audio"""
        if audio_file is None:
            return None
        
        try:
            # Load audio using soundfile
            audio_np, sr = sf.read(audio_file, dtype='float32')
            # Convert to torch: [samples, channels] or [samples] -> [channels, samples]
            if audio_np.ndim == 1:
                audio = torch.from_numpy(audio_np).unsqueeze(0)
            else:
                audio = torch.from_numpy(audio_np.T)
            
            if audio.shape[0] == 1:
                audio = torch.cat([audio, audio], dim=0)
            
            audio = audio[:2]
            
            # Resample if needed
            if sr != 48000:
                import torch.nn.functional as F
                ratio = 48000 / sr
                new_length = int(audio.shape[-1] * ratio)
                audio = F.interpolate(audio.unsqueeze(0), size=new_length, mode='linear', align_corners=False).squeeze(0)
            
            audio = torch.clamp(audio, -1.0, 1.0)
            
            return audio
        except Exception as e:
            logger.error(f"Error processing target audio: {e}")
            return None
    
    def _parse_audio_code_string(self, code_str: str) -> List[int]:
        """Extract integer audio codes from prompt tokens like <|audio_code_123|>."""
        if not code_str:
            return []
        try:
            return [int(x) for x in re.findall(r"<\|audio_code_(\d+)\|>", code_str)]
        except Exception:
            return []
    
    def _decode_audio_codes_to_latents(self, code_str: str) -> Optional[torch.Tensor]:
        """
        Convert serialized audio code string into 25Hz latents using model quantizer/detokenizer.
        """
        if not self.model or not hasattr(self.model, 'tokenizer') or not hasattr(self.model, 'detokenizer'):
            return None
        
        code_ids = self._parse_audio_code_string(code_str)
        if len(code_ids) == 0:
            return None
        
        with self._load_model_context("model"):
            quantizer = self.model.tokenizer.quantizer
            detokenizer = self.model.detokenizer
            
            num_quantizers = getattr(quantizer, "num_quantizers", 1)
            # Create indices tensor: [T_5Hz]
            indices = torch.tensor(code_ids, device=self.device, dtype=torch.long)  # [T_5Hz]
            
            indices = indices.unsqueeze(0).unsqueeze(-1)  # [1, T_5Hz, 1]
            
            # Get quantized representation from indices
            # The quantizer expects [batch, T_5Hz] format and handles quantizer dimension internally
            quantized = quantizer.get_output_from_indices(indices)
            if quantized.dtype != self.dtype:
                quantized = quantized.to(self.dtype)
            
            # Detokenize to 25Hz: [1, T_5Hz, dim] -> [1, T_25Hz, dim]
            lm_hints_25hz = detokenizer(quantized)
            return lm_hints_25hz
    
    def _create_default_meta(self) -> str:
        """Create default metadata string."""
        return (
            "- bpm: N/A\n"
            "- timesignature: N/A\n" 
            "- keyscale: N/A\n"
            "- duration: 30 seconds\n"
        )
    
    def _dict_to_meta_string(self, meta_dict: Dict[str, Any]) -> str:
        """Convert metadata dict to formatted string."""
        bpm = meta_dict.get('bpm', meta_dict.get('tempo', 'N/A'))
        timesignature = meta_dict.get('timesignature', meta_dict.get('time_signature', 'N/A'))
        keyscale = meta_dict.get('keyscale', meta_dict.get('key', meta_dict.get('scale', 'N/A')))
        duration = meta_dict.get('duration', meta_dict.get('length', 30))

        # Format duration
        if isinstance(duration, (int, float)):
            duration = f"{int(duration)} seconds"
        elif not isinstance(duration, str):
            duration = "30 seconds"
        
        return (
            f"- bpm: {bpm}\n"
            f"- timesignature: {timesignature}\n"
            f"- keyscale: {keyscale}\n"
            f"- duration: {duration}\n"
        )
    
    def _parse_metas(self, metas: List[Union[str, Dict[str, Any]]]) -> List[str]:
        """
        Parse and normalize metadata with fallbacks.
        
        Args:
            metas: List of metadata (can be strings, dicts, or None)
            
        Returns:
            List of formatted metadata strings
        """
        parsed_metas = []
        for meta in metas:
            if meta is None:
                # Default fallback metadata
                parsed_meta = self._create_default_meta()
            elif isinstance(meta, str):
                # Already formatted string
                parsed_meta = meta
            elif isinstance(meta, dict):
                # Convert dict to formatted string
                parsed_meta = self._dict_to_meta_string(meta)
            else:
                # Fallback for any other type
                parsed_meta = self._create_default_meta()
            
            parsed_metas.append(parsed_meta)
        
        return parsed_metas
    
    def build_dit_inputs(
        self,
        task: str,
        instruction: Optional[str],
        caption: str,
        lyrics: str,
        metas: Optional[Union[str, Dict[str, Any]]] = None,
        vocal_language: str = "en",
    ) -> Tuple[str, str]:
        """
        Build text inputs for the caption and lyric branches used by DiT.

        Args:
            task: Task name (e.g., text2music, cover, repaint); kept for logging/future branching.
            instruction: Instruction text; default fallback matches service_generate behavior.
            caption: Caption string.
            lyrics: Lyrics string.
            metas: Metadata (str or dict); follows _parse_metas formatting.
            vocal_language: Language code for lyrics section.

        Returns:
            (caption_input_text, lyrics_input_text)

        Example:
            caption_input, lyrics_input = handler.build_dit_inputs(
                task="text2music",
                instruction=None,
                caption="A calm piano melody",
                lyrics="la la la",
                metas={"bpm": 90, "duration": 45},
                vocal_language="en",
            )
        """
        # Align instruction formatting with _prepare_batch
        final_instruction = instruction or "Fill the audio semantic mask based on the given conditions:"
        if not final_instruction.endswith(":"):
            final_instruction = final_instruction + ":"

        parsed_meta = self._parse_metas([metas])[0]
        caption_input = SFT_GEN_PROMPT.format(final_instruction, caption, parsed_meta)
        lyrics_input = f"# Languages\n{vocal_language}\n\n# Lyric\n{lyrics}<|endoftext|>"
        return caption_input, lyrics_input
    
    def _get_text_hidden_states(self, text_prompt: str) -> Tuple[torch.Tensor, torch.Tensor]:
        """Get text hidden states from text encoder."""
        if self.text_tokenizer is None or self.text_encoder is None:
            raise ValueError("Text encoder not initialized")
        
        with self._load_model_context("text_encoder"):
            # Tokenize
            text_inputs = self.text_tokenizer(
                text_prompt,
                padding="longest",
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            text_input_ids = text_inputs.input_ids.to(self.device)
            text_attention_mask = text_inputs.attention_mask.to(self.device).bool()
            
            # Encode
            with torch.no_grad():
                text_outputs = self.text_encoder(text_input_ids)
                if hasattr(text_outputs, 'last_hidden_state'):
                    text_hidden_states = text_outputs.last_hidden_state
                elif isinstance(text_outputs, tuple):
                    text_hidden_states = text_outputs[0]
                else:
                    text_hidden_states = text_outputs
            
            text_hidden_states = text_hidden_states.to(self.dtype)
            
            return text_hidden_states, text_attention_mask
    
    def extract_caption_from_sft_format(self, caption: str) -> str:
        try:
            if "# Instruction" in caption and "# Caption" in caption:
                pattern = r'#\s*Caption\s*\n(.*?)(?:\n\s*#\s*Metas|$)'
                match = re.search(pattern, caption, re.DOTALL)
                if match:
                    return match.group(1).strip()
            return caption
        except Exception as e:
            logger.error(f"Error extracting caption: {e}")
            return caption

    def prepare_seeds(self, actual_batch_size, seed, use_random_seed):
        actual_seed_list: List[int] = []
        seed_value_for_ui = ""

        if use_random_seed:
            # Generate brand new seeds and expose them back to the UI
            actual_seed_list = [random.randint(0, 2 ** 32 - 1) for _ in range(actual_batch_size)]
            seed_value_for_ui = ", ".join(str(s) for s in actual_seed_list)
        else:
            # Parse seed input: can be a single number, comma-separated numbers, or -1
            # If seed is a string, try to parse it as comma-separated values
            seed_list = []
            if isinstance(seed, str):
                # Handle string input (e.g., "123,456" or "-1")
                seed_str_list = [s.strip() for s in seed.split(",")]
                for s in seed_str_list:
                    if s == "-1" or s == "":
                        seed_list.append(-1)
                    else:
                        try:
                            seed_list.append(int(float(s)))
                        except (ValueError, TypeError):
                            seed_list.append(-1)
            elif seed is None or (isinstance(seed, (int, float)) and seed < 0):
                # If seed is None or negative, use -1 for all items
                seed_list = [-1] * actual_batch_size
            elif isinstance(seed, (int, float)):
                # Single seed value
                seed_list = [int(seed)]
            else:
                # Fallback: use -1
                seed_list = [-1] * actual_batch_size

            # Process seed list according to rules:
            # 1. If all are -1, generate different random seeds for each batch item
            # 2. If one non-negative seed is provided and batch_size > 1, first uses that seed, rest are random
            # 3. If more seeds than batch_size, use first batch_size seeds
            # Check if user provided only one non-negative seed (not -1)
            has_single_non_negative_seed = (len(seed_list) == 1 and seed_list[0] != -1)

            for i in range(actual_batch_size):
                if i < len(seed_list):
                    seed_val = seed_list[i]
                else:
                    # If not enough seeds provided, use -1 (will generate random)
                    seed_val = -1

                # Special case: if only one non-negative seed was provided and batch_size > 1,
                # only the first item uses that seed, others are random
                if has_single_non_negative_seed and actual_batch_size > 1 and i > 0:
                    # Generate random seed for remaining items
                    actual_seed_list.append(random.randint(0, 2 ** 32 - 1))
                elif seed_val == -1:
                    # Generate a random seed for this item
                    actual_seed_list.append(random.randint(0, 2 ** 32 - 1))
                else:
                    actual_seed_list.append(int(seed_val))

            seed_value_for_ui = ", ".join(str(s) for s in actual_seed_list)
        return actual_seed_list, seed_value_for_ui
    
    def prepare_metadata(self, bpm, key_scale, time_signature):
        # Build metadata dict - use "N/A" as default for empty fields
        metadata_dict = {}
        if bpm:
            metadata_dict["bpm"] = bpm
        else:
            metadata_dict["bpm"] = "N/A"

        if key_scale.strip():
            metadata_dict["keyscale"] = key_scale
        else:
            metadata_dict["keyscale"] = "N/A"

        if time_signature.strip() and time_signature != "N/A" and time_signature:
            metadata_dict["timesignature"] = time_signature
        else:
            metadata_dict["timesignature"] = "N/A"
        return metadata_dict
    
    def is_silence(self, audio):
        return torch.all(audio.abs() < 1e-6)

    def generate_instruction(
        self,
        task_type: str,
        track_name: Optional[str] = None,
        complete_track_classes: Optional[List[str]] = None
    ) -> str:
        TRACK_NAMES = [
            "woodwinds", "brass", "fx", "synth", "strings", "percussion",
            "keyboard", "guitar", "bass", "drums", "backing_vocals", "vocals"
        ]
        
        if task_type == "text2music":
            return "Fill the audio semantic mask based on the given conditions:"
        elif task_type == "repaint":
            return "Repaint the mask area based on the given conditions:"
        elif task_type == "cover":
            return "Generate audio semantic tokens based on the given conditions:"
        elif task_type == "extract":
            if track_name:
                # Convert to uppercase
                track_name_upper = track_name.upper()
                return f"Extract the {track_name_upper} track from the audio:"
            else:
                return "Extract the track from the audio:"
        elif task_type == "lego":
            if track_name:
                # Convert to uppercase
                track_name_upper = track_name.upper()
                return f"Generate the {track_name_upper} track based on the audio context:"
            else:
                return "Generate the track based on the audio context:"
        elif task_type == "complete":
            if complete_track_classes and len(complete_track_classes) > 0:
                # Convert to uppercase and join with " | "
                track_classes_upper = [t.upper() for t in complete_track_classes]
                complete_track_classes_str = " | ".join(track_classes_upper)
                return f"Complete the input track with {complete_track_classes_str}:"
            else:
                return "Complete the input track:"
        else:
            return "Fill the audio semantic mask based on the given conditions:"
    
    def process_reference_audio(self, audio_file) -> Optional[torch.Tensor]:
        if audio_file is None:
            return None
            
        try:
            # Load audio file
            audio, sr = torchaudio.load(audio_file)
            
            logger.info(f"Reference audio shape: {audio.shape}")
            logger.info(f"Reference audio sample rate: {sr}")
            logger.info(f"Reference audio duration: {audio.shape[-1] / 48000.0} seconds")
            
            # Convert to stereo (duplicate channel if mono)
            if audio.shape[0] == 1:
                audio = torch.cat([audio, audio], dim=0)
            
            # Keep only first 2 channels
            audio = audio[:2]
            
            # Resample to 48kHz if needed
            if sr != 48000:
                audio = torchaudio.transforms.Resample(sr, 48000)(audio)
            
            # Clamp values to [-1.0, 1.0]
            audio = torch.clamp(audio, -1.0, 1.0)
            
            is_silence = self.is_silence(audio)
            if is_silence:
                return None
            
            # Target length: 30 seconds at 48kHz
            target_frames = 30 * 48000
            segment_frames = 10 * 48000  # 10 seconds per segment
            
            # If audio is less than 30 seconds, repeat to at least 30 seconds
            if audio.shape[-1] < target_frames:
                repeat_times = math.ceil(target_frames / audio.shape[-1])
                audio = audio.repeat(1, repeat_times)
            # If audio is greater than or equal to 30 seconds, no operation needed
            
            # For all cases, select random 10-second segments from front, middle, and back
            # then concatenate them to form 30 seconds
            total_frames = audio.shape[-1]
            segment_size = total_frames // 3
            
            # Front segment: [0, segment_size]
            front_start = random.randint(0, max(0, segment_size - segment_frames))
            front_audio = audio[:, front_start:front_start + segment_frames]
            
            # Middle segment: [segment_size, 2*segment_size]
            middle_start = segment_size + random.randint(0, max(0, segment_size - segment_frames))
            middle_audio = audio[:, middle_start:middle_start + segment_frames]
            
            # Back segment: [2*segment_size, total_frames]
            back_start = 2 * segment_size + random.randint(0, max(0, (total_frames - 2 * segment_size) - segment_frames))
            back_audio = audio[:, back_start:back_start + segment_frames]
            
            # Concatenate three segments to form 30 seconds
            audio = torch.cat([front_audio, middle_audio, back_audio], dim=-1)
            
            return audio
            
        except Exception as e:
            logger.error(f"Error processing reference audio: {e}")
            return None

    def process_src_audio(self, audio_file) -> Optional[torch.Tensor]:
        if audio_file is None:
            return None
            
        try:
            # Load audio file
            audio, sr = torchaudio.load(audio_file)
            
            # Convert to stereo (duplicate channel if mono)
            if audio.shape[0] == 1:
                audio = torch.cat([audio, audio], dim=0)
            
            # Keep only first 2 channels
            audio = audio[:2]
            
            # Resample to 48kHz if needed
            if sr != 48000:
                audio = torchaudio.transforms.Resample(sr, 48000)(audio)
            
            # Clamp values to [-1.0, 1.0]
            audio = torch.clamp(audio, -1.0, 1.0)
            
            return audio
            
        except Exception as e:
            logger.error(f"Error processing target audio: {e}")
            return None
    
    def convert_src_audio_to_codes(self, audio_file) -> str:
        """
        Convert uploaded source audio to audio codes string.
        
        Args:
            audio_file: Path to audio file or None
            
        Returns:
            Formatted codes string like '<|audio_code_123|><|audio_code_456|>...' or error message
        """
        if audio_file is None:
            return "❌ Please upload source audio first"
        
        if self.model is None or self.vae is None:
            return "❌ Model not initialized. Please initialize the service first."
        
        try:
            # Process audio file
            processed_audio = self.process_src_audio(audio_file)
            if processed_audio is None:
                return "❌ Failed to process audio file"
            
            # Encode audio to latents using VAE
            with torch.no_grad():
                with self._load_model_context("vae"):
                    # Prepare audio for VAE: [channels, samples] -> [1, channels, samples]
                    vae_input = processed_audio.unsqueeze(0).to(self.device).to(self.vae.dtype)
                    
                    # Check if audio is silence
                    if self.is_silence(vae_input):
                        return "❌ Audio file appears to be silent"
                    
                    # Encode to latents
                    latents = self.vae.encode(vae_input).latent_dist.sample()
                    # Cast back to model dtype
                    latents = latents.to(self.dtype)
                    # Transpose: [1, d, T] -> [1, T, d] -> [T, d]
                    latents = latents.squeeze(0).transpose(0, 1)  # [T, d]
                
                # Create attention mask for latents
                attention_mask = torch.ones(latents.shape[0], dtype=torch.bool, device=self.device)
                
                # Tokenize latents to get code indices
                with self._load_model_context("model"):
                    # Prepare latents for tokenize: [T, d] -> [1, T, d]
                    hidden_states = latents.unsqueeze(0)  # [1, T, d]
                    
                    # Call tokenize method
                    # tokenize returns: (quantized, indices, attention_mask)
                    _, indices, _ = self.model.tokenize(hidden_states, self.silence_latent, attention_mask.unsqueeze(0))
                    
                    # Format indices as code string
                    # indices shape: [1, T_5Hz] or [1, T_5Hz, num_quantizers]
                    # Flatten and convert to list
                    indices_flat = indices.flatten().cpu().tolist()
                    codes_string = "".join([f"<|audio_code_{idx}|>" for idx in indices_flat])
                    
                    logger.info(f"[convert_src_audio_to_codes] Generated {len(indices_flat)} audio codes")
                    return codes_string
                    
        except Exception as e:
            error_msg = f"❌ Error converting audio to codes: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return error_msg
        
    def prepare_batch_data(
        self,
        actual_batch_size,
        processed_src_audio,
        audio_duration,
        captions,
        lyrics,
        vocal_language,
        instruction,
        bpm,
        key_scale,
        time_signature
    ):
        pure_caption = self.extract_caption_from_sft_format(captions)
        captions_batch = [pure_caption] * actual_batch_size
        instructions_batch = [instruction] * actual_batch_size
        lyrics_batch = [lyrics] * actual_batch_size
        vocal_languages_batch = [vocal_language] * actual_batch_size
        # Calculate duration for metadata
        calculated_duration = None
        if processed_src_audio is not None:
            calculated_duration = processed_src_audio.shape[-1] / 48000.0
        elif audio_duration is not None and audio_duration > 0:
            calculated_duration = audio_duration

        # Build metadata dict - use "N/A" as default for empty fields
        metadata_dict = {}
        if bpm:
            metadata_dict["bpm"] = bpm
        else:
            metadata_dict["bpm"] = "N/A"

        if key_scale.strip():
            metadata_dict["keyscale"] = key_scale
        else:
            metadata_dict["keyscale"] = "N/A"

        if time_signature.strip() and time_signature != "N/A" and time_signature:
            metadata_dict["timesignature"] = time_signature
        else:
            metadata_dict["timesignature"] = "N/A"

        # Add duration to metadata if available (inference service format: "30 seconds")
        if calculated_duration is not None:
            metadata_dict["duration"] = f"{int(calculated_duration)} seconds"
        # If duration not set, inference service will use default (30 seconds)

        # Format metadata - inference service accepts dict and will convert to string
        # Create a copy for each batch item (in case we modify it)
        metas_batch = [metadata_dict.copy() for _ in range(actual_batch_size)]
        return captions_batch, instructions_batch, lyrics_batch, vocal_languages_batch, metas_batch
    
    def determine_task_type(self, task_type, audio_code_string):
        # Determine task type - repaint and lego tasks can have repainting parameters
        # Other tasks (cover, text2music, extract, complete) should NOT have repainting
        is_repaint_task = (task_type == "repaint")
        is_lego_task = (task_type == "lego")
        is_cover_task = (task_type == "cover")

        has_codes = False
        if isinstance(audio_code_string, list):
            has_codes = any((c or "").strip() for c in audio_code_string)
        else:
            has_codes = bool(audio_code_string and str(audio_code_string).strip())

        if has_codes:
            is_cover_task = True
        # Both repaint and lego tasks can use repainting parameters for chunk mask
        can_use_repainting = is_repaint_task or is_lego_task
        return is_repaint_task, is_lego_task, is_cover_task, can_use_repainting

    def create_target_wavs(self, duration_seconds: float) -> torch.Tensor:
        try:
            # Ensure minimum precision of 100ms
            duration_seconds = max(0.1, round(duration_seconds, 1))
            # Calculate frames for 48kHz stereo
            frames = int(duration_seconds * 48000)
            # Create silent stereo audio
            target_wavs = torch.zeros(2, frames)
            return target_wavs
        except Exception as e:
            logger.error(f"Error creating target audio: {e}")
            # Fallback to 30 seconds if error
            return torch.zeros(2, 30 * 48000)
    
    def prepare_padding_info(
        self,
        actual_batch_size,
        processed_src_audio,
        audio_duration,
        repainting_start,
        repainting_end,
        is_repaint_task,
        is_lego_task,
        is_cover_task,
        can_use_repainting,
    ):
        target_wavs_batch = []
        # Store padding info for each batch item to adjust repainting coordinates
        padding_info_batch = []
        for i in range(actual_batch_size):
            if processed_src_audio is not None:
                if is_cover_task:
                    # Cover task: Use src_audio directly without padding
                    batch_target_wavs = processed_src_audio
                    padding_info_batch.append({
                        'left_padding_duration': 0.0,
                        'right_padding_duration': 0.0
                    })
                elif is_repaint_task or is_lego_task:
                    # Repaint/lego task: May need padding for outpainting
                    src_audio_duration = processed_src_audio.shape[-1] / 48000.0

                    # Determine actual end time
                    if repainting_end is None or repainting_end < 0:
                        actual_end = src_audio_duration
                    else:
                        actual_end = repainting_end

                    left_padding_duration = max(0, -repainting_start) if repainting_start is not None else 0
                    right_padding_duration = max(0, actual_end - src_audio_duration)

                    # Create padded audio
                    left_padding_frames = int(left_padding_duration * 48000)
                    right_padding_frames = int(right_padding_duration * 48000)

                    if left_padding_frames > 0 or right_padding_frames > 0:
                        # Pad the src audio
                        batch_target_wavs = torch.nn.functional.pad(
                            processed_src_audio,
                            (left_padding_frames, right_padding_frames),
                            'constant', 0
                        )
                    else:
                        batch_target_wavs = processed_src_audio

                    # Store padding info for coordinate adjustment
                    padding_info_batch.append({
                        'left_padding_duration': left_padding_duration,
                        'right_padding_duration': right_padding_duration
                    })
                else:
                    # Other tasks: Use src_audio directly without padding
                    batch_target_wavs = processed_src_audio
                    padding_info_batch.append({
                        'left_padding_duration': 0.0,
                        'right_padding_duration': 0.0
                    })
            else:
                padding_info_batch.append({
                    'left_padding_duration': 0.0,
                    'right_padding_duration': 0.0
                })
                if audio_duration is not None and audio_duration > 0:
                    batch_target_wavs = self.create_target_wavs(audio_duration)
                else:
                    import random
                    random_duration = random.uniform(10.0, 120.0)
                    batch_target_wavs = self.create_target_wavs(random_duration)
            target_wavs_batch.append(batch_target_wavs)

        # Stack target_wavs into batch tensor
        # Ensure all tensors have the same shape by padding to max length
        max_frames = max(wav.shape[-1] for wav in target_wavs_batch)
        padded_target_wavs = []
        for wav in target_wavs_batch:
            if wav.shape[-1] < max_frames:
                pad_frames = max_frames - wav.shape[-1]
                padded_wav = torch.nn.functional.pad(wav, (0, pad_frames), 'constant', 0)
                padded_target_wavs.append(padded_wav)
            else:
                padded_target_wavs.append(wav)

        target_wavs_tensor = torch.stack(padded_target_wavs, dim=0)  # [batch_size, 2, frames]

        if can_use_repainting:
            # Repaint task: Set repainting parameters
            if repainting_start is None:
                repainting_start_batch = None
            elif isinstance(repainting_start, (int, float)):
                if processed_src_audio is not None:
                    adjusted_start = repainting_start + padding_info_batch[0]['left_padding_duration']
                    repainting_start_batch = [adjusted_start] * actual_batch_size
                else:
                    repainting_start_batch = [repainting_start] * actual_batch_size
            else:
                # List input - adjust each item
                repainting_start_batch = []
                for i in range(actual_batch_size):
                    if processed_src_audio is not None:
                        adjusted_start = repainting_start[i] + padding_info_batch[i]['left_padding_duration']
                        repainting_start_batch.append(adjusted_start)
                    else:
                        repainting_start_batch.append(repainting_start[i])

            # Handle repainting_end - use src audio duration if not specified or negative
            if processed_src_audio is not None:
                # If src audio is provided, use its duration as default end
                src_audio_duration = processed_src_audio.shape[-1] / 48000.0
                if repainting_end is None or repainting_end < 0:
                    # Use src audio duration (before padding), then adjust for padding
                    adjusted_end = src_audio_duration + padding_info_batch[0]['left_padding_duration']
                    repainting_end_batch = [adjusted_end] * actual_batch_size
                else:
                    # Adjust repainting_end to be relative to padded audio
                    adjusted_end = repainting_end + padding_info_batch[0]['left_padding_duration']
                    repainting_end_batch = [adjusted_end] * actual_batch_size
            else:
                # No src audio - repainting doesn't make sense without it
                if repainting_end is None or repainting_end < 0:
                    repainting_end_batch = None
                elif isinstance(repainting_end, (int, float)):
                    repainting_end_batch = [repainting_end] * actual_batch_size
                else:
                    # List input - adjust each item
                    repainting_end_batch = []
                    for i in range(actual_batch_size):
                        if processed_src_audio is not None:
                            adjusted_end = repainting_end[i] + padding_info_batch[i]['left_padding_duration']
                            repainting_end_batch.append(adjusted_end)
                        else:
                            repainting_end_batch.append(repainting_end[i])
        else:
            # All other tasks (cover, text2music, extract, complete): No repainting
            # Only repaint and lego tasks should have repainting parameters
            repainting_start_batch = None
            repainting_end_batch = None
            
        return repainting_start_batch, repainting_end_batch, target_wavs_tensor

    def _prepare_batch(
        self,
        captions: List[str],
        lyrics: List[str],
        keys: Optional[List[str]] = None,
        target_wavs: Optional[torch.Tensor] = None,
        refer_audios: Optional[List[List[torch.Tensor]]] = None,
        metas: Optional[List[Union[str, Dict[str, Any]]]] = None,
        vocal_languages: Optional[List[str]] = None,
        repainting_start: Optional[List[float]] = None,
        repainting_end: Optional[List[float]] = None,
        instructions: Optional[List[str]] = None,
        audio_code_hints: Optional[List[Optional[str]]] = None,
        audio_cover_strength: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Prepare batch data with fallbacks for missing inputs.
        
        Args:
            captions: List of text captions (optional, can be empty strings)
            lyrics: List of lyrics (optional, can be empty strings)
            keys: List of unique identifiers (optional)
            target_wavs: Target audio tensors (optional, will use silence if not provided)
            refer_audios: Reference audio tensors (optional, will use silence if not provided)
            metas: Metadata (optional, will use defaults if not provided)
            vocal_languages: Vocal languages (optional, will default to 'en')
            
        Returns:
            Batch dictionary ready for model input
        """
        batch_size = len(captions)

        # Ensure audio_code_hints is a list of the correct length
        if audio_code_hints is None:
            audio_code_hints = [None] * batch_size
        elif len(audio_code_hints) != batch_size:
            if len(audio_code_hints) == 1:
                audio_code_hints = audio_code_hints * batch_size
            else:
                audio_code_hints = audio_code_hints[:batch_size]
                while len(audio_code_hints) < batch_size:
                    audio_code_hints.append(None)
        
        for ii, refer_audio_list in enumerate(refer_audios):
            if isinstance(refer_audio_list, list):
                for idx, refer_audio in enumerate(refer_audio_list):
                    refer_audio_list[idx] = refer_audio_list[idx].to(self.device).to(torch.bfloat16)
            elif isinstance(refer_audio_list, torch.Tensor):
                refer_audios[ii] = refer_audios[ii].to(self.device)
        
        if vocal_languages is None:
            vocal_languages = self._create_fallback_vocal_languages(batch_size)
        
        # Normalize audio_code_hints to batch list
        if audio_code_hints is None:
            audio_code_hints = [None] * batch_size
        elif not isinstance(audio_code_hints, list):
            audio_code_hints = [audio_code_hints] * batch_size
        elif len(audio_code_hints) == 1 and batch_size > 1:
            audio_code_hints = audio_code_hints * batch_size
        else:
            audio_code_hints = (audio_code_hints + [None] * batch_size)[:batch_size]
        audio_code_hints = [hint if isinstance(hint, str) and hint.strip() else None for hint in audio_code_hints]
        
        # Parse metas with fallbacks
        parsed_metas = self._parse_metas(metas)
        
        # Encode target_wavs to get target_latents
        with torch.no_grad():
            target_latents_list = []
            latent_lengths = []
            # Use per-item wavs (may be adjusted if audio_code_hints are provided)
            target_wavs_list = [target_wavs[i].clone() for i in range(batch_size)]
            if target_wavs.device != self.device:
                target_wavs = target_wavs.to(self.device)
            
            with self._load_model_context("vae"):
                for i in range(batch_size):
                    code_hint = audio_code_hints[i]
                    # Prefer decoding from provided audio codes
                    if code_hint:
                        logger.info(f"[generate_music] Decoding audio codes for item {i}...")
                        decoded_latents = self._decode_audio_codes_to_latents(code_hint)
                        if decoded_latents is not None:
                            decoded_latents = decoded_latents.squeeze(0)
                            target_latents_list.append(decoded_latents)
                            latent_lengths.append(decoded_latents.shape[0])
                            # Create a silent wav matching the latent length for downstream scaling
                            frames_from_codes = max(1, int(decoded_latents.shape[0] * 1920))
                            target_wavs_list[i] = torch.zeros(2, frames_from_codes)
                            continue
                    # Fallback to VAE encode from audio
                    current_wav = target_wavs_list[i].to(self.device).unsqueeze(0)
                    if self.is_silence(current_wav):
                        expected_latent_length = current_wav.shape[-1] // 1920
                        target_latent = self.silence_latent[0, :expected_latent_length, :]
                    else:
                        # Ensure input is in VAE's dtype
                        logger.info(f"[generate_music] Encoding target audio to latents for item {i}...")
                        vae_input = current_wav.to(self.device).to(self.vae.dtype)
                        target_latent = self.vae.encode(vae_input).latent_dist.sample()
                        # Cast back to model dtype
                        target_latent = target_latent.to(self.dtype)
                        target_latent = target_latent.squeeze(0).transpose(0, 1)
                    target_latents_list.append(target_latent)
                    latent_lengths.append(target_latent.shape[0])
             
            # Pad target_wavs to consistent length for outputs
            max_target_frames = max(wav.shape[-1] for wav in target_wavs_list)
            padded_target_wavs = []
            for wav in target_wavs_list:
                if wav.shape[-1] < max_target_frames:
                    pad_frames = max_target_frames - wav.shape[-1]
                    wav = torch.nn.functional.pad(wav, (0, pad_frames), "constant", 0)
                padded_target_wavs.append(wav)
            target_wavs = torch.stack(padded_target_wavs)
            wav_lengths = torch.tensor([target_wavs.shape[-1]] * batch_size, dtype=torch.long)
            
            # Pad latents to same length
            max_latent_length = max(latent.shape[0] for latent in target_latents_list)
            max_latent_length = max(128, max_latent_length)
            
            padded_latents = []
            for latent in target_latents_list:
                latent_length = latent.shape[0]
                
                if latent.shape[0] < max_latent_length:
                    pad_length = max_latent_length - latent.shape[0]
                    latent = torch.cat([latent, self.silence_latent[0, :pad_length, :]], dim=0)
                padded_latents.append(latent)
            
            target_latents = torch.stack(padded_latents)
            latent_masks = torch.stack([
                torch.cat([
                    torch.ones(l, dtype=torch.long, device=self.device),
                    torch.zeros(max_latent_length - l, dtype=torch.long, device=self.device)
                ])
                for l in latent_lengths
            ])
        
        # Process instructions early so we can use them for task type detection
        # Use custom instructions if provided, otherwise use default
        if instructions is None:
            instructions = ["Fill the audio semantic mask based on the given conditions:"] * batch_size
        
        # Ensure instructions list has the same length as batch_size
        if len(instructions) != batch_size:
            if len(instructions) == 1:
                instructions = instructions * batch_size
            else:
                # Pad or truncate to match batch_size
                instructions = instructions[:batch_size]
                while len(instructions) < batch_size:
                    instructions.append("Fill the audio semantic mask based on the given conditions:")
        
        # Generate chunk_masks and spans based on repainting parameters
        # Also determine if this is a cover task (target audio provided without repainting)
        chunk_masks = []
        spans = []
        is_covers = []
        # Store repainting latent ranges for later use in src_latents creation
        repainting_ranges = {}  # {batch_idx: (start_latent, end_latent)}
        
        for i in range(batch_size):
            has_code_hint = audio_code_hints[i] is not None
            # Check if repainting is enabled for this batch item
            has_repainting = False
            if repainting_start is not None and repainting_end is not None:
                start_sec = repainting_start[i] if repainting_start[i] is not None else 0.0
                end_sec = repainting_end[i]
                
                if end_sec is not None and end_sec > start_sec:
                    # Repainting mode with outpainting support
                    # The target_wavs may have been padded for outpainting
                    # Need to calculate the actual position in the padded audio
                    
                    # Calculate padding (if start < 0, there's left padding)
                    left_padding_sec = max(0, -start_sec)
                    
                    # Adjust positions to account for padding
                    # In the padded audio, the original start is shifted by left_padding
                    adjusted_start_sec = start_sec + left_padding_sec
                    adjusted_end_sec = end_sec + left_padding_sec
                    
                    # Convert seconds to latent frames (audio_frames / 1920 = latent_frames)
                    start_latent = int(adjusted_start_sec * self.sample_rate // 1920)
                    end_latent = int(adjusted_end_sec * self.sample_rate // 1920)

                    # Clamp to valid range
                    start_latent = max(0, min(start_latent, max_latent_length - 1))
                    end_latent = max(start_latent + 1, min(end_latent, max_latent_length))
                    # Create mask: False = keep original, True = generate new
                    mask = torch.zeros(max_latent_length, dtype=torch.bool, device=self.device)
                    mask[start_latent:end_latent] = True
                    chunk_masks.append(mask)
                    spans.append(("repainting", start_latent, end_latent))
                    # Store repainting range for later use
                    repainting_ranges[i] = (start_latent, end_latent)
                    has_repainting = True
                    is_covers.append(False)  # Repainting is not cover task
                else:
                    # Full generation (no valid repainting range)
                    chunk_masks.append(torch.ones(max_latent_length, dtype=torch.bool, device=self.device))
                    spans.append(("full", 0, max_latent_length))
                    # Determine task type from instruction, not from target_wavs
                    # Only cover task should have is_cover=True
                    instruction_i = instructions[i] if instructions and i < len(instructions) else ""
                    instruction_lower = instruction_i.lower()
                    # Cover task instruction: "Generate audio semantic tokens based on the given conditions:"
                    is_cover = ("generate audio semantic tokens" in instruction_lower and 
                               "based on the given conditions" in instruction_lower) or has_code_hint
                    is_covers.append(is_cover)
            else:
                # Full generation (no repainting parameters)
                chunk_masks.append(torch.ones(max_latent_length, dtype=torch.bool, device=self.device))
                spans.append(("full", 0, max_latent_length))
                # Determine task type from instruction, not from target_wavs
                # Only cover task should have is_cover=True
                instruction_i = instructions[i] if instructions and i < len(instructions) else ""
                instruction_lower = instruction_i.lower()
                # Cover task instruction: "Generate audio semantic tokens based on the given conditions:"
                is_cover = ("generate audio semantic tokens" in instruction_lower and 
                           "based on the given conditions" in instruction_lower) or has_code_hint
                is_covers.append(is_cover)
        
        chunk_masks = torch.stack(chunk_masks)
        is_covers = torch.BoolTensor(is_covers).to(self.device)
        
        # Create src_latents based on task type
        # For cover/extract/complete/lego/repaint tasks: src_latents = target_latents.clone() (if target_wavs provided)
        # For text2music task: src_latents = silence_latent (if no target_wavs or silence)
        # For repaint task: additionally replace inpainting region with silence_latent
        src_latents_list = []
        silence_latent_tiled = self.silence_latent[0, :max_latent_length, :]
        for i in range(batch_size):
            # Check if target_wavs is provided and not silent (for extract/complete/lego/cover/repaint tasks)
            has_code_hint = audio_code_hints[i] is not None
            has_target_audio = has_code_hint or (target_wavs is not None and target_wavs[i].abs().sum() > 1e-6)
            
            if has_target_audio:
                # For tasks that use input audio (cover/extract/complete/lego/repaint)
                # Check if this item has repainting
                item_has_repainting = (i in repainting_ranges)
                
                if item_has_repainting:
                    # Repaint task: src_latents = target_latents with inpainting region replaced by silence_latent
                    # 1. Clone target_latents (encoded from src audio, preserving original audio)
                    src_latent = target_latents[i].clone()
                    # 2. Replace inpainting region with silence_latent
                    start_latent, end_latent = repainting_ranges[i]
                    src_latent[start_latent:end_latent] = silence_latent_tiled[start_latent:end_latent]
                    src_latents_list.append(src_latent)
                else:
                    # Cover/extract/complete/lego tasks: src_latents = target_latents.clone()
                    # All these tasks need to base on input audio
                    src_latents_list.append(target_latents[i].clone())
            else:
                # Text2music task: src_latents = silence_latent (no input audio)
                # Use silence_latent for the full length
                src_latents_list.append(silence_latent_tiled.clone())
        
        src_latents = torch.stack(src_latents_list)
        
        # Process audio_code_hints to generate precomputed_lm_hints_25Hz
        precomputed_lm_hints_25Hz_list = []
        for i in range(batch_size):
            if audio_code_hints[i] is not None:
                # Decode audio codes to 25Hz latents
                logger.info(f"[generate_music] Decoding audio codes for LM hints for item {i}...")
                hints = self._decode_audio_codes_to_latents(audio_code_hints[i])
                if hints is not None:
                    # Pad or crop to match max_latent_length
                    if hints.shape[1] < max_latent_length:
                        pad_length = max_latent_length - hints.shape[1]
                        pad = self.silence_latent
                        # Match dims: hints is usually [1, T, D], silence_latent is [1, T, D]
                        if pad.dim() == 2:
                            pad = pad.unsqueeze(0)
                        if hints.dim() == 2:
                            hints = hints.unsqueeze(0)
                        pad_chunk = pad[:, :pad_length, :]
                        if pad_chunk.device != hints.device or pad_chunk.dtype != hints.dtype:
                            pad_chunk = pad_chunk.to(device=hints.device, dtype=hints.dtype)
                        hints = torch.cat([hints, pad_chunk], dim=1)
                    elif hints.shape[1] > max_latent_length:
                        hints = hints[:, :max_latent_length, :]
                    precomputed_lm_hints_25Hz_list.append(hints[0])  # Remove batch dimension
                else:
                    precomputed_lm_hints_25Hz_list.append(None)
            else:
                precomputed_lm_hints_25Hz_list.append(None)
        
        # Stack precomputed hints if any exist, otherwise set to None
        if any(h is not None for h in precomputed_lm_hints_25Hz_list):
            # For items without hints, use silence_latent as placeholder
            precomputed_lm_hints_25Hz = torch.stack([
                h if h is not None else silence_latent_tiled
                for h in precomputed_lm_hints_25Hz_list
            ])
        else:
            precomputed_lm_hints_25Hz = None
        
        # Format text_inputs
        text_inputs = []
        text_token_idss = []
        text_attention_masks = []
        lyric_token_idss = []
        lyric_attention_masks = []
        
        for i in range(batch_size):
            # Use custom instruction for this batch item
            instruction = instructions[i] if i < len(instructions) else "Fill the audio semantic mask based on the given conditions:"
            # Ensure instruction ends with ":"
            if not instruction.endswith(":"):
                instruction = instruction + ":"
            
            # Format text prompt with custom instruction
            text_prompt = SFT_GEN_PROMPT.format(instruction, captions[i], parsed_metas[i])
            
            # Tokenize text
            text_inputs_dict = self.text_tokenizer(
                text_prompt,
                padding="longest",
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            text_token_ids = text_inputs_dict.input_ids[0]
            text_attention_mask = text_inputs_dict.attention_mask[0].bool()
            
            # Format and tokenize lyrics
            lyrics_text = f"# Languages\n{vocal_languages[i]}\n\n# Lyric\n{lyrics[i]}<|endoftext|>"
            lyrics_inputs_dict = self.text_tokenizer(
                lyrics_text,
                padding="longest",
                truncation=True,
                max_length=2048,
                return_tensors="pt",
            )
            lyric_token_ids = lyrics_inputs_dict.input_ids[0]
            lyric_attention_mask = lyrics_inputs_dict.attention_mask[0].bool()
            
            # Build full text input
            text_input = text_prompt + "\n\n" + lyrics_text
            
            text_inputs.append(text_input)
            text_token_idss.append(text_token_ids)
            text_attention_masks.append(text_attention_mask)
            lyric_token_idss.append(lyric_token_ids)
            lyric_attention_masks.append(lyric_attention_mask)
            
        # Pad tokenized sequences
        max_text_length = max(len(seq) for seq in text_token_idss)
        padded_text_token_idss = torch.stack([
            torch.nn.functional.pad(
                seq, (0, max_text_length - len(seq)), 'constant',
                self.text_tokenizer.pad_token_id
            )
            for seq in text_token_idss
        ])
        
        padded_text_attention_masks = torch.stack([
            torch.nn.functional.pad(
                seq, (0, max_text_length - len(seq)), 'constant', 0
            )
            for seq in text_attention_masks
        ])
        
        max_lyric_length = max(len(seq) for seq in lyric_token_idss)
        padded_lyric_token_idss = torch.stack([
            torch.nn.functional.pad(
                seq, (0, max_lyric_length - len(seq)), 'constant',
                self.text_tokenizer.pad_token_id
            )
            for seq in lyric_token_idss
        ])
        
        padded_lyric_attention_masks = torch.stack([
            torch.nn.functional.pad(
                seq, (0, max_lyric_length - len(seq)), 'constant', 0
            )
            for seq in lyric_attention_masks
        ])

        padded_non_cover_text_input_ids = None
        padded_non_cover_text_attention_masks = None
        if audio_cover_strength < 1.0:
            non_cover_text_input_ids = []
            non_cover_text_attention_masks = []
            for i in range(batch_size):
                # Use custom instruction for this batch item
                instruction = "Fill the audio semantic mask based on the given conditions:"
                
                # Format text prompt with custom instruction
                text_prompt = SFT_GEN_PROMPT.format(instruction, captions[i], parsed_metas[i])
                
                # Tokenize text
                text_inputs_dict = self.text_tokenizer(
                    text_prompt,
                    padding="longest",
                    truncation=True,
                    max_length=256,
                    return_tensors="pt",
                )
                text_token_ids = text_inputs_dict.input_ids[0]
                non_cover_text_attention_mask = text_inputs_dict.attention_mask[0].bool()
                non_cover_text_input_ids.append(text_token_ids)
                non_cover_text_attention_masks.append(non_cover_text_attention_mask)
            
            padded_non_cover_text_input_ids = torch.stack([
                torch.nn.functional.pad(
                    seq, (0, max_text_length - len(seq)), 'constant',
                    self.text_tokenizer.pad_token_id
                )
                for seq in non_cover_text_input_ids
            ])
            padded_non_cover_text_attention_masks = torch.stack([
                torch.nn.functional.pad(
                    seq, (0, max_text_length - len(seq)), 'constant', 0
                )
                for seq in non_cover_text_attention_masks
            ])
        
        if audio_cover_strength < 1.0:
            assert padded_non_cover_text_input_ids is not None, "When audio_cover_strength < 1.0, padded_non_cover_text_input_ids must not be None"
            assert padded_non_cover_text_attention_masks is not None, "When audio_cover_strength < 1.0, padded_non_cover_text_attention_masks must not be None"
        # Prepare batch
        batch = {
            "keys": keys,
            "target_wavs": target_wavs.to(self.device),
            "refer_audioss": refer_audios,
            "wav_lengths": wav_lengths.to(self.device),
            "captions": captions,
            "lyrics": lyrics,
            "metas": parsed_metas,
            "vocal_languages": vocal_languages,
            "target_latents": target_latents,
            "src_latents": src_latents,
            "latent_masks": latent_masks,
            "chunk_masks": chunk_masks,
            "spans": spans,
            "text_inputs": text_inputs,
            "text_token_idss": padded_text_token_idss,
            "text_attention_masks": padded_text_attention_masks,
            "lyric_token_idss": padded_lyric_token_idss,
            "lyric_attention_masks": padded_lyric_attention_masks,
            "is_covers": is_covers,
            "precomputed_lm_hints_25Hz": precomputed_lm_hints_25Hz,
            "non_cover_text_input_ids": padded_non_cover_text_input_ids,
            "non_cover_text_attention_masks": padded_non_cover_text_attention_masks,
        }
        # to device
        for k, v in batch.items():
            if isinstance(v, torch.Tensor):
                batch[k] = v.to(self.device)
                if torch.is_floating_point(v):
                    batch[k] = v.to(self.dtype)
        return batch
    
    def infer_refer_latent(self, refer_audioss):
        refer_audio_order_mask = []
        refer_audio_latents = []

        def _normalize_audio_2d(a: torch.Tensor) -> torch.Tensor:
            """Normalize audio tensor to [2, T] on current device."""
            if not isinstance(a, torch.Tensor):
                raise TypeError(f"refer_audio must be a torch.Tensor, got {type(a)!r}")
            # Accept [T], [1, T], [2, T], [1, 2, T]
            if a.dim() == 3 and a.shape[0] == 1:
                a = a.squeeze(0)
            if a.dim() == 1:
                a = a.unsqueeze(0)
            if a.dim() != 2:
                raise ValueError(f"refer_audio must be 1D/2D/3D(1,2,T); got shape={tuple(a.shape)}")
            if a.shape[0] == 1:
                a = torch.cat([a, a], dim=0)
            a = a[:2]
            return a

        def _ensure_latent_3d(z: torch.Tensor) -> torch.Tensor:
            """Ensure latent is [N, T, D] (3D) for packing."""
            if z.dim() == 4 and z.shape[0] == 1:
                z = z.squeeze(0)
            if z.dim() == 2:
                z = z.unsqueeze(0)
            return z

        for batch_idx, refer_audios in enumerate(refer_audioss):
            if len(refer_audios) == 1 and torch.all(refer_audios[0] == 0.0):
                refer_audio_latent = _ensure_latent_3d(self.silence_latent[:, :750, :])
                refer_audio_latents.append(refer_audio_latent)
                refer_audio_order_mask.append(batch_idx)
            else:
                for refer_audio in refer_audios:
                    refer_audio = _normalize_audio_2d(refer_audio)
                    # Ensure input is in VAE's dtype
                    vae_input = refer_audio.unsqueeze(0).to(self.vae.dtype)
                    refer_audio_latent = self.vae.encode(vae_input).latent_dist.sample()
                    # Cast back to model dtype
                    refer_audio_latent = refer_audio_latent.to(self.dtype)
                    refer_audio_latents.append(_ensure_latent_3d(refer_audio_latent.transpose(1, 2)))
                    refer_audio_order_mask.append(batch_idx)

        refer_audio_latents = torch.cat(refer_audio_latents, dim=0)
        refer_audio_order_mask = torch.tensor(refer_audio_order_mask, device=self.device, dtype=torch.long)
        return refer_audio_latents, refer_audio_order_mask

    def infer_text_embeddings(self, text_token_idss):
        with torch.no_grad():
            text_embeddings = self.text_encoder(input_ids=text_token_idss, lyric_attention_mask=None).last_hidden_state
        return text_embeddings

    def infer_lyric_embeddings(self, lyric_token_ids):
        with torch.no_grad():
            lyric_embeddings = self.text_encoder.embed_tokens(lyric_token_ids)
        return lyric_embeddings

    def preprocess_batch(self, batch):

        # step 1: VAE encode latents, target_latents: N x T x d
        # target_latents: N x T x d
        target_latents = batch["target_latents"]
        src_latents = batch["src_latents"]
        attention_mask = batch["latent_masks"]
        audio_codes = batch.get("audio_codes", None)
        audio_attention_mask = attention_mask

        dtype = target_latents.dtype
        bs = target_latents.shape[0]
        device = target_latents.device

        # step 2: refer_audio timbre
        keys = batch["keys"]
        with self._load_model_context("vae"):
            refer_audio_acoustic_hidden_states_packed, refer_audio_order_mask = self.infer_refer_latent(batch["refer_audioss"])
        if refer_audio_acoustic_hidden_states_packed.dtype != dtype:
            refer_audio_acoustic_hidden_states_packed = refer_audio_acoustic_hidden_states_packed.to(dtype)

        # step 4: chunk mask, N x T x d
        chunk_mask = batch["chunk_masks"]
        chunk_mask = chunk_mask.to(device).unsqueeze(-1).repeat(1, 1, target_latents.shape[2])

        spans = batch["spans"]
        
        text_token_idss = batch["text_token_idss"]
        text_attention_mask = batch["text_attention_masks"]
        lyric_token_idss = batch["lyric_token_idss"]
        lyric_attention_mask = batch["lyric_attention_masks"]
        text_inputs = batch["text_inputs"]

        logger.info("[preprocess_batch] Inferring prompt embeddings...")
        with self._load_model_context("text_encoder"):
            text_hidden_states = self.infer_text_embeddings(text_token_idss)
            logger.info("[preprocess_batch] Inferring lyric embeddings...")
            lyric_hidden_states = self.infer_lyric_embeddings(lyric_token_idss)

            is_covers = batch["is_covers"]
            
            # Get precomputed hints from batch if available
            precomputed_lm_hints_25Hz = batch.get("precomputed_lm_hints_25Hz", None)
            
            # Get non-cover text input ids and attention masks from batch if available
            non_cover_text_input_ids = batch.get("non_cover_text_input_ids", None)
            non_cover_text_attention_masks = batch.get("non_cover_text_attention_masks", None)
            non_cover_text_hidden_states = None
            if non_cover_text_input_ids is not None:
                logger.info("[preprocess_batch] Inferring non-cover text embeddings...")
                non_cover_text_hidden_states = self.infer_text_embeddings(non_cover_text_input_ids)

        return (
            keys,
            text_inputs,
            src_latents,
            target_latents,
            # model inputs
            text_hidden_states,
            text_attention_mask,
            lyric_hidden_states,
            lyric_attention_mask,
            audio_attention_mask,
            refer_audio_acoustic_hidden_states_packed,
            refer_audio_order_mask,
            chunk_mask,
            spans,
            is_covers,
            audio_codes,
            lyric_token_idss,
            precomputed_lm_hints_25Hz,
            non_cover_text_hidden_states,
            non_cover_text_attention_masks,
        )
    
    @torch.no_grad()
    def service_generate(
        self,
        captions: Union[str, List[str]],
        lyrics: Union[str, List[str]],
        keys: Optional[Union[str, List[str]]] = None,
        target_wavs: Optional[torch.Tensor] = None,
        refer_audios: Optional[List[List[torch.Tensor]]] = None,
        metas: Optional[Union[str, Dict[str, Any], List[Union[str, Dict[str, Any]]]]] = None,
        vocal_languages: Optional[Union[str, List[str]]] = None,
        infer_steps: int = 60,
        guidance_scale: float = 7.0,
        seed: Optional[Union[int, List[int]]] = None,
        return_intermediate: bool = False,
        repainting_start: Optional[Union[float, List[float]]] = None,
        repainting_end: Optional[Union[float, List[float]]] = None,
        instructions: Optional[Union[str, List[str]]] = None,
        audio_cover_strength: float = 1.0,
        use_adg: bool = False,
        cfg_interval_start: float = 0.0,
        cfg_interval_end: float = 1.0,
        audio_code_hints: Optional[Union[str, List[str]]] = None,
        infer_method: str = "ode",
    ) -> Dict[str, Any]:

        """
        Generate music from text inputs.
        
        Args:
            captions: Text caption(s) describing the music (optional, can be empty strings)
            lyrics: Lyric text(s) (optional, can be empty strings)
            keys: Unique identifier(s) (optional)
            target_wavs: Target audio tensor(s) for conditioning (optional)
            refer_audios: Reference audio tensor(s) for style transfer (optional)
            metas: Metadata dict(s) or string(s) (optional)
            vocal_languages: Language code(s) for lyrics (optional, defaults to 'en')
            infer_steps: Number of inference steps (default: 60)
            guidance_scale: Guidance scale for generation (default: 7.0)
            seed: Random seed (optional)
            return_intermediate: Whether to return intermediate results (default: False)
            repainting_start: Start time(s) for repainting region in seconds (optional)
            repainting_end: End time(s) for repainting region in seconds (optional)
            instructions: Instruction text(s) for generation (optional)
            audio_cover_strength: Strength of audio cover mode (default: 1.0)
            use_adg: Whether to use ADG (Adaptive Diffusion Guidance) (default: False)
            cfg_interval_start: Start of CFG interval (0.0-1.0, default: 0.0)
            cfg_interval_end: End of CFG interval (0.0-1.0, default: 1.0)
            
        Returns:
            Dictionary containing:
            - pred_wavs: Generated audio tensors
            - target_wavs: Input target audio (if provided)
            - vqvae_recon_wavs: VAE reconstruction of target
            - keys: Identifiers used
            - text_inputs: Formatted text inputs
            - sr: Sample rate
            - spans: Generation spans
            - time_costs: Timing information
            - seed_num: Seed used
        """
        if self.config.is_turbo:
            # Limit inference steps to maximum 8
            if infer_steps > 8:
                logger.warning(f"dmd_gan version: infer_steps {infer_steps} exceeds maximum 8, clamping to 8")
                infer_steps = 8
            # CFG parameters are not adjustable for dmd_gan (they will be ignored)
            # Note: guidance_scale, cfg_interval_start, cfg_interval_end are still passed but may be ignored by the model
        
        # Convert single inputs to lists
        if isinstance(captions, str):
            captions = [captions]
        if isinstance(lyrics, str):
            lyrics = [lyrics]
        if isinstance(keys, str):
            keys = [keys]
        if isinstance(vocal_languages, str):
            vocal_languages = [vocal_languages]
        if isinstance(metas, (str, dict)):
            metas = [metas]
            
        # Convert repainting parameters to lists
        if isinstance(repainting_start, (int, float)):
            repainting_start = [repainting_start]
        if isinstance(repainting_end, (int, float)):
            repainting_end = [repainting_end]
        
        # Convert instructions to list
        if isinstance(instructions, str):
            instructions = [instructions]
        elif instructions is None:
            instructions = None
        
        # Convert audio_code_hints to list
        if isinstance(audio_code_hints, str):
            audio_code_hints = [audio_code_hints]
        elif audio_code_hints is None:
            audio_code_hints = None

        # Get batch size from captions
        batch_size = len(captions)

        # Ensure audio_code_hints matches batch size
        if audio_code_hints is not None:
            if len(audio_code_hints) != batch_size:
                if len(audio_code_hints) == 1:
                    audio_code_hints = audio_code_hints * batch_size
                else:
                    audio_code_hints = audio_code_hints[:batch_size]
                    while len(audio_code_hints) < batch_size:
                        audio_code_hints.append(None)
        
        # Convert seed to list format
        if seed is None:
            seed_list = None
        elif isinstance(seed, list):
            seed_list = seed
            # Ensure we have enough seeds for batch size
            if len(seed_list) < batch_size:
                # Pad with last seed or random seeds
                import random
                while len(seed_list) < batch_size:
                    seed_list.append(random.randint(0, 2**32 - 1))
            elif len(seed_list) > batch_size:
                # Truncate to batch size
                seed_list = seed_list[:batch_size]
        else:
            # Single seed value - use for all batch items
            seed_list = [int(seed)] * batch_size

        # Don't set global random seed here - each item will use its own seed
        
        # Prepare batch
        batch = self._prepare_batch(
            captions=captions,
            lyrics=lyrics,
            keys=keys,
            target_wavs=target_wavs,
            refer_audios=refer_audios,
            metas=metas,
            vocal_languages=vocal_languages,
            repainting_start=repainting_start,
            repainting_end=repainting_end,
            instructions=instructions,
            audio_code_hints=audio_code_hints,
            audio_cover_strength=audio_cover_strength,
        )
        
        processed_data = self.preprocess_batch(batch)
        
        (
            keys,
            text_inputs,
            src_latents,
            target_latents,
            # model inputs
            text_hidden_states,
            text_attention_mask,
            lyric_hidden_states,
            lyric_attention_mask,
            audio_attention_mask,
            refer_audio_acoustic_hidden_states_packed,
            refer_audio_order_mask,
            chunk_mask,
            spans,
            is_covers,
            audio_codes,
            lyric_token_idss,
            precomputed_lm_hints_25Hz,
            non_cover_text_hidden_states,
            non_cover_text_attention_masks,
        ) = processed_data

        # Set generation parameters
        # Use seed_list if available, otherwise generate a single seed
        if seed_list is not None:
            # Pass seed list to model (will be handled there)
            seed_param = seed_list
        else:
            seed_param = random.randint(0, 2**32 - 1)
        
        generate_kwargs = {
            "text_hidden_states": text_hidden_states,
            "text_attention_mask": text_attention_mask,
            "lyric_hidden_states": lyric_hidden_states,
            "lyric_attention_mask": lyric_attention_mask,
            "refer_audio_acoustic_hidden_states_packed": refer_audio_acoustic_hidden_states_packed,
            "refer_audio_order_mask": refer_audio_order_mask,
            "src_latents": src_latents,
            "chunk_masks": chunk_mask,
            "is_covers": is_covers,
            "silence_latent": self.silence_latent,
            "seed": seed_param,
            "non_cover_text_hidden_states": non_cover_text_hidden_states,
            "non_cover_text_attention_mask": non_cover_text_attention_masks,
            "precomputed_lm_hints_25Hz": precomputed_lm_hints_25Hz,
            "audio_cover_strength": audio_cover_strength,
            "infer_method": infer_method,
            "infer_steps": infer_steps,
            "diffusion_guidance_sale": guidance_scale,
            "use_adg": use_adg,
            "cfg_interval_start": cfg_interval_start,
            "cfg_interval_end": cfg_interval_end,
        }
        logger.info("[service_generate] Generating audio...")
        with self._load_model_context("model"):
            outputs = self.model.generate_audio(**generate_kwargs)
        
        outputs['actural_texts'] = text_inputs
        return outputs

    def tiled_decode(self, latents, chunk_size=512, overlap=64):
        """
        Decode latents using tiling to reduce VRAM usage.
        Uses overlap-discard strategy to avoid boundary artifacts.
        
        Args:
            latents: [Batch, Channels, Length]
            chunk_size: Size of latent chunk to process at once
            overlap: Overlap size in latent frames
        """
        B, C, T = latents.shape
        
        # If short enough, decode directly
        if T <= chunk_size:
            return self.vae.decode(latents).sample

        # Calculate stride (core size)
        stride = chunk_size - 2 * overlap
        if stride <= 0:
            raise ValueError(f"chunk_size {chunk_size} must be > 2 * overlap {overlap}")
            
        decoded_audio_list = []
        
        # We need to determine upsample factor to trim audio correctly
        upsample_factor = None
        
        num_steps = math.ceil(T / stride)
        
        for i in tqdm(range(num_steps), desc="Decoding audio chunks"):
            # Core range in latents
            core_start = i * stride
            core_end = min(core_start + stride, T)
            
            # Window range (with overlap)
            win_start = max(0, core_start - overlap)
            win_end = min(T, core_end + overlap)
            
            # Extract chunk
            latent_chunk = latents[:, :, win_start:win_end]
            
            # Decode
            # [Batch, Channels, AudioSamples]
            audio_chunk = self.vae.decode(latent_chunk).sample
            
            # Determine upsample factor from the first chunk
            if upsample_factor is None:
                upsample_factor = audio_chunk.shape[-1] / latent_chunk.shape[-1]
            
            # Calculate trim amounts in audio samples
            # How much overlap was added at the start?
            added_start = core_start - win_start # latent frames
            trim_start = int(round(added_start * upsample_factor))
            
            # How much overlap was added at the end?
            added_end = win_end - core_end # latent frames
            trim_end = int(round(added_end * upsample_factor))
            
            # Trim audio
            audio_len = audio_chunk.shape[-1]
            end_idx = audio_len - trim_end
            
            audio_core = audio_chunk[:, :, trim_start:end_idx]
            decoded_audio_list.append(audio_core)
            
        # Concatenate
        final_audio = torch.cat(decoded_audio_list, dim=-1)
        return final_audio

    def generate_music(
        self,
        captions: str,
        lyrics: str,
        bpm: Optional[int] = None,
        key_scale: str = "",
        time_signature: str = "",
        vocal_language: str = "en",
        inference_steps: int = 8,
        guidance_scale: float = 7.0,
        use_random_seed: bool = True,
        seed: Optional[Union[str, float, int]] = -1,
        reference_audio=None,
        audio_duration: Optional[float] = None,
        batch_size: Optional[int] = None,
        src_audio=None,
        audio_code_string: Union[str, List[str]] = "",
        repainting_start: float = 0.0,
        repainting_end: Optional[float] = None,
        instruction: str = "Fill the audio semantic mask based on the given conditions:",
        audio_cover_strength: float = 1.0,
        task_type: str = "text2music",
        use_adg: bool = False,
        cfg_interval_start: float = 0.0,
        cfg_interval_end: float = 1.0,
        audio_format: str = "mp3",
        lm_temperature: float = 0.6,
        use_tiled_decode: bool = True,
        progress=None
    ) -> Tuple[Optional[str], Optional[str], List[str], str, str, str, str, str, Optional[Any], str, str, Optional[Any]]:
        """
        Main interface for music generation
        
        Returns:
            (first_audio, second_audio, all_audio_paths, generation_info, status_message, 
             seed_value_for_ui, align_score_1, align_text_1, align_plot_1, 
             align_score_2, align_text_2, align_plot_2)
        """
        if progress is None:
            def progress(*args, **kwargs):
                pass

        if self.model is None or self.vae is None or self.text_tokenizer is None or self.text_encoder is None:
            return None, None, [], "", "❌ Model not fully initialized. Please initialize all components first.", "-1", "", "", None, "", "", None

        def _has_audio_codes(v: Union[str, List[str]]) -> bool:
            if isinstance(v, list):
                return any((x or "").strip() for x in v)
            return bool(v and str(v).strip())

        # Auto-detect task type based on audio_code_string
        # If audio_code_string is provided and not empty, use cover task
        # Otherwise, use text2music task (or keep current task_type if not text2music)
        if task_type == "text2music":
            if _has_audio_codes(audio_code_string):
                # User has provided audio codes, switch to cover task
                task_type = "cover"
                # Update instruction for cover task
                instruction = "Generate audio semantic tokens based on the given conditions:"

        logger.info("[generate_music] Starting generation...")
        if progress:
            progress(0.05, desc="Preparing inputs...")
        logger.info("[generate_music] Preparing inputs...")
        
        # Reset offload cost
        self.current_offload_cost = 0.0

        # Caption and lyrics are optional - can be empty
        # Use provided batch_size or default
        actual_batch_size = batch_size if batch_size is not None else self.batch_size
        actual_batch_size = max(1, actual_batch_size)  # Ensure at least 1

        actual_seed_list, seed_value_for_ui = self.prepare_seeds(actual_batch_size, seed, use_random_seed)
        
        # Convert special values to None
        if audio_duration is not None and audio_duration <= 0:
            audio_duration = None
        # if seed is not None and seed < 0:
        #     seed = None
        if repainting_end is not None and repainting_end < 0:
            repainting_end = None
            
        try:
            progress(0.1, desc="Preparing inputs...")

            # 1. Process reference audio
            refer_audios = None
            if reference_audio is not None:
                logger.info("[generate_music] Processing reference audio...")
                processed_ref_audio = self.process_reference_audio(reference_audio)
                if processed_ref_audio is not None:
                    # Convert to the format expected by the service: List[List[torch.Tensor]]
                    # Each batch item has a list of reference audios
                    refer_audios = [[processed_ref_audio] for _ in range(actual_batch_size)]
            else:
                refer_audios = [[torch.zeros(2, 30*self.sample_rate)] for _ in range(actual_batch_size)]
            
            # 2. Process source audio
            # If audio_code_string is provided, ignore src_audio and use codes instead
            processed_src_audio = None
            if src_audio is not None:
                # Check if audio codes are provided - if so, ignore src_audio
                if _has_audio_codes(audio_code_string):
                    logger.info("[generate_music] Audio codes provided, ignoring src_audio and using codes instead")
                else:
                    logger.info("[generate_music] Processing source audio...")
                    processed_src_audio = self.process_src_audio(src_audio)
                
            # 3. Prepare batch data
            captions_batch, instructions_batch, lyrics_batch, vocal_languages_batch, metas_batch = self.prepare_batch_data(
                actual_batch_size,
                processed_src_audio,
                audio_duration,
                captions,
                lyrics,
                vocal_language,
                instruction,
                bpm,
                key_scale,
                time_signature
            )
            
            is_repaint_task, is_lego_task, is_cover_task, can_use_repainting = self.determine_task_type(task_type, audio_code_string)
            
            repainting_start_batch, repainting_end_batch, target_wavs_tensor = self.prepare_padding_info(
                actual_batch_size,
                processed_src_audio,
                audio_duration,
                repainting_start,
                repainting_end,
                is_repaint_task,
                is_lego_task,
                is_cover_task,
                can_use_repainting
            )
            
            progress(0.3, desc=f"Generating music (batch size: {actual_batch_size})...")
            
            # Prepare audio_code_hints - use if audio_code_string is provided
            # This works for both text2music (auto-switched to cover) and cover tasks
            audio_code_hints_batch = None
            if _has_audio_codes(audio_code_string):
                if isinstance(audio_code_string, list):
                    audio_code_hints_batch = audio_code_string
                else:
                    audio_code_hints_batch = [audio_code_string] * actual_batch_size

            should_return_intermediate = (task_type == "text2music")
            outputs = self.service_generate(
                captions=captions_batch,
                lyrics=lyrics_batch,
                metas=metas_batch,  # Pass as dict, service will convert to string
                vocal_languages=vocal_languages_batch,
                refer_audios=refer_audios,  # Already in List[List[torch.Tensor]] format
                target_wavs=target_wavs_tensor,  # Shape: [batch_size, 2, frames]
                infer_steps=inference_steps,
                guidance_scale=guidance_scale,
                seed=actual_seed_list,  # Pass list of seeds, one per batch item
                repainting_start=repainting_start_batch,
                repainting_end=repainting_end_batch,
                instructions=instructions_batch,  # Pass instructions to service
                audio_cover_strength=audio_cover_strength,  # Pass audio cover strength
                use_adg=use_adg,  # Pass use_adg parameter
                cfg_interval_start=cfg_interval_start,  # Pass CFG interval start
                cfg_interval_end=cfg_interval_end,  # Pass CFG interval end
                audio_code_hints=audio_code_hints_batch,  # Pass audio code hints as list
                return_intermediate=should_return_intermediate
            )
            
            logger.info("[generate_music] Model generation completed. Decoding latents...")
            actural_texts = outputs["actural_texts"]
            pred_latents = outputs["target_latents"]  # [batch, latent_length, latent_dim]
            time_costs = outputs["time_costs"]
            time_costs["offload_time_cost"] = self.current_offload_cost
            logger.info(f"  - pred_latents: {pred_latents.shape}, dtype={pred_latents.dtype} {pred_latents.min()=}, {pred_latents.max()=}, {pred_latents.mean()=} {pred_latents.std()=}")
            logger.info(f"  - time_costs: {time_costs}")
            if progress:
                progress(0.8, desc="Decoding audio...")
            logger.info("[generate_music] Decoding latents with VAE...")
            
            # Decode latents to audio
            start_time = time.time()
            with torch.no_grad():
                with self._load_model_context("vae"):
                    # Transpose for VAE decode: [batch, latent_length, latent_dim] -> [batch, latent_dim, latent_length]
                    pred_latents_for_decode = pred_latents.transpose(1, 2)
                    # Ensure input is in VAE's dtype
                    pred_latents_for_decode = pred_latents_for_decode.to(self.vae.dtype)
                    
                    if use_tiled_decode:
                        logger.info("[generate_music] Using tiled VAE decode to reduce VRAM usage...")
                        pred_wavs = self.tiled_decode(pred_latents_for_decode)  # [batch, channels, samples]
                    else:
                        pred_wavs = self.vae.decode(pred_latents_for_decode).sample
                    
                    # Cast output to float32 for audio processing/saving
                    pred_wavs = pred_wavs.to(torch.float32)
            end_time = time.time()
            time_costs["vae_decode_time_cost"] = end_time - start_time
            time_costs["total_time_cost"] = time_costs["total_time_cost"] + time_costs["vae_decode_time_cost"]
            
            # Update offload cost one last time to include VAE offloading
            time_costs["offload_time_cost"] = self.current_offload_cost
            
            logger.info("[generate_music] VAE decode completed. Saving audio files...")
            if progress:
                progress(0.9, desc="Saving audio files...")
            
            # Save audio files using soundfile (supports wav, flac, mp3 via format param)
            audio_format_lower = audio_format.lower() if audio_format else "wav"
            if audio_format_lower not in ["wav", "flac", "mp3"]:
                audio_format_lower = "wav"
            
            saved_files = []
            for i in range(actual_batch_size):
                audio_file = os.path.join(self.temp_dir, f"generated_{i}_{actual_seed_list[i]}.{audio_format_lower}")
                # Convert to numpy: [channels, samples] -> [samples, channels]
                audio_np = pred_wavs[i].cpu().float().numpy().T
                sf.write(audio_file, audio_np, self.sample_rate)
                saved_files.append(audio_file)
            
            # Prepare return values
            first_audio = saved_files[0] if len(saved_files) > 0 else None
            second_audio = saved_files[1] if len(saved_files) > 1 else None
            
            # Format time costs if available
            time_costs_str = ""
            if time_costs:
                if isinstance(time_costs, dict):
                    time_costs_str = "\n\n**⏱️ Time Costs:**\n"
                    for key, value in time_costs.items():
                        # Format key: encoder_time_cost -> Encoder
                        formatted_key = key.replace("_time_cost", "").replace("_", " ").title()
                        time_costs_str += f"  - {formatted_key}: {value:.2f}s\n"
                elif isinstance(time_costs, (int, float)):
                    time_costs_str = f"\n\n**⏱️ Time Cost:** {time_costs:.2f}s"
            
            generation_info = f"""**🎵 Generation Complete**

    **Seeds:** {seed_value_for_ui}
    **Steps:** {inference_steps}
    **Files:** {len(saved_files)} audio(s){time_costs_str}"""
            status_message = f"✅ Generation completed successfully!"
            logger.info(f"[generate_music] Done! Generated {len(saved_files)} audio files.")
            
            # Alignment scores and plots (placeholder for now)
            align_score_1 = ""
            align_text_1 = ""
            align_plot_1 = None
            align_score_2 = ""
            align_text_2 = ""
            align_plot_2 = None
            
            return (
                first_audio,
                second_audio,
                saved_files,
                generation_info,
                status_message,
                seed_value_for_ui,
                actural_texts,
                align_score_1,
                align_text_1,
                align_plot_1,
                align_score_2,
                align_text_2,
                align_plot_2,
            )

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}\n{traceback.format_exc()}"
            return None, None, [], "", error_msg, seed_value_for_ui, "", "", None, "", "", None

