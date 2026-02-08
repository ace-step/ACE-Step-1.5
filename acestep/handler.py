"""
Business Logic Handler
Encapsulates all data processing and business logic as a bridge between model and UI
"""
import os

# Disable tokenizers parallelism to avoid fork warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import math
from copy import deepcopy
import tempfile
import traceback
import re
import random
import uuid
import hashlib
import json
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
from acestep.model_downloader import (
    ensure_main_model,
    ensure_dit_model,
    check_main_model_exists,
    check_model_exists,
    get_checkpoints_dir,
)
from acestep.constants import (
    TASK_INSTRUCTIONS,
    SFT_GEN_PROMPT,
    DEFAULT_DIT_INSTRUCTION,
)
from acestep.dit_alignment_score import MusicStampsAligner, MusicLyricScorer
from acestep.gpu_config import get_gpu_memory_gb, get_global_gpu_config


warnings.filterwarnings("ignore")


class AceStepHandler:
    """ACE-Step Business Logic Handler"""
    
    def __init__(self):
        self.model = None
        self.config = None
        self.device = "cpu"
        self.dtype = torch.float32  # Will be set based on device in initialize_service

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
        self.custom_layers_config = {2: [6], 3: [10, 11], 4: [3], 5: [8, 9], 6: [8]}
        self.offload_to_cpu = False
        self.offload_dit_to_cpu = False
        self.compiled = False
        self.current_offload_cost = 0.0
        self.last_init_params = None
        
        # LoRA state
        self.lora_loaded = False
        self.use_lora = False
        self.lora_scale = 1.0  # LoRA influence scale (0-1)
        self._base_decoder = None  # Backup of original decoder
    
    def get_available_checkpoints(self) -> str:
        """Return project root directory path"""
        # Get project root (handler.py is in acestep/, so go up two levels to project root)
        project_root = self._get_project_root()
        # default checkpoints
        checkpoint_dir = os.path.join(project_root, "checkpoints")
        if os.path.exists(checkpoint_dir):
            return [checkpoint_dir]
        else:
            return []
    
    def get_available_acestep_v15_models(self) -> List[str]:
        """Scan and return all model directory names starting with 'acestep-v15-'"""
        # Get project root
        project_root = self._get_project_root()
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
    
    def is_turbo_model(self) -> bool:
        """Check if the currently loaded model is a turbo model"""
        if self.config is None:
            return False
        return getattr(self.config, 'is_turbo', False)
    
    def load_lora(self, lora_path: str) -> str:
        """Load LoRA adapter into the decoder.
        
        Args:
            lora_path: Path to the LoRA adapter directory (containing adapter_config.json)
            
        Returns:
            Status message
        """
        if self.model is None:
            return "❌ Model not initialized. Please initialize service first."
        
        if not lora_path or not lora_path.strip():
            return "❌ Please provide a LoRA path."
        
        lora_path = lora_path.strip()
        
        # Check if path exists
        if not os.path.exists(lora_path):
            return f"❌ LoRA path not found: {lora_path}"
        
        # Check if it's a valid PEFT adapter directory
        config_file = os.path.join(lora_path, "adapter_config.json")
        if not os.path.exists(config_file):
            return f"❌ Invalid LoRA adapter: adapter_config.json not found in {lora_path}"
        
        try:
            from peft import PeftModel, PeftConfig
        except ImportError:
            return "❌ PEFT library not installed. Please install with: pip install peft"
        
        try:
            import copy
            # Backup base decoder if not already backed up
            if self._base_decoder is None:
                self._base_decoder = copy.deepcopy(self.model.decoder)
                logger.info("Base decoder backed up")
            else:
                # Restore base decoder before loading new LoRA
                self.model.decoder = copy.deepcopy(self._base_decoder)
                logger.info("Restored base decoder before loading new LoRA")
            
            # Load PEFT adapter
            logger.info(f"Loading LoRA adapter from {lora_path}")
            self.model.decoder = PeftModel.from_pretrained(
                self.model.decoder,
                lora_path,
                is_trainable=False,
            )
            self.model.decoder = self.model.decoder.to(self.device).to(self.dtype)
            self.model.decoder.eval()
            
            self.lora_loaded = True
            self.use_lora = True  # Enable LoRA by default after loading
            
            logger.info(f"LoRA adapter loaded successfully from {lora_path}")
            return f"✅ LoRA loaded from {lora_path}"
            
        except Exception as e:
            logger.exception("Failed to load LoRA adapter")
            return f"❌ Failed to load LoRA: {str(e)}"
    
    def unload_lora(self) -> str:
        """Unload LoRA adapter and restore base decoder.
        
        Returns:
            Status message
        """
        if not self.lora_loaded:
            return "⚠️ No LoRA adapter loaded."
        
        if self._base_decoder is None:
            return "❌ Base decoder backup not found. Cannot restore."
        
        try:
            import copy
            # Restore base decoder
            self.model.decoder = copy.deepcopy(self._base_decoder)
            self.model.decoder = self.model.decoder.to(self.device).to(self.dtype)
            self.model.decoder.eval()
            
            self.lora_loaded = False
            self.use_lora = False
            self.lora_scale = 1.0  # Reset scale to default
            
            logger.info("LoRA unloaded, base decoder restored")
            return "✅ LoRA unloaded, using base model"
            
        except Exception as e:
            logger.exception("Failed to unload LoRA")
            return f"❌ Failed to unload LoRA: {str(e)}"
    
    def set_use_lora(self, use_lora: bool) -> str:
        """Toggle LoRA usage for inference.
        
        Args:
            use_lora: Whether to use LoRA adapter
            
        Returns:
            Status message
        """
        if use_lora and not self.lora_loaded:
            return "❌ No LoRA adapter loaded. Please load a LoRA first."
        
        self.use_lora = use_lora
        
        # Use PEFT's enable/disable methods if available
        if self.lora_loaded and hasattr(self.model.decoder, 'disable_adapter_layers'):
            try:
                if use_lora:
                    self.model.decoder.enable_adapter_layers()
                    logger.info("LoRA adapter enabled")
                else:
                    self.model.decoder.disable_adapter_layers()
                    logger.info("LoRA adapter disabled")
            except Exception as e:
                logger.warning(f"Could not toggle adapter layers: {e}")
        
        status = "enabled" if use_lora else "disabled"
        return f"✅ LoRA {status}"
    
    def set_lora_scale(self, scale: float) -> str:
        """Set LoRA adapter scale/weight (0-1 range).
        
        Args:
            scale: LoRA influence scale (0=disabled, 1=full effect)
            
        Returns:
            Status message
        """
        if not self.lora_loaded:
            return "⚠️ No LoRA loaded"
        
        # Clamp scale to 0-1 range
        self.lora_scale = max(0.0, min(1.0, scale))
        
        # Iterate through all LoRA layers and set their scaling
        try:
            for name, module in self.model.decoder.named_modules():
                if hasattr(module, 'scaling'):
                    scaling = module.scaling
                    # Handle dict-style scaling (adapter_name -> value)
                    if isinstance(scaling, dict):
                        # Save original scaling on first call
                        if not hasattr(module, '_original_scaling'):
                            module._original_scaling = {k: v for k, v in scaling.items()}
                        # Apply new scale
                        for adapter_name in scaling:
                            module.scaling[adapter_name] = module._original_scaling[adapter_name] * self.lora_scale
                    # Handle float-style scaling (single value)
                    elif isinstance(scaling, (int, float)):
                        if not hasattr(module, '_original_scaling'):
                            module._original_scaling = scaling
                        module.scaling = module._original_scaling * self.lora_scale
            
            logger.info(f"LoRA scale set to {self.lora_scale:.2f}")
            return f"✅ LoRA scale: {self.lora_scale:.2f}"
        except Exception as e:
            logger.warning(f"Could not set LoRA scale: {e}")
            return f"⚠️ Scale set to {self.lora_scale:.2f} (partial)"
    
    def get_lora_status(self) -> Dict[str, Any]:
        """Get current LoRA status.
        
        Returns:
            Dictionary with LoRA status info
        """
        return {
            "loaded": self.lora_loaded,
            "active": self.use_lora,
            "scale": self.lora_scale,
        }
    
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
        prefer_source: Optional[str] = None,
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
            prefer_source: Preferred download source ("huggingface", "modelscope", or None for auto-detect)

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
            self.compiled = compile_model
            # Set dtype based on device: bfloat16 for cuda/xpu/mps, float32 for cpu
            # Models are trained in bfloat16; MPS supports bfloat16 natively since PyTorch 2.3+
            if device in ["cuda", "xpu", "mps"]:
                self.dtype = torch.bfloat16
            else:
                self.dtype = torch.float32
            self.quantization = quantization
            if self.quantization is not None:
                assert compile_model, "Quantization requires compile_model to be True"
                try:
                    import torchao
                except ImportError:
                    raise ImportError("torchao is required for quantization but is not installed. Please install torchao to use quantization features.")
                

            # Auto-detect project root (independent of passed project_root parameter)
            actual_project_root = self._get_project_root()
            checkpoint_dir = os.path.join(actual_project_root, "checkpoints")

            # Auto-download models if not present
            from pathlib import Path
            checkpoint_path = Path(checkpoint_dir)
            
            # Check and download main model components (vae, text_encoder, default DiT)
            if not check_main_model_exists(checkpoint_path):
                logger.info("[initialize_service] Main model not found, starting auto-download...")
                success, msg = ensure_main_model(checkpoint_path, prefer_source=prefer_source)
                if not success:
                    return f"❌ Failed to download main model: {msg}", False
                logger.info(f"[initialize_service] {msg}")

            # Check and download the requested DiT model
            if not check_model_exists(config_path, checkpoint_path):
                logger.info(f"[initialize_service] DiT model '{config_path}' not found, starting auto-download...")
                success, msg = ensure_dit_model(config_path, checkpoint_path, prefer_source=prefer_source)
                if not success:
                    return f"❌ Failed to download DiT model '{config_path}': {msg}", False
                logger.info(f"[initialize_service] {msg}")

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
                    logger.info(f"[initialize_service] Attempting to load model with attention implementation: {attn_implementation}")
                    self.model = AutoModel.from_pretrained(
                        acestep_v15_checkpoint_path, 
                        trust_remote_code=True, 
                        attn_implementation=attn_implementation,
                        dtype="bfloat16"
                    )
                except Exception as e:
                    logger.warning(f"[initialize_service] Failed to load model with {attn_implementation}: {e}")
                    if attn_implementation == "sdpa":
                        logger.info("[initialize_service] Falling back to eager attention")
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
                        logger.info(f"[initialize_service] Keeping main model on {device} (persistent)")
                        self.model = self.model.to(device).to(self.dtype)
                    else:
                        self.model = self.model.to("cpu").to(self.dtype)
                self.model.eval()
                
                if compile_model:
                    # Add __len__ method to model to support torch.compile
                    # torch.compile's dynamo requires this method for introspection
                    # Note: This modifies the model class, affecting all instances
                    if not hasattr(self.model.__class__, '__len__'):
                        def _model_len(model_self):
                            """Return 0 as default length for torch.compile compatibility"""
                            return 0
                        self.model.__class__.__len__ = _model_len
                    
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
                        logger.info(f"[initialize_service] DiT quantized with: {self.quantization}")
                    
                    
                silence_latent_path = os.path.join(acestep_v15_checkpoint_path, "silence_latent.pt")
                if os.path.exists(silence_latent_path):
                    self.silence_latent = torch.load(silence_latent_path, weights_only=True).transpose(1, 2)
                    # Always keep silence_latent on GPU - it's used in many places outside model context
                    # and is small enough that it won't significantly impact VRAM
                    self.silence_latent = self.silence_latent.to(device).to(self.dtype)
                else:
                    raise FileNotFoundError(f"Silence latent not found at {silence_latent_path}")
            else:
                raise FileNotFoundError(f"ACE-Step V1.5 checkpoint not found at {acestep_v15_checkpoint_path}")
            
            # 2. Load VAE
            vae_checkpoint_path = os.path.join(checkpoint_dir, "vae")
            if os.path.exists(vae_checkpoint_path):
                self.vae = AutoencoderOobleck.from_pretrained(vae_checkpoint_path)
                if not self.offload_to_cpu:
                    # Keep VAE in GPU precision when resident on accelerator.
                    vae_dtype = self._get_vae_dtype(device)
                    self.vae = self.vae.to(device).to(vae_dtype)
                else:
                    # Use CPU-appropriate dtype when VAE is offloaded.
                    vae_dtype = self._get_vae_dtype("cpu")
                    self.vae = self.vae.to("cpu").to(vae_dtype)
                self.vae.eval()
            else:
                raise FileNotFoundError(f"VAE checkpoint not found at {vae_checkpoint_path}")

            if compile_model:
                # Add __len__ method to VAE to support torch.compile if needed
                # Note: This modifies the VAE class, affecting all instances
                if not hasattr(self.vae.__class__, '__len__'):
                    def _vae_len(vae_self):
                        """Return 0 as default length for torch.compile compatibility"""
                        return 0
                    self.vae.__class__.__len__ = _vae_len
                
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

            # Persist latest successful init settings for mode switching (e.g. training preset).
            self.last_init_params = {
                "project_root": project_root,
                "config_path": config_path,
                "device": device,
                "use_flash_attention": use_flash_attention,
                "compile_model": compile_model,
                "offload_to_cpu": offload_to_cpu,
                "offload_dit_to_cpu": offload_dit_to_cpu,
                "quantization": quantization,
                "prefer_source": prefer_source,
            }
            
            return status_msg, True
            
        except Exception as e:
            error_msg = f"❌ Error initializing model: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            logger.exception("[initialize_service] Error initializing model")
            return error_msg, False

    def switch_to_training_preset(self) -> Tuple[str, bool]:
        """Best-effort switch to a training-safe preset (non-quantized DiT)."""
        if self.quantization is None:
            return "Already in training-safe preset (quantization disabled).", True

        if not self.last_init_params:
            return "Cannot switch preset automatically: no previous init parameters found.", False

        params = dict(self.last_init_params)
        params["quantization"] = None

        status, ok = self.initialize_service(
            project_root=params["project_root"],
            config_path=params["config_path"],
            device=params["device"],
            use_flash_attention=params["use_flash_attention"],
            compile_model=params["compile_model"],
            offload_to_cpu=params["offload_to_cpu"],
            offload_dit_to_cpu=params["offload_dit_to_cpu"],
            quantization=None,
            prefer_source=params.get("prefer_source"),
        )
        if ok:
            return f"Switched to training preset (quantization disabled).\n{status}", True
        return f"Failed to switch to training preset.\n{status}", False
    
    def _empty_cache(self):
        """Clear accelerator memory cache (CUDA, XPU, or MPS)."""
        device_type = self.device if isinstance(self.device, str) else self.device.type
        if device_type == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
        elif device_type == "xpu" and hasattr(torch, 'xpu') and torch.xpu.is_available():
            torch.xpu.empty_cache()
        elif device_type == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()

    def _synchronize(self):
        """Synchronize accelerator operations (CUDA, XPU, or MPS)."""
        device_type = self.device if isinstance(self.device, str) else self.device.type
        if device_type == "cuda" and torch.cuda.is_available():
            torch.cuda.synchronize()
        elif device_type == "xpu" and hasattr(torch, 'xpu') and torch.xpu.is_available():
            torch.xpu.synchronize()
        elif device_type == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.synchronize()

    def _memory_allocated(self):
        """Get current accelerator memory usage in bytes, or 0 for unsupported backends."""
        device_type = self.device if isinstance(self.device, str) else self.device.type
        if device_type == "cuda" and torch.cuda.is_available():
            return torch.cuda.memory_allocated()
        # MPS and XPU don't expose per-tensor memory tracking
        return 0

    def _max_memory_allocated(self):
        """Get peak accelerator memory usage in bytes, or 0 for unsupported backends."""
        device_type = self.device if isinstance(self.device, str) else self.device.type
        if device_type == "cuda" and torch.cuda.is_available():
            return torch.cuda.max_memory_allocated()
        return 0

    def _is_on_target_device(self, tensor, target_device):
        """Check if tensor is on the target device (handles cuda vs cuda:0 comparison)."""
        if tensor is None:
            return True
        try:
            target_type = torch.device(target_device).type
        except Exception:
            target_type = str(target_device)
        return tensor.device.type == target_type
    
    def _ensure_silence_latent_on_device(self):
        """Ensure silence_latent is on the correct device (self.device)."""
        if hasattr(self, "silence_latent") and self.silence_latent is not None:
            if not self._is_on_target_device(self.silence_latent, self.device):
                self.silence_latent = self.silence_latent.to(self.device).to(self.dtype)
    
    def _move_module_recursive(self, module, target_device, dtype=None, visited=None):
        """
        Recursively move a module and all its submodules to the target device.
        This handles modules that may not be properly registered.
        """
        if visited is None:
            visited = set()
        
        module_id = id(module)
        if module_id in visited:
            return
        visited.add(module_id)
        
        # Move the module itself
        module.to(target_device)
        if dtype is not None:
            module.to(dtype)
        
        # Move all direct parameters
        for param_name, param in module._parameters.items():
            if param is not None and not self._is_on_target_device(param, target_device):
                module._parameters[param_name] = param.to(target_device)
                if dtype is not None:
                    module._parameters[param_name] = module._parameters[param_name].to(dtype)
        
        # Move all direct buffers
        for buf_name, buf in module._buffers.items():
            if buf is not None and not self._is_on_target_device(buf, target_device):
                module._buffers[buf_name] = buf.to(target_device)
        
        # Recursively process all submodules (registered and unregistered)
        for name, child in module._modules.items():
            if child is not None:
                self._move_module_recursive(child, target_device, dtype, visited)
        
        # Also check for any nn.Module attributes that might not be in _modules
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue
            try:
                attr = getattr(module, attr_name, None)
                if isinstance(attr, torch.nn.Module) and id(attr) not in visited:
                    self._move_module_recursive(attr, target_device, dtype, visited)
            except Exception:
                pass
    
    def _recursive_to_device(self, model, device, dtype=None):
        """
        Recursively move all parameters and buffers of a model to the specified device.
        This is more thorough than model.to() for some custom HuggingFace models.
        """
        target_device = torch.device(device) if isinstance(device, str) else device
        
        # Method 1: Standard .to() call
        model.to(target_device)
        if dtype is not None:
            model.to(dtype)
        
        # Method 2: Use our thorough recursive moving for any missed modules
        self._move_module_recursive(model, target_device, dtype)
        
        # Method 3: Force move via state_dict if there are still parameters on wrong device
        wrong_device_params = []
        for name, param in model.named_parameters():
            if not self._is_on_target_device(param, device):
                wrong_device_params.append(name)
        
        if wrong_device_params and device != "cpu":
            logger.warning(f"[_recursive_to_device] {len(wrong_device_params)} parameters on wrong device, using state_dict method")
            # Get current state dict and move all tensors
            state_dict = model.state_dict()
            moved_state_dict = {}
            for key, value in state_dict.items():
                if isinstance(value, torch.Tensor):
                    moved_state_dict[key] = value.to(target_device)
                    if dtype is not None and moved_state_dict[key].is_floating_point():
                        moved_state_dict[key] = moved_state_dict[key].to(dtype)
                else:
                    moved_state_dict[key] = value
            model.load_state_dict(moved_state_dict)
        
        # Synchronize accelerator to ensure all transfers are complete
        if device != "cpu":
            self._synchronize()
        
        # Final verification
        if device != "cpu":
            still_wrong = []
            for name, param in model.named_parameters():
                if not self._is_on_target_device(param, device):
                    still_wrong.append(f"{name} on {param.device}")
            if still_wrong:
                logger.error(f"[_recursive_to_device] CRITICAL: {len(still_wrong)} parameters still on wrong device: {still_wrong[:10]}")
    
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
                        logger.info(f"[_load_model_context] Moving {model_name} to {self.device} (persistent)")
                        self._recursive_to_device(model, self.device, self.dtype)
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
        logger.info(f"[_load_model_context] Loading {model_name} to {self.device}")
        start_time = time.time()
        if model_name == "vae":
            vae_dtype = self._get_vae_dtype()
            self._recursive_to_device(model, self.device, vae_dtype)
        else:
            self._recursive_to_device(model, self.device, self.dtype)
        
        if model_name == "model" and hasattr(self, "silence_latent"):
             self.silence_latent = self.silence_latent.to(self.device).to(self.dtype)
        
        load_time = time.time() - start_time
        self.current_offload_cost += load_time
        logger.info(f"[_load_model_context] Loaded {model_name} to {self.device} in {load_time:.4f}s")

        try:
            yield
        finally:
            # Offload to CPU
            logger.info(f"[_load_model_context] Offloading {model_name} to CPU")
            start_time = time.time()
            if model_name == "vae":
                self._recursive_to_device(model, "cpu", self._get_vae_dtype("cpu"))
            else:
                self._recursive_to_device(model, "cpu")
            
            # NOTE: Do NOT offload silence_latent to CPU here!
            # silence_latent is used in many places outside of model context,
            # so it should stay on GPU to avoid device mismatch errors.
            
            self._empty_cache()
            offload_time = time.time() - start_time
            self.current_offload_cost += offload_time
            logger.info(f"[_load_model_context] Offloaded {model_name} to CPU in {offload_time:.4f}s")

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
            
            # Normalize to stereo 48kHz
            audio = self._normalize_audio_to_stereo_48k(audio, sr)
            
            return audio
        except Exception as e:
            logger.exception("[process_target_audio] Error processing target audio")
            return None
    
    def _parse_audio_code_string(self, code_str: str) -> List[int]:
        """Extract integer audio codes from prompt tokens like <|audio_code_123|>.
        Code values are clamped to valid range [0, 63999] (codebook size = 64000).
        """
        if not code_str:
            return []
        try:
            MAX_AUDIO_CODE = 63999  # Maximum valid audio code value (codebook size = 64000)
            codes = []
            clamped_count = 0
            for x in re.findall(r"<\|audio_code_(\d+)\|>", code_str):
                code_value = int(x)
                # Clamp code value to valid range [0, MAX_AUDIO_CODE]
                clamped_value = max(0, min(code_value, MAX_AUDIO_CODE))
                if clamped_value != code_value:
                    clamped_count += 1
                    logger.warning(f"[_parse_audio_code_string] Clamped audio code value from {code_value} to {clamped_value}")
                codes.append(clamped_value)
            if clamped_count > 0:
                logger.warning(f"[_parse_audio_code_string] Clamped {clamped_count} audio code value(s) to valid range [0, {MAX_AUDIO_CODE}]")
            return codes
        except Exception as e:
            logger.debug(f"[_parse_audio_code_string] Failed to parse audio code string: {e}")
            return []
    
    def _decode_audio_codes_to_latents(self, code_str: str) -> Optional[torch.Tensor]:
        """
        Convert serialized audio code string into 25Hz latents using model quantizer/detokenizer.
        
        Note: Code values are already clamped to valid range [0, 63999] by _parse_audio_code_string(),
        ensuring indices are within the quantizer's codebook size (64000).
        """
        if self.model is None or not hasattr(self.model, 'tokenizer') or not hasattr(self.model, 'detokenizer'):
            return None
        
        code_ids = self._parse_audio_code_string(code_str)
        if len(code_ids) == 0:
            return None
        
        with self._load_model_context("model"):
            quantizer = self.model.tokenizer.quantizer
            detokenizer = self.model.detokenizer
            
            num_quantizers = getattr(quantizer, "num_quantizers", 1)
            # Create indices tensor: [T_5Hz]
            # Note: code_ids are already clamped to [0, 63999] by _parse_audio_code_string()
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
            caption: Caption string (fallback if not in metas).
            lyrics: Lyrics string.
            metas: Metadata (str or dict); follows _parse_metas formatting.
                   May contain 'caption' and 'language' fields from LM CoT output.
            vocal_language: Language code for lyrics section (fallback if not in metas).

        Returns:
            (caption_input_text, lyrics_input_text)

        Example:
            caption_input, lyrics_input = handler.build_dit_inputs(
                task="text2music",
                instruction=None,
                caption="A calm piano melody",
                lyrics="la la la",
                metas={"bpm": 90, "duration": 45, "caption": "LM generated caption", "language": "en"},
                vocal_language="en",
            )
        """
        # Align instruction formatting with _prepare_batch
        final_instruction = self._format_instruction(instruction or DEFAULT_DIT_INSTRUCTION)

        # Extract caption and language from metas if available (from LM CoT output)
        # Fallback to user-provided values if not in metas
        actual_caption = caption
        actual_language = vocal_language
        
        if metas is not None:
            # Parse metas to dict if it's a string
            if isinstance(metas, str):
                # Try to parse as dict-like string or use as-is
                parsed_metas = self._parse_metas([metas])
                if parsed_metas and isinstance(parsed_metas[0], dict):
                    meta_dict = parsed_metas[0]
                else:
                    meta_dict = {}
            elif isinstance(metas, dict):
                meta_dict = metas
            else:
                meta_dict = {}
            
            # Extract caption from metas if available
            if 'caption' in meta_dict and meta_dict['caption']:
                actual_caption = str(meta_dict['caption'])
            
            # Extract language from metas if available
            if 'language' in meta_dict and meta_dict['language']:
                actual_language = str(meta_dict['language'])

        parsed_meta = self._parse_metas([metas])[0]
        caption_input = SFT_GEN_PROMPT.format(final_instruction, actual_caption, parsed_meta)
        lyrics_input = self._format_lyrics(lyrics, actual_language)
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
            logger.exception("[extract_caption_from_sft_format] Error extracting caption")
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
                        except (ValueError, TypeError) as e:
                            logger.debug(f"[prepare_seeds] Failed to parse seed value '{s}': {e}")
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
        """Build metadata dict - use "N/A" as default for empty fields."""
        return self._build_metadata_dict(bpm, key_scale, time_signature)
    
    def is_silence(self, audio):
        return torch.all(audio.abs() < 1e-6)
    
    def _get_project_root(self) -> str:
        """Get project root directory path."""
        current_file = os.path.abspath(__file__)
        return os.path.dirname(os.path.dirname(current_file))
    
    def _get_vae_dtype(self, device: Optional[str] = None) -> torch.dtype:
        """Get VAE dtype based on target device and GPU tier."""
        target_device = device or self.device
        if target_device in ["cuda", "xpu", "mps"]:
            return torch.bfloat16
        if target_device == "cpu":
            # On low-VRAM tiers (<=8GB), avoid CPU bfloat16 VAE path.
            # This path is often extremely slow and can destabilize preprocessing.
            gpu_config = get_global_gpu_config()
            if gpu_config.tier in {"tier1", "tier2", "tier3"}:
                return torch.float32
        return self.dtype
    
    def _format_instruction(self, instruction: str) -> str:
        """Format instruction to ensure it ends with colon."""
        if not instruction.endswith(":"):
            instruction = instruction + ":"
        return instruction
    
    def _normalize_audio_to_stereo_48k(self, audio: torch.Tensor, sr: int) -> torch.Tensor:
        """
        Normalize audio to stereo 48kHz format.
        
        Args:
            audio: Audio tensor [channels, samples] or [samples]
            sr: Sample rate
            
        Returns:
            Normalized audio tensor [2, samples] at 48kHz
        """
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
    
    def _normalize_audio_code_hints(self, audio_code_hints: Optional[Union[str, List[str]]], batch_size: int) -> List[Optional[str]]:
        """Normalize audio_code_hints to list of correct length."""
        if audio_code_hints is None:
            normalized = [None] * batch_size
        elif isinstance(audio_code_hints, str):
            normalized = [audio_code_hints] * batch_size
        elif len(audio_code_hints) == 1 and batch_size > 1:
            normalized = audio_code_hints * batch_size
        elif len(audio_code_hints) != batch_size:
            # Pad or truncate to match batch_size
            normalized = list(audio_code_hints[:batch_size])
            while len(normalized) < batch_size:
                normalized.append(None)
        else:
            normalized = list(audio_code_hints)
        
        # Clean up: convert empty strings to None
        normalized = [hint if isinstance(hint, str) and hint.strip() else None for hint in normalized]
        return normalized
    
    def _normalize_instructions(self, instructions: Optional[Union[str, List[str]]], batch_size: int, default: Optional[str] = None) -> List[str]:
        """Normalize instructions to list of correct length."""
        if instructions is None:
            default_instruction = default or DEFAULT_DIT_INSTRUCTION
            return [default_instruction] * batch_size
        elif isinstance(instructions, str):
            return [instructions] * batch_size
        elif len(instructions) == 1:
            return instructions * batch_size
        elif len(instructions) != batch_size:
            # Pad or truncate to match batch_size
            normalized = list(instructions[:batch_size])
            default_instruction = default or DEFAULT_DIT_INSTRUCTION
            while len(normalized) < batch_size:
                normalized.append(default_instruction)
            return normalized
        else:
            return list(instructions)
    
    def _format_lyrics(self, lyrics: str, language: str) -> str:
        """Format lyrics text with language header."""
        return f"# Languages\n{language}\n\n# Lyric\n{lyrics}<|endoftext|>"
    
    def _pad_sequences(self, sequences: List[torch.Tensor], max_length: int, pad_value: int = 0) -> torch.Tensor:
        """Pad sequences to same length."""
        return torch.stack([
            torch.nn.functional.pad(seq, (0, max_length - len(seq)), 'constant', pad_value)
            for seq in sequences
        ])
    
    def _extract_caption_and_language(self, metas: List[Union[str, Dict[str, Any]]], captions: List[str], vocal_languages: List[str]) -> Tuple[List[str], List[str]]:
        """Extract caption and language from metas with fallback to provided values."""
        actual_captions = list(captions)
        actual_languages = list(vocal_languages)
        
        for i, meta in enumerate(metas):
            if i >= len(actual_captions):
                break
                
            meta_dict = None
            if isinstance(meta, str):
                parsed = self._parse_metas([meta])
                if parsed and isinstance(parsed[0], dict):
                    meta_dict = parsed[0]
            elif isinstance(meta, dict):
                meta_dict = meta
            
            if meta_dict:
                if 'caption' in meta_dict and meta_dict['caption']:
                    actual_captions[i] = str(meta_dict['caption'])
                if 'language' in meta_dict and meta_dict['language']:
                    actual_languages[i] = str(meta_dict['language'])
        
        return actual_captions, actual_languages
    
    def _encode_audio_to_latents(self, audio: torch.Tensor) -> torch.Tensor:
        """
        Encode audio to latents using VAE with tiled encoding for long audio.
        
        Args:
            audio: Audio tensor [channels, samples] or [batch, channels, samples]
            
        Returns:
            Latents tensor [T, D] or [batch, T, D]
        """
        # Save original dimension info BEFORE modifying audio
        input_was_2d = (audio.dim() == 2)
        
        # Ensure batch dimension
        if input_was_2d:
            audio = audio.unsqueeze(0)
        
        # Use tiled_encode for memory-efficient encoding
        # tiled_encode handles device transfer and dtype conversion internally
        with torch.no_grad():
            latents = self.tiled_encode(audio, offload_latent_to_cpu=True)
        
        # Move back to device and cast to model dtype
        latents = latents.to(self.device).to(self.dtype)
        
        # Transpose: [batch, d, T] -> [batch, T, d]
        latents = latents.transpose(1, 2)
        
        # Remove batch dimension if input didn't have it
        if input_was_2d:
            latents = latents.squeeze(0)
        
        return latents
    
    def _build_metadata_dict(self, bpm: Optional[Union[int, str]], key_scale: str, time_signature: str, duration: Optional[float] = None) -> Dict[str, Any]:
        """
        Build metadata dictionary with default values.
        
        Args:
            bpm: BPM value (optional)
            key_scale: Key/scale string
            time_signature: Time signature string
            duration: Duration in seconds (optional)
            
        Returns:
            Metadata dictionary
        """
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
        
        # Add duration if provided
        if duration is not None:
            metadata_dict["duration"] = f"{int(duration)} seconds"
        
        return metadata_dict

    def generate_instruction(
        self,
        task_type: str,
        track_name: Optional[str] = None,
        complete_track_classes: Optional[List[str]] = None
    ) -> str:
        if task_type == "text2music":
            return TASK_INSTRUCTIONS["text2music"]
        elif task_type == "repaint":
            return TASK_INSTRUCTIONS["repaint"]
        elif task_type == "cover":
            return TASK_INSTRUCTIONS["cover"]
        elif task_type == "extract":
            if track_name:
                # Convert to uppercase
                track_name_upper = track_name.upper()
                return TASK_INSTRUCTIONS["extract"].format(TRACK_NAME=track_name_upper)
            else:
                return TASK_INSTRUCTIONS["extract_default"]
        elif task_type == "lego":
            if track_name:
                # Convert to uppercase
                track_name_upper = track_name.upper()
                return TASK_INSTRUCTIONS["lego"].format(TRACK_NAME=track_name_upper)
            else:
                return TASK_INSTRUCTIONS["lego_default"]
        elif task_type == "complete":
            if complete_track_classes and len(complete_track_classes) > 0:
                # Convert to uppercase and join with " | "
                track_classes_upper = [t.upper() for t in complete_track_classes]
                complete_track_classes_str = " | ".join(track_classes_upper)
                return TASK_INSTRUCTIONS["complete"].format(TRACK_CLASSES=complete_track_classes_str)
            else:
                return TASK_INSTRUCTIONS["complete_default"]
        else:
            return TASK_INSTRUCTIONS["text2music"]
    
    def process_reference_audio(self, audio_file) -> Optional[torch.Tensor]:
        if audio_file is None:
            return None
            
        try:
            # Load audio file
            audio, sr = torchaudio.load(audio_file)
            
            logger.debug(f"[process_reference_audio] Reference audio shape: {audio.shape}")
            logger.debug(f"[process_reference_audio] Reference audio sample rate: {sr}")
            logger.debug(f"[process_reference_audio] Reference audio duration: {audio.shape[-1] / 48000.0} seconds")
            
            # Normalize to stereo 48kHz
            audio = self._normalize_audio_to_stereo_48k(audio, sr)
            
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
            logger.exception("[process_reference_audio] Error processing reference audio")
            return None

    def process_src_audio(self, audio_file) -> Optional[torch.Tensor]:
        if audio_file is None:
            return None
            
        try:
            # Load audio file
            audio, sr = torchaudio.load(audio_file)
            
            # Normalize to stereo 48kHz
            audio = self._normalize_audio_to_stereo_48k(audio, sr)
            
            return audio
            
        except Exception as e:
            logger.exception("[process_src_audio] Error processing source audio")
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
                    # Check if audio is silence
                    if self.is_silence(processed_audio.unsqueeze(0)):
                        return "❌ Audio file appears to be silent"
                    
                    # Encode to latents using helper method
                    latents = self._encode_audio_to_latents(processed_audio)  # [T, d]
                
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
            logger.exception("[convert_src_audio_to_codes] Error converting audio to codes")
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
        elif audio_duration is not None and float(audio_duration) > 0:
            calculated_duration = float(audio_duration)

        # Build metadata dict - use "N/A" as default for empty fields
        metadata_dict = self._build_metadata_dict(bpm, key_scale, time_signature, calculated_duration)

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
            logger.exception("[create_target_wavs] Error creating target audio")
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
                if audio_duration is not None and float(audio_duration) > 0:
                    batch_target_wavs = self.create_target_wavs(float(audio_duration))
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
        
        # Ensure silence_latent is on the correct device for batch preparation
        self._ensure_silence_latent_on_device()

        # Normalize audio_code_hints to batch list
        audio_code_hints = self._normalize_audio_code_hints(audio_code_hints, batch_size)

        # Guard: refer_audios can be None when reference audio UI path didn't populate it (e.g. TEXT2MUSIC)
        if refer_audios is None:
            refer_audios = [[torch.zeros(2, 30 * self.sample_rate)] for _ in range(batch_size)]

        for ii, refer_audio_list in enumerate(refer_audios):
            if isinstance(refer_audio_list, list):
                for idx, refer_audio in enumerate(refer_audio_list):
                    refer_audio_list[idx] = refer_audio_list[idx].to(self.device).to(torch.bfloat16)
            elif isinstance(refer_audio_list, torch.Tensor):
                refer_audios[ii] = refer_audios[ii].to(self.device)
        
        if vocal_languages is None:
            vocal_languages = self._create_fallback_vocal_languages(batch_size)
        
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
                        # Encode using helper method
                        logger.info(f"[generate_music] Encoding target audio to latents for item {i}...")
                        target_latent = self._encode_audio_to_latents(current_wav.squeeze(0))  # Remove batch dim for helper
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
        instructions = self._normalize_instructions(instructions, batch_size, DEFAULT_DIT_INSTRUCTION)
        
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
        
        # Extract caption and language from metas if available (from LM CoT output)
        # Fallback to user-provided values if not in metas
        actual_captions, actual_languages = self._extract_caption_and_language(parsed_metas, captions, vocal_languages)
        
        # Format text_inputs
        text_inputs = []
        text_token_idss = []
        text_attention_masks = []
        lyric_token_idss = []
        lyric_attention_masks = []
        
        for i in range(batch_size):
            # Use custom instruction for this batch item
            instruction = self._format_instruction(instructions[i] if i < len(instructions) else DEFAULT_DIT_INSTRUCTION)
            
            actual_caption = actual_captions[i]
            actual_language = actual_languages[i]
            
            # Format text prompt with custom instruction (using LM-generated caption if available)
            text_prompt = SFT_GEN_PROMPT.format(instruction, actual_caption, parsed_metas[i])

            # DEBUG: Print DiT text encoder input for verification
            if i == 0:
                logger.info(f"\n{'='*70}")
                logger.info("🔍 [DEBUG] DiT TEXT ENCODER INPUT (Inference)")
                logger.info(f"{'='*70}")
                logger.info(f"text_prompt:\n{text_prompt}")
                logger.info(f"{'='*70}\n")

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
            
            # Format and tokenize lyrics (using LM-generated language if available)
            lyrics_text = self._format_lyrics(lyrics[i], actual_language)
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
        padded_text_token_idss = self._pad_sequences(text_token_idss, max_text_length, self.text_tokenizer.pad_token_id)
        padded_text_attention_masks = self._pad_sequences(text_attention_masks, max_text_length, 0)
        
        max_lyric_length = max(len(seq) for seq in lyric_token_idss)
        padded_lyric_token_idss = self._pad_sequences(lyric_token_idss, max_lyric_length, self.text_tokenizer.pad_token_id)
        padded_lyric_attention_masks = self._pad_sequences(lyric_attention_masks, max_lyric_length, 0)

        padded_non_cover_text_input_ids = None
        padded_non_cover_text_attention_masks = None
        if audio_cover_strength < 1.0:
            non_cover_text_input_ids = []
            non_cover_text_attention_masks = []
            for i in range(batch_size):
                # Use custom instruction for this batch item
                instruction = self._format_instruction(DEFAULT_DIT_INSTRUCTION)
                
                # Extract caption from metas if available (from LM CoT output)
                actual_caption = actual_captions[i]
                
                # Format text prompt with custom instruction (using LM-generated caption if available)
                text_prompt = SFT_GEN_PROMPT.format(instruction, actual_caption, parsed_metas[i])
                
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
            
            padded_non_cover_text_input_ids = self._pad_sequences(non_cover_text_input_ids, max_text_length, self.text_tokenizer.pad_token_id)
            padded_non_cover_text_attention_masks = self._pad_sequences(non_cover_text_attention_masks, max_text_length, 0)
        
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
        
        # Ensure silence_latent is on the correct device
        self._ensure_silence_latent_on_device()

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
                    # Use tiled_encode for memory-efficient encoding of long audio
                    with torch.no_grad():
                        refer_audio_latent = self.tiled_encode(refer_audio, offload_latent_to_cpu=True)
                    # Move to device and cast to model dtype
                    refer_audio_latent = refer_audio_latent.to(self.device).to(self.dtype)
                    # Ensure 3D before transpose: [C, T] -> [1, C, T] -> [1, T, C]
                    if refer_audio_latent.dim() == 2:
                        refer_audio_latent = refer_audio_latent.unsqueeze(0)
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
        shift: float = 1.0,
        audio_code_hints: Optional[Union[str, List[str]]] = None,
        infer_method: str = "ode",
        timesteps: Optional[List[float]] = None,
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
                logger.warning(f"[service_generate] dmd_gan version: infer_steps {infer_steps} exceeds maximum 8, clamping to 8")
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
        
        # Get batch size from captions
        batch_size = len(captions)

        # Normalize instructions and audio_code_hints to match batch size
        instructions = self._normalize_instructions(instructions, batch_size, DEFAULT_DIT_INSTRUCTION) if instructions is not None else None
        audio_code_hints = self._normalize_audio_code_hints(audio_code_hints, batch_size) if audio_code_hints is not None else None
        
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
        
        # Ensure silence_latent is on the correct device before creating generate_kwargs
        self._ensure_silence_latent_on_device()
        
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
            "shift": shift,
        }
        # Add custom timesteps if provided (convert to tensor)
        if timesteps is not None:
            generate_kwargs["timesteps"] = torch.tensor(timesteps, dtype=torch.float32)
        logger.info("[service_generate] Generating audio...")
        with self._load_model_context("model"):
            # Prepare condition tensors first (for LRC timestamp generation)
            encoder_hidden_states, encoder_attention_mask, context_latents = self.model.prepare_condition(
                text_hidden_states=text_hidden_states,
                text_attention_mask=text_attention_mask,
                lyric_hidden_states=lyric_hidden_states,
                lyric_attention_mask=lyric_attention_mask,
                refer_audio_acoustic_hidden_states_packed=refer_audio_acoustic_hidden_states_packed,
                refer_audio_order_mask=refer_audio_order_mask,
                hidden_states=src_latents,
                attention_mask=torch.ones(src_latents.shape[0], src_latents.shape[1], device=src_latents.device, dtype=src_latents.dtype),
                silence_latent=self.silence_latent,
                src_latents=src_latents,
                chunk_masks=chunk_mask,
                is_covers=is_covers,
                precomputed_lm_hints_25Hz=precomputed_lm_hints_25Hz,
            )
            
            outputs = self.model.generate_audio(**generate_kwargs)
        
        # Add intermediate information to outputs for extra_outputs
        outputs["src_latents"] = src_latents
        outputs["target_latents_input"] = target_latents  # Input target latents (before generation)
        outputs["chunk_masks"] = chunk_mask
        outputs["spans"] = spans
        outputs["latent_masks"] = batch.get("latent_masks")  # Latent masks for valid length
        
        # Add condition tensors for LRC timestamp generation
        outputs["encoder_hidden_states"] = encoder_hidden_states
        outputs["encoder_attention_mask"] = encoder_attention_mask
        outputs["context_latents"] = context_latents
        outputs["lyric_token_idss"] = lyric_token_idss
        
        return outputs

    def tiled_decode(self, latents, chunk_size=512, overlap=64, offload_wav_to_cpu=True):
        """
        Decode latents using tiling to reduce VRAM usage.
        Uses overlap-discard strategy to avoid boundary artifacts.
        
        Args:
            latents: [Batch, Channels, Length]
            chunk_size: Size of latent chunk to process at once
            overlap: Overlap size in latent frames
            offload_wav_to_cpu: If True, offload decoded wav audio to CPU immediately to save VRAM
        """
        B, C, T = latents.shape
        
        # Check device type (handle both string and torch.device)
        device_type = self.device if isinstance(self.device, str) else self.device.type
        if device_type == "mps":
            # MPS conv1d has an output length limit; use smaller chunks to avoid it.
            max_chunk_size = 32
            if chunk_size > max_chunk_size:
                orig_chunk_size = chunk_size
                orig_overlap = overlap
                chunk_size = max_chunk_size
                overlap = min(overlap, max(1, chunk_size // 4))
                logger.warning(
                    f"[tiled_decode] MPS device detected; reducing chunk_size from {orig_chunk_size} "
                    f"to {max_chunk_size} and overlap from {orig_overlap} to {overlap} "
                    f"to avoid MPS conv output limit."
                )
        
        # If short enough, decode directly
        if T <= chunk_size:
            # Decode and immediately extract .sample to avoid keeping DecoderOutput object
            decoder_output = self.vae.decode(latents)
            result = decoder_output.sample
            del decoder_output
            return result

        # Calculate stride (core size)
        stride = chunk_size - 2 * overlap
        if stride <= 0:
            raise ValueError(f"chunk_size {chunk_size} must be > 2 * overlap {overlap}")
        
        num_steps = math.ceil(T / stride)
        
        if offload_wav_to_cpu:
            # Optimized path: offload wav to CPU immediately to save VRAM
            return self._tiled_decode_offload_cpu(latents, B, T, stride, overlap, num_steps)
        else:
            # Default path: keep everything on GPU
            return self._tiled_decode_gpu(latents, B, T, stride, overlap, num_steps)
    
    def _tiled_decode_gpu(self, latents, B, T, stride, overlap, num_steps):
        """Standard tiled decode keeping all data on GPU."""
        decoded_audio_list = []
        upsample_factor = None
        
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
            decoder_output = self.vae.decode(latent_chunk)
            audio_chunk = decoder_output.sample
            del decoder_output
            
            # Determine upsample factor from the first chunk
            if upsample_factor is None:
                upsample_factor = audio_chunk.shape[-1] / latent_chunk.shape[-1]
            
            # Calculate trim amounts in audio samples
            # How much overlap was added at the start?
            added_start = core_start - win_start  # latent frames
            trim_start = int(round(added_start * upsample_factor))
            
            # How much overlap was added at the end?
            added_end = win_end - core_end  # latent frames
            trim_end = int(round(added_end * upsample_factor))
            
            # Trim audio
            audio_len = audio_chunk.shape[-1]
            end_idx = audio_len - trim_end if trim_end > 0 else audio_len
            
            audio_core = audio_chunk[:, :, trim_start:end_idx]
            decoded_audio_list.append(audio_core)
            
        # Concatenate
        final_audio = torch.cat(decoded_audio_list, dim=-1)
        return final_audio
    
    def _tiled_decode_offload_cpu(self, latents, B, T, stride, overlap, num_steps):
        """Optimized tiled decode that offloads to CPU immediately to save VRAM."""
        # First pass: decode first chunk to get upsample_factor and audio channels
        first_core_start = 0
        first_core_end = min(stride, T)
        first_win_start = 0
        first_win_end = min(T, first_core_end + overlap)
        
        first_latent_chunk = latents[:, :, first_win_start:first_win_end]
        first_decoder_output = self.vae.decode(first_latent_chunk)
        first_audio_chunk = first_decoder_output.sample
        del first_decoder_output
        
        upsample_factor = first_audio_chunk.shape[-1] / first_latent_chunk.shape[-1]
        audio_channels = first_audio_chunk.shape[1]
        
        # Calculate total audio length and pre-allocate CPU tensor
        total_audio_length = int(round(T * upsample_factor))
        final_audio = torch.zeros(B, audio_channels, total_audio_length, 
                                  dtype=first_audio_chunk.dtype, device='cpu')
        
        # Process first chunk: trim and copy to CPU
        first_added_end = first_win_end - first_core_end
        first_trim_end = int(round(first_added_end * upsample_factor))
        first_audio_len = first_audio_chunk.shape[-1]
        first_end_idx = first_audio_len - first_trim_end if first_trim_end > 0 else first_audio_len
        
        first_audio_core = first_audio_chunk[:, :, :first_end_idx]
        audio_write_pos = first_audio_core.shape[-1]
        final_audio[:, :, :audio_write_pos] = first_audio_core.cpu()
        
        # Free GPU memory
        del first_audio_chunk, first_audio_core, first_latent_chunk
        
        # Process remaining chunks
        for i in tqdm(range(1, num_steps), desc="Decoding audio chunks"):
            # Core range in latents
            core_start = i * stride
            core_end = min(core_start + stride, T)
            
            # Window range (with overlap)
            win_start = max(0, core_start - overlap)
            win_end = min(T, core_end + overlap)
            
            # Extract chunk
            latent_chunk = latents[:, :, win_start:win_end]
            
            # Decode on GPU
            # [Batch, Channels, AudioSamples]
            decoder_output = self.vae.decode(latent_chunk)
            audio_chunk = decoder_output.sample
            del decoder_output
            
            # Calculate trim amounts in audio samples
            added_start = core_start - win_start  # latent frames
            trim_start = int(round(added_start * upsample_factor))
            
            added_end = win_end - core_end  # latent frames
            trim_end = int(round(added_end * upsample_factor))
            
            # Trim audio
            audio_len = audio_chunk.shape[-1]
            end_idx = audio_len - trim_end if trim_end > 0 else audio_len
            
            audio_core = audio_chunk[:, :, trim_start:end_idx]
            
            # Copy to pre-allocated CPU tensor
            core_len = audio_core.shape[-1]
            final_audio[:, :, audio_write_pos:audio_write_pos + core_len] = audio_core.cpu()
            audio_write_pos += core_len
            
            # Free GPU memory immediately
            del audio_chunk, audio_core, latent_chunk
        
        # Trim to actual length (in case of rounding differences)
        final_audio = final_audio[:, :, :audio_write_pos]
        
        return final_audio
    
    def tiled_encode(self, audio, chunk_size=None, overlap=None, offload_latent_to_cpu=True):
        """
        Encode audio to latents using tiling to reduce VRAM usage.
        Uses overlap-discard strategy to avoid boundary artifacts.
        
        Args:
            audio: Audio tensor [Batch, Channels, Samples] or [Channels, Samples]
            chunk_size: Size of audio chunk to process at once (in samples). 
                       Default: 48000 * 30 = 1440000 (30 seconds at 48kHz)
            overlap: Overlap size in audio samples. Default: 48000 * 2 = 96000 (2 seconds)
            offload_latent_to_cpu: If True, offload encoded latents to CPU immediately to save VRAM
            
        Returns:
            Latents tensor [Batch, Channels, T] (same format as vae.encode output)
        """
        # Default values for 48kHz audio, adaptive to GPU memory
        if chunk_size is None:
            gpu_memory = get_gpu_memory_gb()
            if gpu_memory <= 8:
                chunk_size = 48000 * 15  # 15 seconds for low VRAM (<4GB)
            else:
                chunk_size = 48000 * 30  # 30 seconds for normal VRAM
        if overlap is None:
            overlap = 48000 * 2  # 2 seconds overlap
        
        # Handle 2D input [Channels, Samples]
        input_was_2d = (audio.dim() == 2)
        if input_was_2d:
            audio = audio.unsqueeze(0)
        
        B, C, S = audio.shape  # Batch, Channels, Samples
        
        # If short enough, encode directly
        if S <= chunk_size:
            vae_input = audio.to(self.device).to(self.vae.dtype)
            with torch.no_grad():
                latents = self.vae.encode(vae_input).latent_dist.sample()
            if input_was_2d:
                latents = latents.squeeze(0)
            return latents
        
        # Calculate stride (core size)
        stride = chunk_size - 2 * overlap
        if stride <= 0:
            raise ValueError(f"chunk_size {chunk_size} must be > 2 * overlap {overlap}")
        
        num_steps = math.ceil(S / stride)
        
        if offload_latent_to_cpu:
            result = self._tiled_encode_offload_cpu(audio, B, S, stride, overlap, num_steps, chunk_size)
        else:
            result = self._tiled_encode_gpu(audio, B, S, stride, overlap, num_steps, chunk_size)
        
        if input_was_2d:
            result = result.squeeze(0)
        
        return result
    
    def _tiled_encode_gpu(self, audio, B, S, stride, overlap, num_steps, chunk_size):
        """Standard tiled encode keeping all data on GPU."""
        encoded_latent_list = []
        downsample_factor = None
        
        for i in tqdm(range(num_steps), desc="Encoding audio chunks"):
            # Core range in audio samples
            core_start = i * stride
            core_end = min(core_start + stride, S)
            
            # Window range (with overlap)
            win_start = max(0, core_start - overlap)
            win_end = min(S, core_end + overlap)
            
            # Extract chunk and move to GPU
            audio_chunk = audio[:, :, win_start:win_end].to(self.device).to(self.vae.dtype)
            
            # Encode
            with torch.no_grad():
                latent_chunk = self.vae.encode(audio_chunk).latent_dist.sample()
            
            # Determine downsample factor from the first chunk
            if downsample_factor is None:
                downsample_factor = audio_chunk.shape[-1] / latent_chunk.shape[-1]
            
            # Calculate trim amounts in latent frames
            added_start = core_start - win_start  # audio samples
            trim_start = int(round(added_start / downsample_factor))
            
            added_end = win_end - core_end  # audio samples
            trim_end = int(round(added_end / downsample_factor))
            
            # Trim latent
            latent_len = latent_chunk.shape[-1]
            end_idx = latent_len - trim_end if trim_end > 0 else latent_len
            
            latent_core = latent_chunk[:, :, trim_start:end_idx]
            encoded_latent_list.append(latent_core)
            
            del audio_chunk
        
        # Concatenate
        final_latents = torch.cat(encoded_latent_list, dim=-1)
        return final_latents
    
    def _tiled_encode_offload_cpu(self, audio, B, S, stride, overlap, num_steps, chunk_size):
        """Optimized tiled encode that offloads latents to CPU immediately to save VRAM."""
        # First pass: encode first chunk to get downsample_factor and latent channels
        first_core_start = 0
        first_core_end = min(stride, S)
        first_win_start = 0
        first_win_end = min(S, first_core_end + overlap)
        
        first_audio_chunk = audio[:, :, first_win_start:first_win_end].to(self.device).to(self.vae.dtype)
        with torch.no_grad():
            first_latent_chunk = self.vae.encode(first_audio_chunk).latent_dist.sample()
        
        downsample_factor = first_audio_chunk.shape[-1] / first_latent_chunk.shape[-1]
        latent_channels = first_latent_chunk.shape[1]
        
        # Calculate total latent length and pre-allocate CPU tensor
        total_latent_length = int(round(S / downsample_factor))
        final_latents = torch.zeros(B, latent_channels, total_latent_length, 
                                   dtype=first_latent_chunk.dtype, device='cpu')
        
        # Process first chunk: trim and copy to CPU
        first_added_end = first_win_end - first_core_end
        first_trim_end = int(round(first_added_end / downsample_factor))
        first_latent_len = first_latent_chunk.shape[-1]
        first_end_idx = first_latent_len - first_trim_end if first_trim_end > 0 else first_latent_len
        
        first_latent_core = first_latent_chunk[:, :, :first_end_idx]
        latent_write_pos = first_latent_core.shape[-1]
        final_latents[:, :, :latent_write_pos] = first_latent_core.cpu()
        
        # Free GPU memory
        del first_audio_chunk, first_latent_chunk, first_latent_core
        
        # Process remaining chunks
        for i in tqdm(range(1, num_steps), desc="Encoding audio chunks"):
            # Core range in audio samples
            core_start = i * stride
            core_end = min(core_start + stride, S)
            
            # Window range (with overlap)
            win_start = max(0, core_start - overlap)
            win_end = min(S, core_end + overlap)
            
            # Extract chunk and move to GPU
            audio_chunk = audio[:, :, win_start:win_end].to(self.device).to(self.vae.dtype)
            
            # Encode on GPU
            with torch.no_grad():
                latent_chunk = self.vae.encode(audio_chunk).latent_dist.sample()
            
            # Calculate trim amounts in latent frames
            added_start = core_start - win_start  # audio samples
            trim_start = int(round(added_start / downsample_factor))
            
            added_end = win_end - core_end  # audio samples
            trim_end = int(round(added_end / downsample_factor))
            
            # Trim latent
            latent_len = latent_chunk.shape[-1]
            end_idx = latent_len - trim_end if trim_end > 0 else latent_len
            
            latent_core = latent_chunk[:, :, trim_start:end_idx]
            
            # Copy to pre-allocated CPU tensor
            core_len = latent_core.shape[-1]
            final_latents[:, :, latent_write_pos:latent_write_pos + core_len] = latent_core.cpu()
            latent_write_pos += core_len
            
            # Free GPU memory immediately
            del audio_chunk, latent_chunk, latent_core
        
        # Trim to actual length (in case of rounding differences)
        final_latents = final_latents[:, :, :latent_write_pos]
        
        return final_latents

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
        instruction: str = DEFAULT_DIT_INSTRUCTION,
        audio_cover_strength: float = 1.0,
        task_type: str = "text2music",
        use_adg: bool = False,
        cfg_interval_start: float = 0.0,
        cfg_interval_end: float = 1.0,
        shift: float = 1.0,
        infer_method: str = "ode",
        use_tiled_decode: bool = True,
        timesteps: Optional[List[float]] = None,
        progress=None
    ) -> Dict[str, Any]:
        """
        Main interface for music generation
        
        Returns:
            Dictionary containing:
            - audios: List of audio dictionaries with path, key, params
            - generation_info: Markdown-formatted generation information
            - status_message: Status message
            - extra_outputs: Dictionary with latents, masks, time_costs, etc.
            - success: Whether generation completed successfully
            - error: Error message if generation failed
        """
        if progress is None:
            def progress(*args, **kwargs):
                pass

        if self.model is None or self.vae is None or self.text_tokenizer is None or self.text_encoder is None:
            return {
                "audios": [],
                "status_message": "❌ Model not fully initialized. Please initialize all components first.",
                "extra_outputs": {},
                "success": False,
                "error": "Model not fully initialized",
            }

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
                instruction = TASK_INSTRUCTIONS["cover"]

        logger.info("[generate_music] Starting generation...")
        if progress:
            progress(0.51, desc="Preparing inputs...")
        logger.info("[generate_music] Preparing inputs...")
        
        # Reset offload cost
        self.current_offload_cost = 0.0

        # Caption and lyrics are optional - can be empty
        # Use provided batch_size or default
        actual_batch_size = batch_size if batch_size is not None else self.batch_size
        actual_batch_size = max(1, actual_batch_size)  # Ensure at least 1

        actual_seed_list, seed_value_for_ui = self.prepare_seeds(actual_batch_size, seed, use_random_seed)
        
        # Convert special values to None
        if audio_duration is not None and float(audio_duration) <= 0:
            audio_duration = None
        # if seed is not None and seed < 0:
        #     seed = None
        if repainting_end is not None and float(repainting_end) < 0:
            repainting_end = None
            
        try:
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
            
            progress(0.52, desc=f"Generating music (batch size: {actual_batch_size})...")
            
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
                shift=shift,  # Pass shift parameter
                infer_method=infer_method,  # Pass infer method (ode or sde)
                audio_code_hints=audio_code_hints_batch,  # Pass audio code hints as list
                return_intermediate=should_return_intermediate,
                timesteps=timesteps,  # Pass custom timesteps if provided
            )
            
            logger.info("[generate_music] Model generation completed. Decoding latents...")
            pred_latents = outputs["target_latents"]  # [batch, latent_length, latent_dim]
            time_costs = outputs["time_costs"]
            time_costs["offload_time_cost"] = self.current_offload_cost
            logger.debug(f"[generate_music] pred_latents: {pred_latents.shape}, dtype={pred_latents.dtype} {pred_latents.min()=}, {pred_latents.max()=}, {pred_latents.mean()=}, {pred_latents.std()=}")
            logger.debug(f"[generate_music] time_costs: {time_costs}")

            if torch.isnan(pred_latents).any() or torch.isinf(pred_latents).any():
                raise RuntimeError(
                    "Generation produced NaN or Inf latents. "
                    "This usually indicates a checkpoint/config mismatch "
                    "or unsupported quantization/backend combination. "
                    "Try running with --backend pt or verify your model checkpoints match this release."
                )
            if pred_latents.numel() > 0 and pred_latents.abs().sum() == 0:
                raise RuntimeError(
                    "Generation produced zero latents. "
                    "This usually indicates a checkpoint/config mismatch or unsupported setup."
                )

            if progress:
                progress(0.8, desc="Decoding audio...")
            logger.info("[generate_music] Decoding latents with VAE...")
            
            # Decode latents to audio
            start_time = time.time()
            with torch.no_grad():
                with self._load_model_context("vae"):
                    # Move pred_latents to CPU early to save VRAM (will be used in extra_outputs later)
                    pred_latents_cpu = pred_latents.detach().cpu()
                    
                    # Transpose for VAE decode: [batch, latent_length, latent_dim] -> [batch, latent_dim, latent_length]
                    pred_latents_for_decode = pred_latents.transpose(1, 2).contiguous()
                    # Ensure input is in VAE's dtype
                    pred_latents_for_decode = pred_latents_for_decode.to(self.vae.dtype)
                    
                    # Release original pred_latents to free VRAM before VAE decode
                    del pred_latents
                    self._empty_cache()
                    
                    logger.debug(f"[generate_music] Before VAE decode: allocated={self._memory_allocated()/1024**3:.2f}GB, max={self._max_memory_allocated()/1024**3:.2f}GB")
                    
                    # ROCm fix: decode VAE on CPU to bypass MIOpen workspace bugs
                    # On APUs with unified memory this has zero data-transfer cost
                    import os as _os
                    _vae_cpu = _os.environ.get("ACESTEP_VAE_ON_CPU", "0").lower() in ("1", "true", "yes")
                    if _vae_cpu:
                        logger.info("[generate_music] Moving VAE to CPU for decode (ACESTEP_VAE_ON_CPU=1)...")
                        _vae_device = next(self.vae.parameters()).device
                        self.vae = self.vae.cpu()
                        pred_latents_for_decode = pred_latents_for_decode.cpu()
                        self._empty_cache()

                    if use_tiled_decode:
                        logger.info("[generate_music] Using tiled VAE decode to reduce VRAM usage...")
                        pred_wavs = self.tiled_decode(pred_latents_for_decode)  # [batch, channels, samples]
                    else:
                        decoder_output = self.vae.decode(pred_latents_for_decode)
                        pred_wavs = decoder_output.sample
                        del decoder_output

                    if _vae_cpu:
                        logger.info("[generate_music] VAE decode on CPU complete, restoring to GPU...")
                        self.vae = self.vae.to(_vae_device)
                        if pred_wavs.device.type != 'cpu':
                            pass  # already on right device
                        # pred_wavs stays on CPU - fine for audio post-processing
                    
                    logger.debug(f"[generate_music] After VAE decode: allocated={self._memory_allocated()/1024**3:.2f}GB, max={self._max_memory_allocated()/1024**3:.2f}GB")
                    
                    # Release pred_latents_for_decode after decode
                    del pred_latents_for_decode
                    
                    # Cast output to float32 for audio processing/saving (in-place if possible)
                    if pred_wavs.dtype != torch.float32:
                        pred_wavs = pred_wavs.float()
                    
                    self._empty_cache()
            end_time = time.time()
            time_costs["vae_decode_time_cost"] = end_time - start_time
            time_costs["total_time_cost"] = time_costs["total_time_cost"] + time_costs["vae_decode_time_cost"]
            
            # Update offload cost one last time to include VAE offloading
            time_costs["offload_time_cost"] = self.current_offload_cost
            
            logger.info("[generate_music] VAE decode completed. Preparing audio tensors...")
            if progress:
                progress(0.99, desc="Preparing audio data...")
            
            # Prepare audio tensors (no file I/O here, no UUID generation)
            # pred_wavs is already [batch, channels, samples] format
            # Move to CPU and convert to float32 for return
            audio_tensors = []
            
            for i in range(actual_batch_size):
                # Extract audio tensor: [channels, samples] format, CPU, float32
                audio_tensor = pred_wavs[i].cpu().float()
                audio_tensors.append(audio_tensor)
            
            status_message = f"✅ Generation completed successfully!"
            logger.info(f"[generate_music] Done! Generated {len(audio_tensors)} audio tensors.")
            
            # Extract intermediate information from outputs
            src_latents = outputs.get("src_latents")  # [batch, T, D]
            target_latents_input = outputs.get("target_latents_input")  # [batch, T, D]
            chunk_masks = outputs.get("chunk_masks")  # [batch, T]
            spans = outputs.get("spans", [])  # List of tuples
            latent_masks = outputs.get("latent_masks")  # [batch, T]
            
            # Extract condition tensors for LRC timestamp generation
            encoder_hidden_states = outputs.get("encoder_hidden_states")
            encoder_attention_mask = outputs.get("encoder_attention_mask")
            context_latents = outputs.get("context_latents")
            lyric_token_idss = outputs.get("lyric_token_idss")
            
            # Move all tensors to CPU to save VRAM (detach to release computation graph)
            extra_outputs = {
                "pred_latents": pred_latents_cpu,  # Already moved to CPU earlier to save VRAM during VAE decode
                "target_latents": target_latents_input.detach().cpu() if target_latents_input is not None else None,
                "src_latents": src_latents.detach().cpu() if src_latents is not None else None,
                "chunk_masks": chunk_masks.detach().cpu() if chunk_masks is not None else None,
                "latent_masks": latent_masks.detach().cpu() if latent_masks is not None else None,
                "spans": spans,
                "time_costs": time_costs,
                "seed_value": seed_value_for_ui,
                # Condition tensors for LRC timestamp generation
                "encoder_hidden_states": encoder_hidden_states.detach().cpu() if encoder_hidden_states is not None else None,
                "encoder_attention_mask": encoder_attention_mask.detach().cpu() if encoder_attention_mask is not None else None,
                "context_latents": context_latents.detach().cpu() if context_latents is not None else None,
                "lyric_token_idss": lyric_token_idss.detach().cpu() if lyric_token_idss is not None else None,
            }
            
            # Build audios list with tensor data (no file paths, no UUIDs, handled outside)
            audios = []
            for idx, audio_tensor in enumerate(audio_tensors):
                audio_dict = {
                    "tensor": audio_tensor,  # torch.Tensor [channels, samples], CPU, float32
                    "sample_rate": self.sample_rate,
                }
                audios.append(audio_dict)
            
            return {
                "audios": audios,
                "status_message": status_message,
                "extra_outputs": extra_outputs,
                "success": True,
                "error": None,
            }

        except Exception as e:
            error_msg = f"❌ Error: {str(e)}\n{traceback.format_exc()}"
            logger.exception("[generate_music] Generation failed")
            return {
                "audios": [],
                "status_message": error_msg,
                "extra_outputs": {},
                "success": False,
                "error": str(e),
            }

    @torch.no_grad()
    def get_lyric_timestamp(
        self,
        pred_latent: torch.Tensor,
        encoder_hidden_states: torch.Tensor,
        encoder_attention_mask: torch.Tensor,
        context_latents: torch.Tensor,
        lyric_token_ids: torch.Tensor,
        total_duration_seconds: float,
        vocal_language: str = "en",
        inference_steps: int = 8,
        seed: int = 42,
        custom_layers_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate lyrics timestamps from generated audio latents using cross-attention alignment.
        
        This method adds noise to the final pred_latent and re-infers one step to get
        cross-attention matrices, then uses DTW to align lyrics tokens with audio frames.
        
        Args:
            pred_latent: Generated latent tensor [batch, T, D]
            encoder_hidden_states: Cached encoder hidden states
            encoder_attention_mask: Cached encoder attention mask
            context_latents: Cached context latents
            lyric_token_ids: Tokenized lyrics tensor [batch, seq_len]
            total_duration_seconds: Total audio duration in seconds
            vocal_language: Language code for lyrics header parsing
            inference_steps: Number of inference steps (for noise level calculation)
            seed: Random seed for noise generation
            custom_layers_config: Dict mapping layer indices to head indices
            
        Returns:
            Dict containing:
            - lrc_text: LRC formatted lyrics with timestamps
            - sentence_timestamps: List of SentenceTimestamp objects
            - token_timestamps: List of TokenTimestamp objects
            - success: Whether generation succeeded
            - error: Error message if failed
        """
        from transformers.cache_utils import EncoderDecoderCache, DynamicCache
        
        if self.model is None:
            return {
                "lrc_text": "",
                "sentence_timestamps": [],
                "token_timestamps": [],
                "success": False,
                "error": "Model not initialized"
            }
        
        if custom_layers_config is None:
            custom_layers_config = self.custom_layers_config
        
        try:
            # Move tensors to device
            device = self.device
            dtype = self.dtype
            
            pred_latent = pred_latent.to(device=device, dtype=dtype)
            encoder_hidden_states = encoder_hidden_states.to(device=device, dtype=dtype)
            encoder_attention_mask = encoder_attention_mask.to(device=device, dtype=dtype)
            context_latents = context_latents.to(device=device, dtype=dtype)
            
            bsz = pred_latent.shape[0]
            
            # Calculate noise level: t_last = 1.0 / inference_steps
            t_last_val = 1.0 / inference_steps
            t_curr_tensor = torch.tensor([t_last_val] * bsz, device=device, dtype=dtype)
            
            x1 = pred_latent
            
            # Generate noise
            if seed is None:
                x0 = torch.randn_like(x1)
            else:
                # MPS doesn't support torch.Generator(device="mps"); use CPU generator and move result
                gen_device = "cpu" if (isinstance(device, str) and device == "mps") or (hasattr(device, 'type') and device.type == "mps") else device
                generator = torch.Generator(device=gen_device).manual_seed(int(seed))
                x0 = torch.randn(x1.shape, generator=generator, device=gen_device, dtype=dtype).to(device)
            
            # Add noise to pred_latent: xt = t * noise + (1 - t) * x1
            xt = t_last_val * x0 + (1.0 - t_last_val) * x1

            xt_in = xt
            t_in = t_curr_tensor
            
            # Get null condition embedding
            encoder_hidden_states_in = encoder_hidden_states
            encoder_attention_mask_in = encoder_attention_mask
            context_latents_in = context_latents
            latent_length = x1.shape[1]
            attention_mask = torch.ones(bsz, latent_length, device=device, dtype=dtype)
            attention_mask_in = attention_mask
            past_key_values = None
            
            # Run decoder with output_attentions=True
            with self._load_model_context("model"):
                decoder = self.model.decoder
                decoder_outputs = decoder(
                    hidden_states=xt_in,
                    timestep=t_in,
                    timestep_r=t_in,
                    attention_mask=attention_mask_in,
                    encoder_hidden_states=encoder_hidden_states_in,
                    use_cache=False,
                    past_key_values=past_key_values,
                    encoder_attention_mask=encoder_attention_mask_in,
                    context_latents=context_latents_in,
                    output_attentions=True,
                    custom_layers_config=custom_layers_config,
                    enable_early_exit=True
                )
                
                # Extract cross-attention matrices
                if decoder_outputs[2] is None:
                    return {
                        "lrc_text": "",
                        "sentence_timestamps": [],
                        "token_timestamps": [],
                        "success": False,
                        "error": "Model did not return attentions"
                    }
                
                cross_attns = decoder_outputs[2]  # Tuple of tensors (some may be None)
                
                captured_layers_list = []
                for layer_attn in cross_attns:
                    # Skip None values (layers that didn't return attention)
                    if layer_attn is None:
                        continue
                    # Only take conditional part (first half of batch)
                    cond_attn = layer_attn[:bsz]
                    layer_matrix = cond_attn.transpose(-1, -2)
                    captured_layers_list.append(layer_matrix)
                
                if not captured_layers_list:
                    return {
                        "lrc_text": "",
                        "sentence_timestamps": [],
                        "token_timestamps": [],
                        "success": False,
                        "error": "No valid attention layers returned"
                    }
                
                stacked = torch.stack(captured_layers_list)
                if bsz == 1:
                    all_layers_matrix = stacked.squeeze(1)
                else:
                    all_layers_matrix = stacked
            
            # Process lyric token IDs to extract pure lyrics
            if isinstance(lyric_token_ids, torch.Tensor):
                raw_lyric_ids = lyric_token_ids[0].tolist()
            else:
                raw_lyric_ids = lyric_token_ids
            
            # Parse header to find lyrics start position
            header_str = f"# Languages\n{vocal_language}\n\n# Lyric\n"
            header_ids = self.text_tokenizer.encode(header_str, add_special_tokens=False)
            start_idx = len(header_ids)
            
            # Find end of lyrics (before endoftext token)
            try:
                end_idx = raw_lyric_ids.index(151643)  # <|endoftext|> token
            except ValueError:
                end_idx = len(raw_lyric_ids)
            
            pure_lyric_ids = raw_lyric_ids[start_idx:end_idx]
            pure_lyric_matrix = all_layers_matrix[:, :, start_idx:end_idx, :]
            
            # Create aligner and generate timestamps
            aligner = MusicStampsAligner(self.text_tokenizer)
            
            align_info = aligner.stamps_align_info(
                attention_matrix=pure_lyric_matrix,
                lyrics_tokens=pure_lyric_ids,
                total_duration_seconds=total_duration_seconds,
                custom_config=custom_layers_config,
                return_matrices=False,
                violence_level=2.0,
                medfilt_width=1,
            )
            
            if align_info.get("calc_matrix") is None:
                return {
                    "lrc_text": "",
                    "sentence_timestamps": [],
                    "token_timestamps": [],
                    "success": False,
                    "error": align_info.get("error", "Failed to process attention matrix")
                }
            
            # Generate timestamps
            result = aligner.get_timestamps_and_lrc(
                calc_matrix=align_info["calc_matrix"],
                lyrics_tokens=pure_lyric_ids,
                total_duration_seconds=total_duration_seconds
            )
            
            return {
                "lrc_text": result["lrc_text"],
                "sentence_timestamps": result["sentence_timestamps"],
                "token_timestamps": result["token_timestamps"],
                "success": True,
                "error": None
            }
            
        except Exception as e:
            error_msg = f"Error generating timestamps: {str(e)}"
            logger.exception("[get_lyric_timestamp] Failed")
            return {
                "lrc_text": "",
                "sentence_timestamps": [],
                "token_timestamps": [],
                "success": False,
                "error": error_msg
            }

    @torch.no_grad()
    def get_lyric_score(
            self,
            pred_latent: torch.Tensor,
            encoder_hidden_states: torch.Tensor,
            encoder_attention_mask: torch.Tensor,
            context_latents: torch.Tensor,
            lyric_token_ids: torch.Tensor,
            vocal_language: str = "en",
            inference_steps: int = 8,
            seed: int = 42,
            custom_layers_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Calculate both LM and DiT alignment scores in one pass.

        - lm_score: Checks structural alignment using pure noise at t=1.0.
        - dit_score: Checks denoising alignment using regressed latents at t=1/steps.

        Args:
            pred_latent: Generated latent tensor [batch, T, D]
            encoder_hidden_states: Cached encoder hidden states
            encoder_attention_mask: Cached encoder attention mask
            context_latents: Cached context latents
            lyric_token_ids: Tokenized lyrics tensor [batch, seq_len]
            vocal_language: Language code for lyrics header parsing
            inference_steps: Number of inference steps (for noise level calculation)
            seed: Random seed for noise generation
            custom_layers_config: Dict mapping layer indices to head indices

        Returns:
            Dict containing:
            - lm_score: float
            - dit_score: float
            - success: Whether generation succeeded
            - error: Error message if failed
        """
        from transformers.cache_utils import EncoderDecoderCache, DynamicCache

        if self.model is None:
            return {
                "lm_score": 0.0,
                "dit_score": 0.0,
                "success": False,
                "error": "Model not initialized"
            }

        if custom_layers_config is None:
            custom_layers_config = self.custom_layers_config

        try:
            # Move tensors to device
            device = self.device
            dtype = self.dtype

            pred_latent = pred_latent.to(device=device, dtype=dtype)
            encoder_hidden_states = encoder_hidden_states.to(device=device, dtype=dtype)
            encoder_attention_mask = encoder_attention_mask.to(device=device, dtype=dtype)
            context_latents = context_latents.to(device=device, dtype=dtype)

            bsz = pred_latent.shape[0]

            if seed is None:
                x0 = torch.randn_like(pred_latent)
            else:
                # MPS doesn't support torch.Generator(device="mps"); use CPU generator and move result
                gen_device = "cpu" if (isinstance(device, str) and device == "mps") or (hasattr(device, 'type') and device.type == "mps") else device
                generator = torch.Generator(device=gen_device).manual_seed(int(seed))
                x0 = torch.randn(pred_latent.shape, generator=generator, device=gen_device, dtype=dtype).to(device)

            # --- Input A: LM Score ---
            # t = 1.0, xt = Pure Noise
            t_lm = torch.tensor([1.0] * bsz, device=device, dtype=dtype)
            xt_lm = x0

            # --- Input B: DiT Score ---
            # t = 1.0/steps, xt = Regressed Latent
            t_last_val = 1.0 / inference_steps
            t_dit = torch.tensor([t_last_val] * bsz, device=device, dtype=dtype)
            # Flow Matching Regression: xt = t*x0 + (1-t)*x1
            xt_dit = t_last_val * x0 + (1.0 - t_last_val) * pred_latent

            # Order: [Think_Batch, DiT_Batch]
            xt_in = torch.cat([xt_lm, xt_dit], dim=0)
            t_in = torch.cat([t_lm, t_dit], dim=0)

            # Duplicate conditions
            encoder_hidden_states_in = torch.cat([encoder_hidden_states, encoder_hidden_states], dim=0)
            encoder_attention_mask_in = torch.cat([encoder_attention_mask, encoder_attention_mask], dim=0)
            context_latents_in = torch.cat([context_latents, context_latents], dim=0)

            # Prepare Attention Mask
            latent_length = xt_in.shape[1]
            attention_mask_in = torch.ones(2 * bsz, latent_length, device=device, dtype=dtype)
            past_key_values = None

            # Run decoder with output_attentions=True
            with self._load_model_context("model"):
                decoder = self.model.decoder
                if hasattr(decoder, 'eval'):
                    decoder.eval()

                decoder_outputs = decoder(
                    hidden_states=xt_in,
                    timestep=t_in,
                    timestep_r=t_in,
                    attention_mask=attention_mask_in,
                    encoder_hidden_states=encoder_hidden_states_in,
                    use_cache=False,
                    past_key_values=past_key_values,
                    encoder_attention_mask=encoder_attention_mask_in,
                    context_latents=context_latents_in,
                    output_attentions=True,
                    custom_layers_config=custom_layers_config,
                    enable_early_exit=True
                )

                # Extract cross-attention matrices
                if decoder_outputs[2] is None:
                    return {
                        "lm_score": 0.0,
                        "dit_score": 0.0,
                        "success": False,
                        "error": "Model did not return attentions"
                    }

                cross_attns = decoder_outputs[2]  # Tuple of tensors (some may be None)

                captured_layers_list = []
                for layer_attn in cross_attns:
                    if layer_attn is None:
                        continue

                    # Only take conditional part (first half of batch)
                    layer_matrix = layer_attn.transpose(-1, -2)
                    captured_layers_list.append(layer_matrix)

                if not captured_layers_list:
                    return {
                        "lm_score": 0.0,
                        "dit_score": 0.0,
                        "success": False,
                        "error": "No valid attention layers returned"
                    }

                stacked = torch.stack(captured_layers_list)

                all_layers_matrix_lm = stacked[:, :bsz, ...]
                all_layers_matrix_dit = stacked[:, bsz:, ...]

                if bsz == 1:
                    all_layers_matrix_lm = all_layers_matrix_lm.squeeze(1)
                    all_layers_matrix_dit = all_layers_matrix_dit.squeeze(1)
                else:
                    pass

            # Process lyric token IDs to extract pure lyrics
            if isinstance(lyric_token_ids, torch.Tensor):
                raw_lyric_ids = lyric_token_ids[0].tolist()
            else:
                raw_lyric_ids = lyric_token_ids

            # Parse header to find lyrics start position
            header_str = f"# Languages\n{vocal_language}\n\n# Lyric\n"
            header_ids = self.text_tokenizer.encode(header_str, add_special_tokens=False)
            start_idx = len(header_ids)

            # Find end of lyrics (before endoftext token)
            try:
                end_idx = raw_lyric_ids.index(151643)  # <|endoftext|> token
            except ValueError:
                end_idx = len(raw_lyric_ids)

            pure_lyric_ids = raw_lyric_ids[start_idx:end_idx]
            if start_idx >= all_layers_matrix_lm.shape[-2]:  # Check text dim
                return {
                    "lm_score": 0.0,
                    "dit_score": 0.0,
                    "success": False,
                    "error": "Lyrics indices out of bounds"
                }

            pure_matrix_lm = all_layers_matrix_lm[..., start_idx:end_idx, :]
            pure_matrix_dit = all_layers_matrix_dit[..., start_idx:end_idx, :]

            # Create aligner and calculate alignment info
            aligner = MusicLyricScorer(self.text_tokenizer)

            def calculate_single_score(matrix):
                """Helper to run aligner on a matrix"""
                info = aligner.lyrics_alignment_info(
                    attention_matrix=matrix,
                    token_ids=pure_lyric_ids,
                    custom_config=custom_layers_config,
                    return_matrices=False,
                    medfilt_width=1,
                )
                if info.get("energy_matrix") is None:
                    return 0.0

                res = aligner.calculate_score(
                    energy_matrix=info["energy_matrix"],
                    type_mask=info["type_mask"],
                    path_coords=info["path_coords"],
                )
                # Return the final score (check return key)
                return res.get("lyrics_score", res.get("final_score", 0.0))

            lm_score = calculate_single_score(pure_matrix_lm)
            dit_score = calculate_single_score(pure_matrix_dit)

            return {
                "lm_score": lm_score,
                "dit_score": dit_score,
                "success": True,
                "error": None
            }

        except Exception as e:
            error_msg = f"Error generating score: {str(e)}"
            logger.exception("[get_lyric_score] Failed")
            return {
                "lm_score": 0.0,
                "dit_score": 0.0,
                "success": False,
                "error": error_msg
            }
