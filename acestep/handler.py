"""
Business Logic Handler
Encapsulates all data processing and business logic as a bridge between model and UI
"""
import os
import sys

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
import threading
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
from acestep.constants import DEFAULT_DIT_INSTRUCTION, SFT_GEN_PROMPT, TASK_INSTRUCTIONS
from acestep.core.generation.handler import (
    AudioCodesMixin,
    BatchPrepMixin,
    DiffusionMixin,
    InitServiceMixin,
    IoAudioMixin,
    LoraManagerMixin,
    MemoryUtilsMixin,
    MetadataMixin,
    PaddingMixin,
    ProgressMixin,
    PromptMixin,
    TaskUtilsMixin,
)
from acestep.dit_alignment_score import MusicStampsAligner, MusicLyricScorer
from acestep.gpu_config import get_gpu_memory_gb, get_global_gpu_config, get_effective_free_vram_gb


warnings.filterwarnings("ignore")


class AceStepHandler(
    DiffusionMixin,
    AudioCodesMixin,
    BatchPrepMixin,
    IoAudioMixin,
    InitServiceMixin,
    LoraManagerMixin,
    MemoryUtilsMixin,
    MetadataMixin,
    PaddingMixin,
    ProgressMixin,
    PromptMixin,
    TaskUtilsMixin,
):
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
        self.disable_tqdm = os.environ.get("ACESTEP_DISABLE_TQDM", "").lower() in ("1", "true", "yes") or not getattr(sys.stderr, 'isatty', lambda: False)()
        self.debug_stats = os.environ.get("ACESTEP_DEBUG_STATS", "").lower() in ("1", "true", "yes")
        self._last_diffusion_per_step_sec: Optional[float] = None
        self._progress_estimates_lock = threading.Lock()
        self._progress_estimates = {"records": []}
        self._progress_estimates_path = os.path.join(
            self._get_project_root(),
            ".cache",
            "acestep",
            "progress_estimates.json",
        )
        self._load_progress_estimates()
        self.last_init_params = None
        
        # Quantization state - tracks if model is quantized (int8_weight_only, fp8_weight_only, or w8a8_dynamic)
        # Populated during initialize_service, remains None if quantization is disabled
        self.quantization = None
        
        # LoRA state
        self.lora_loaded = False
        self.use_lora = False
        self.lora_scale = 1.0  # LoRA influence scale (0-1), mirrors active adapter's scale
        self._base_decoder = None  # Backup of original decoder state_dict (CPU) for memory efficiency
        self._active_loras = {}  # adapter_name -> scale (per-adapter)
        self._lora_adapter_registry = {}  # adapter_name -> explicit scaling targets
        self._lora_active_adapter = None

        # MLX DiT acceleration (macOS Apple Silicon only)
        self.mlx_decoder = None
        self.use_mlx_dit = False

        # MLX VAE acceleration (macOS Apple Silicon only)
        self.mlx_vae = None
        self.use_mlx_vae = False

    # ------------------------------------------------------------------
    # MLX DiT acceleration helpers
    # ------------------------------------------------------------------
    def _init_mlx_dit(self) -> bool:
        """Try to initialize the native MLX DiT decoder for Apple Silicon.

        Returns True on success, False on failure (non-fatal).
        """
        try:
            from acestep.mlx_dit import mlx_available
            if not mlx_available():
                logger.info("[MLX-DiT] MLX not available on this platform; skipping.")
                return False

            from acestep.mlx_dit.model import MLXDiTDecoder
            from acestep.mlx_dit.convert import convert_and_load

            mlx_decoder = MLXDiTDecoder.from_config(self.config)
            convert_and_load(self.model, mlx_decoder)
            self.mlx_decoder = mlx_decoder
            self.use_mlx_dit = True
            logger.info("[MLX-DiT] Native MLX DiT decoder initialized successfully.")
            return True
        except Exception as exc:
            logger.warning(f"[MLX-DiT] Failed to initialize MLX decoder (non-fatal): {exc}")
            self.mlx_decoder = None
            self.use_mlx_dit = False
            return False
    
    # ------------------------------------------------------------------
    # MLX VAE acceleration helpers
    # ------------------------------------------------------------------
    def _init_mlx_vae(self) -> bool:
        """Try to initialize the native MLX VAE for Apple Silicon.

        Converts the PyTorch ``AutoencoderOobleck`` weights into a pure-MLX
        re-implementation.  The PyTorch VAE is kept as a fallback.

        Performance optimizations applied:
        - Float16 inference: ~2x throughput from doubled memory bandwidth
          on Apple Silicon.  Snake1d uses mixed precision internally.
          Set ACESTEP_MLX_VAE_FP16=1 to enable float16 inference.
        - mx.compile(): kernel fusion reduces Metal dispatch overhead and
          improves data locality (used by mlx-lm, vllm-mlx, mlx-audio).

        Returns True on success, False on failure (non-fatal).
        """
        try:
            from acestep.mlx_vae import mlx_available
            if not mlx_available():
                logger.info("[MLX-VAE] MLX not available on this platform; skipping.")
            return False

            import os
            import mlx.core as mx
            from mlx.utils import tree_map
            from acestep.mlx_vae.model import MLXAutoEncoderOobleck
            from acestep.mlx_vae.convert import convert_and_load

            mlx_vae = MLXAutoEncoderOobleck.from_pytorch_config(self.vae)
            convert_and_load(self.vae, mlx_vae)

            # --- Float16 conversion for faster inference ---
            # NOTE: Float16 causes audible quality degradation in the Oobleck
            # VAE decoder (the Snake activation and ConvTranspose1d chain
            # amplify rounding errors).  Default to float32 for quality.
            # Set ACESTEP_MLX_VAE_FP16=1 to enable float16 inference.
            use_fp16 = os.environ.get("ACESTEP_MLX_VAE_FP16", "0").lower() in (
                "1", "true", "yes",
            )
            vae_dtype = mx.float16 if use_fp16 else mx.float32

            if use_fp16:
                try:
                    def _to_fp16(x):
                        if isinstance(x, mx.array) and mx.issubdtype(x.dtype, mx.floating):
                            return x.astype(mx.float16)
                        return x
                    mlx_vae.update(tree_map(_to_fp16, mlx_vae.parameters()))
                    mx.eval(mlx_vae.parameters())
                    logger.info("[MLX-VAE] Model weights converted to float16.")
                except Exception as e:
                    logger.warning(f"[MLX-VAE] Float16 conversion failed ({e}); using float32.")
                    vae_dtype = mx.float32

            # --- Compile decode / encode for kernel fusion ---
            try:
                self._mlx_compiled_decode = mx.compile(mlx_vae.decode)
                self._mlx_compiled_encode_sample = mx.compile(mlx_vae.encode_and_sample)
                logger.info("[MLX-VAE] Decode/encode compiled with mx.compile().")
            except Exception as e:
                logger.warning(f"[MLX-VAE] mx.compile() failed ({e}); using uncompiled path.")
                self._mlx_compiled_decode = mlx_vae.decode
                self._mlx_compiled_encode_sample = mlx_vae.encode_and_sample

            self.mlx_vae = mlx_vae
            self.use_mlx_vae = True
            self._mlx_vae_dtype = vae_dtype
            logger.info(
                f"[MLX-VAE] Native MLX VAE initialized "
                f"(dtype={vae_dtype}, compiled=True)."
            )
            return True
        except Exception as exc:
            logger.warning(f"[MLX-VAE] Failed to initialize MLX VAE (non-fatal): {exc}")
            self.mlx_vae = None
            self.use_mlx_vae = False
            return False

    def _mlx_vae_decode(self, latents_torch):
        """Decode latents using native MLX VAE.
        
        Args:
            latents_torch: PyTorch tensor [B, C, T] (NCL format).
            
        Returns:
            PyTorch tensor [B, C_audio, T_audio] (NCL format).
        """
        import numpy as np
        import mlx.core as mx
        import time as _time

        t_start = _time.time()

        latents_np = latents_torch.detach().cpu().float().numpy()
        latents_nlc = np.transpose(latents_np, (0, 2, 1))  # NCL -> NLC

        B = latents_nlc.shape[0]
        T = latents_nlc.shape[1]

        # Convert to model dtype (float16 for speed, float32 fallback)
        vae_dtype = getattr(self, '_mlx_vae_dtype', mx.float32)
        latents_mx = mx.array(latents_nlc).astype(vae_dtype)

        t_convert = _time.time()

        # Use compiled decode (kernel-fused) when available
        decode_fn = getattr(self, '_mlx_compiled_decode', self.mlx_vae.decode)

        # Process batch items sequentially (peak memory stays constant)
        audio_parts = []
        for b in range(B):
            single = latents_mx[b : b + 1]  # [1, T, C]
            decoded = self._mlx_decode_single(single, decode_fn=decode_fn)
            # Cast back to float32 for downstream torch compatibility
            if decoded.dtype != mx.float32:
                decoded = decoded.astype(mx.float32)
            mx.eval(decoded)
            audio_parts.append(np.array(decoded))
            mx.clear_cache()  # Free intermediate buffers between samples

        t_decode = _time.time()

        audio_nlc = np.concatenate(audio_parts, axis=0)  # [B, T_audio, C_audio]
        audio_ncl = np.transpose(audio_nlc, (0, 2, 1))   # NLC -> NCL

        t_elapsed = _time.time() - t_start
        logger.info(
            f"[MLX-VAE] Decoded {B} sample(s), {T} latent frames -> "
            f"audio in {t_elapsed:.2f}s "
            f"(convert={t_convert - t_start:.3f}s, decode={t_decode - t_convert:.2f}s, "
            f"dtype={vae_dtype})"
        )

        return torch.from_numpy(audio_ncl)

    def _mlx_decode_single(self, z_nlc, decode_fn=None):
        """Decode a single sample with optional tiling for very long sequences.

        Args:
            z_nlc: MLX array [1, T, C] in NLC format.
            decode_fn: Compiled or plain decode callable.  Falls back to
                       ``self._mlx_compiled_decode`` or ``self.mlx_vae.decode``.
        
        Returns:
            MLX array [1, T_audio, C_audio] in NLC format.
        """
        import mlx.core as mx

        if decode_fn is None:
            decode_fn = getattr(self, '_mlx_compiled_decode', self.mlx_vae.decode)

        T = z_nlc.shape[1]
        # MLX unified memory: much larger chunk OK than PyTorch MPS.
        # 2048 latent frames ≈ 87 seconds of audio — covers nearly all use cases.
        MLX_CHUNK = 2048
        MLX_OVERLAP = 64

        if T <= MLX_CHUNK:
            # No tiling needed — caller handles mx.eval()
            return decode_fn(z_nlc)

        # Overlap-discard tiling for very long sequences
        stride = MLX_CHUNK - 2 * MLX_OVERLAP
        num_steps = math.ceil(T / stride)
        decoded_parts = []
        upsample_factor = None

        for i in tqdm(range(num_steps), desc="Decoding audio chunks", disable=self.disable_tqdm):
            core_start = i * stride
            core_end = min(core_start + stride, T)
            win_start = max(0, core_start - MLX_OVERLAP)
            win_end = min(T, core_end + MLX_OVERLAP)

            chunk = z_nlc[:, win_start:win_end, :]
            audio_chunk = decode_fn(chunk)
            mx.eval(audio_chunk)

            if upsample_factor is None:
                upsample_factor = audio_chunk.shape[1] / chunk.shape[1]

            added_start = core_start - win_start
            trim_start = int(round(added_start * upsample_factor))
            added_end = win_end - core_end
            trim_end = int(round(added_end * upsample_factor))

            audio_len = audio_chunk.shape[1]
            end_idx = audio_len - trim_end if trim_end > 0 else audio_len
            decoded_parts.append(audio_chunk[:, trim_start:end_idx, :])

        return mx.concatenate(decoded_parts, axis=1)

    def _mlx_vae_encode_sample(self, audio_torch):
        """Encode audio and sample latent using native MLX VAE.
        
        Args:
            audio_torch: PyTorch tensor [B, C, S] (NCL format).
            
        Returns:
            PyTorch tensor [B, C_latent, T_latent] (NCL format).
        """
        import numpy as np
        import mlx.core as mx
        import time as _time

        audio_np = audio_torch.detach().cpu().float().numpy()
        audio_nlc = np.transpose(audio_np, (0, 2, 1))  # NCL -> NLC

        B = audio_nlc.shape[0]
        S = audio_nlc.shape[1]

        # Determine total work units for progress bar
        MLX_ENCODE_CHUNK = 48000 * 30
        MLX_ENCODE_OVERLAP = 48000 * 2
        if S <= MLX_ENCODE_CHUNK:
            chunks_per_sample = 1
        else:
            stride = MLX_ENCODE_CHUNK - 2 * MLX_ENCODE_OVERLAP
            chunks_per_sample = math.ceil(S / stride)
        total_work = B * chunks_per_sample

        t_start = _time.time()

        # Convert to model dtype (float16 for speed)
        vae_dtype = getattr(self, '_mlx_vae_dtype', mx.float32)
        # Use compiled encode when available
        encode_fn = getattr(self, '_mlx_compiled_encode_sample', self.mlx_vae.encode_and_sample)

        latent_parts = []
        pbar = tqdm(
            total=total_work,
            desc=f"MLX VAE Encode (native, n={B})",
            disable=self.disable_tqdm,
            unit="chunk",
        )
        for b in range(B):
            single = mx.array(audio_nlc[b : b + 1])  # [1, S, C_audio]
            if single.dtype != vae_dtype:
                single = single.astype(vae_dtype)
            latent = self._mlx_encode_single(single, pbar=pbar, encode_fn=encode_fn)
            # Cast back to float32 for downstream torch compatibility
            if latent.dtype != mx.float32:
                latent = latent.astype(mx.float32)
            mx.eval(latent)
            latent_parts.append(np.array(latent))
            mx.clear_cache()
        pbar.close()

        t_elapsed = _time.time() - t_start
        logger.info(
            f"[MLX-VAE] Encoded {B} sample(s), {S} audio frames -> "
            f"latent in {t_elapsed:.2f}s (dtype={vae_dtype})"
        )

        latent_nlc = np.concatenate(latent_parts, axis=0)  # [B, T, C_latent]
        latent_ncl = np.transpose(latent_nlc, (0, 2, 1))   # NLC -> NCL
        return torch.from_numpy(latent_ncl)

    def _mlx_encode_single(self, audio_nlc, pbar=None, encode_fn=None):
        """Encode a single audio sample with optional tiling.
        
        Args:
            audio_nlc: MLX array [1, S, C_audio] in NLC format.
            pbar: Optional tqdm progress bar to update.
            encode_fn: Compiled or plain encode callable.  Falls back to
                       ``self._mlx_compiled_encode_sample`` or
                       ``self.mlx_vae.encode_and_sample``.
            
        Returns:
            MLX array [1, T_latent, C_latent] in NLC format.
        """
        import mlx.core as mx

        if encode_fn is None:
            encode_fn = getattr(
                self, '_mlx_compiled_encode_sample', self.mlx_vae.encode_and_sample,
            )

        S = audio_nlc.shape[1]
        # ~30 sec at 48 kHz (generous for MLX unified memory)
        MLX_ENCODE_CHUNK = 48000 * 30
        MLX_ENCODE_OVERLAP = 48000 * 2

        if S <= MLX_ENCODE_CHUNK:
            result = encode_fn(audio_nlc)
            mx.eval(result)
            if pbar is not None:
                pbar.update(1)
            return result

        # Overlap-discard tiling
        stride = MLX_ENCODE_CHUNK - 2 * MLX_ENCODE_OVERLAP
        num_steps = math.ceil(S / stride)
        encoded_parts = []
        downsample_factor = None

        for i in range(num_steps):
            core_start = i * stride
            core_end = min(core_start + stride, S)
            win_start = max(0, core_start - MLX_ENCODE_OVERLAP)
            win_end = min(S, core_end + MLX_ENCODE_OVERLAP)

            chunk = audio_nlc[:, win_start:win_end, :]
            latent_chunk = encode_fn(chunk)
            mx.eval(latent_chunk)

            if downsample_factor is None:
                downsample_factor = chunk.shape[1] / latent_chunk.shape[1]

            added_start = core_start - win_start
            trim_start = int(round(added_start / downsample_factor))
            added_end = win_end - core_end
            trim_end = int(round(added_end / downsample_factor))

            latent_len = latent_chunk.shape[1]
            end_idx = latent_len - trim_end if trim_end > 0 else latent_len
            encoded_parts.append(latent_chunk[:, trim_start:end_idx, :])

            if pbar is not None:
                pbar.update(1)

        return mx.concatenate(encoded_parts, axis=1)
    
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
        use_mlx_dit: bool = True,
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
            if config_path is None:
                config_path = "acestep-v15-turbo"
                logger.warning(
                    "[initialize_service] config_path not set; defaulting to 'acestep-v15-turbo'."
                )
            if device == "auto":
                if torch.cuda.is_available():
                    device = "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    device = "mps"
                elif hasattr(torch, 'xpu') and torch.xpu.is_available():
                    device = "xpu"
                else:
                    device = "cpu"
            elif device == "cuda" and not torch.cuda.is_available():
                if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    logger.warning("[initialize_service] CUDA requested but unavailable. Falling back to MPS.")
                    device = "mps"
                elif hasattr(torch, 'xpu') and torch.xpu.is_available():
                    logger.warning("[initialize_service] CUDA requested but unavailable. Falling back to XPU.")
                    device = "xpu"
                else:
                    logger.warning("[initialize_service] CUDA requested but unavailable. Falling back to CPU.")
                    device = "cpu"
            elif device == "mps" and not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
                if torch.cuda.is_available():
                    logger.warning("[initialize_service] MPS requested but unavailable. Falling back to CUDA.")
                    device = "cuda"
                elif hasattr(torch, 'xpu') and torch.xpu.is_available():
                    logger.warning("[initialize_service] MPS requested but unavailable. Falling back to XPU.")
                    device = "xpu"
                else:
                    logger.warning("[initialize_service] MPS requested but unavailable. Falling back to CPU.")
                    device = "cpu"
            elif device == "xpu" and not (hasattr(torch, 'xpu') and torch.xpu.is_available()):
                if torch.cuda.is_available():
                    logger.warning("[initialize_service] XPU requested but unavailable. Falling back to CUDA.")
                    device = "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    logger.warning("[initialize_service] XPU requested but unavailable. Falling back to MPS.")
                    device = "mps"
                else:
                    logger.warning("[initialize_service] XPU requested but unavailable. Falling back to CPU.")
                    device = "cpu"

            status_msg = ""
            
            self.device = device
            self.offload_to_cpu = offload_to_cpu
            self.offload_dit_to_cpu = offload_dit_to_cpu
            
            # MPS safety: torch.compile and torchao quantization are not supported on MPS
            if device == "mps":
                if compile_model:
                    logger.warning("[initialize_service] torch.compile is not supported on MPS — disabling.")
                    compile_model = False
                if quantization is not None:
                    logger.warning("[initialize_service] Quantization (torchao) is not supported on MPS — disabling.")
                    quantization = None
            
            self.compiled = compile_model
            # Set dtype based on device: bf16 for CUDA/XPU, fp32 for MPS/CPU
            # MPS does not support bfloat16 natively, and converting bfloat16-trained
            # weights to float16 causes NaN/Inf due to the narrower exponent range.
            # Use float32 on MPS for numerical stability.
            if device in ["cuda", "xpu"]:
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
            if config_path == "":
                logger.warning(
                    "[initialize_service] Empty config_path; pass None to use the default model."
                )
            if not check_model_exists(config_path, checkpoint_path):
                logger.info(f"[initialize_service] DiT model '{config_path}' not found, starting auto-download...")
                success, msg = ensure_dit_model(config_path, checkpoint_path, prefer_source=prefer_source)
                if not success:
                    return f"❌ Failed to download DiT model '{config_path}': {msg}", False
                logger.info(f"[initialize_service] {msg}")

            # Check if model code files are up-to-date with GitHub repo versions
            from acestep.model_downloader import _check_code_mismatch, _sync_model_code_files
            mismatched = _check_code_mismatch(config_path, checkpoint_path)
            if mismatched:
                logger.warning(
                    f"[initialize_service] Model code mismatch detected for '{config_path}': "
                    f"{mismatched}. Auto-syncing from acestep/models/..."
                )
                _sync_model_code_files(config_path, checkpoint_path)
                logger.info(f"[initialize_service] Model code files synced successfully.")

            # 1. Load main model
            # config_path is relative path (e.g., "acestep-v15-turbo"), concatenate to checkpoints directory
            acestep_v15_checkpoint_path = os.path.join(checkpoint_dir, config_path)
            if os.path.exists(acestep_v15_checkpoint_path):
                # Force CUDA cleanup before loading DiT to reduce fragmentation on model/mode switch
                if torch.cuda.is_available():
                    if getattr(self, "model", None) is not None:
                        del self.model
                        self.model = None
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()

                # Determine attention implementation, then fall back safely.
                if use_flash_attention and self.is_flash_attention_available(device):
                    attn_implementation = "flash_attention_2"
                else:
                    if use_flash_attention:
                        logger.warning(
                            f"[initialize_service] Flash attention requested but unavailable for device={device}. "
                            "Falling back to SDPA."
                        )
                    attn_implementation = "sdpa"

                attn_candidates = [attn_implementation]
                if "sdpa" not in attn_candidates:
                    attn_candidates.append("sdpa")
                if "eager" not in attn_candidates:
                    attn_candidates.append("eager")

                last_attn_error = None
                self.model = None
                for candidate in attn_candidates:
                    try:
                        logger.info(f"[initialize_service] Attempting to load model with attention implementation: {candidate}")
                        self.model = AutoModel.from_pretrained(
                            acestep_v15_checkpoint_path,
                            trust_remote_code=True,
                            attn_implementation=candidate,
                            torch_dtype=self.dtype,
                        )
                        attn_implementation = candidate
                        break
                    except Exception as e:
                        last_attn_error = e
                        logger.warning(f"[initialize_service] Failed to load model with {candidate}: {e}")

                if self.model is None:
                    raise RuntimeError(
                        f"Failed to load model with attention implementations {attn_candidates}: {last_attn_error}"
                    ) from last_attn_error

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
                        from torchao.quantization.quant_api import _is_linear
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
                        
                        # Only quantize DiT layers; exclude tokenizer and detokenizer submodules.
                        # The tokenizer (ResidualFSQ) and detokenizer contain small Linear layers
                        # that are used for audio code decoding. Quantizing them causes device
                        # mismatch errors during CPU↔GPU offloading because some torchao versions
                        # don't fully support .to(device) on AffineQuantizedTensor, and these
                        # layers are too small to benefit from quantization anyway.
                        def _dit_filter_fn(module, fqn):
                            if not _is_linear(module, fqn):
                                return False
                            # Exclude tokenizer/detokenizer (including via _orig_mod prefix from torch.compile)
                            for part in fqn.split("."):
                                if part in ("tokenizer", "detokenizer"):
                                    return False
                            return True
                        
                        quantize_(self.model, quant_config, filter_fn=_dit_filter_fn)
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

            # Try to initialize native MLX DiT for Apple Silicon acceleration
            mlx_dit_status = "Disabled"
            if use_mlx_dit and device in ("mps", "cpu") and not compile_model:
                mlx_ok = self._init_mlx_dit()
                mlx_dit_status = "Active (native MLX)" if mlx_ok else "Unavailable (PyTorch fallback)"
            elif not use_mlx_dit:
                mlx_dit_status = "Disabled by user"
                self.mlx_decoder = None
                self.use_mlx_dit = False

            # Try to initialize native MLX VAE for Apple Silicon acceleration
            mlx_vae_status = "Disabled"
            if device in ("mps", "cpu") and not compile_model:
                mlx_vae_ok = self._init_mlx_vae()
                mlx_vae_status = "Active (native MLX)" if mlx_vae_ok else "Unavailable (PyTorch fallback)"
            else:
                self.mlx_vae = None
                self.use_mlx_vae = False
            
            status_msg = f"✅ Model initialized successfully on {device}\n"
            status_msg += f"Main model: {acestep_v15_checkpoint_path}\n"
            status_msg += f"VAE: {vae_checkpoint_path}\n"
            status_msg += f"Text encoder: {text_encoder_path}\n"
            status_msg += f"Dtype: {self.dtype}\n"
            status_msg += f"Attention: {actual_attn}\n"
            status_msg += f"Compiled: {compile_model}\n"
            status_msg += f"Offload to CPU: {self.offload_to_cpu}\n"
            status_msg += f"Offload DiT to CPU: {self.offload_dit_to_cpu}\n"
            status_msg += f"MLX DiT: {mlx_dit_status}\n"
            status_msg += f"MLX VAE: {mlx_vae_status}"

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
                "use_mlx_dit": use_mlx_dit,
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
        cover_noise_strength: float = 0.0,
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
                    refer_audio_list[idx] = refer_audio_list[idx].to(self.device).to(self._get_vae_dtype())
            elif isinstance(refer_audio_list, torch.Tensor):
                refer_audios[ii] = refer_audios[ii].to(self.device)
        
        if vocal_languages is None:
            vocal_languages = self._create_fallback_vocal_languages(batch_size)
        
        # Parse metas with fallbacks
        parsed_metas = self._parse_metas(metas)
        
        # Encode target_wavs to get target_latents
        with torch.inference_mode():
            target_latents_list = []
            latent_lengths = []
            # Use per-item wavs (may be adjusted if audio_code_hints are provided)
            target_wavs_list = [target_wavs[i].clone() for i in range(batch_size)]
            if target_wavs.device != self.device:
                target_wavs = target_wavs.to(self.device)
            
            with self._load_model_context("vae"):
                # Detect whether all non-code-hint, non-silent batch items
                # share the same audio content (e.g. cover task where every
                # item comes from the same processed_src_audio).  If so, we
                # VAE-encode only once and reuse the latent for all of them.
                _cached_wav_ref: Optional[torch.Tensor] = None   # first encoded wav (on device)
                _cached_latent: Optional[torch.Tensor] = None    # its VAE latent

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
                        # Check if this wav is identical to a previously encoded
                        # one so we can skip the expensive VAE encode.
                        if (_cached_wav_ref is not None
                                and _cached_latent is not None
                                and _cached_wav_ref.shape == current_wav.shape
                                and torch.equal(_cached_wav_ref, current_wav)):
                            logger.info(f"[generate_music] Reusing cached VAE latents for item {i} (same audio as previous item)")
                            target_latent = _cached_latent.clone()
                        else:
                            # Encode using helper method
                            logger.info(f"[generate_music] Encoding target audio to latents for item {i}...")
                            target_latent = self._encode_audio_to_latents(current_wav.squeeze(0))  # Remove batch dim for helper
                            # Cache for potential reuse by subsequent items
                            _cached_wav_ref = current_wav
                            _cached_latent = target_latent
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
                logger.info(f"{'='*70}")
                logger.info(f"lyrics_text:\n{self._format_lyrics(lyrics[i], actual_language)}")
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

        # Cache for VAE-encoded refer audio latents keyed by data_ptr to avoid
        # redundant encodes when the same reference audio is shared across batch
        # items (e.g. user uploads one reference audio with batch_size > 1).
        _refer_encode_cache: Dict[int, torch.Tensor] = {}

        for batch_idx, refer_audios in enumerate(refer_audioss):
            if len(refer_audios) == 1 and torch.all(refer_audios[0] == 0.0):
                refer_audio_latent = _ensure_latent_3d(self.silence_latent[:, :750, :])
                refer_audio_latents.append(refer_audio_latent)
                refer_audio_order_mask.append(batch_idx)
            else:
                for refer_audio in refer_audios:
                    cache_key = refer_audio.data_ptr()
                    if cache_key in _refer_encode_cache:
                        # Reuse cached latent for identical reference audio
                        refer_audio_latent = _refer_encode_cache[cache_key].clone()
                    else:
                        refer_audio = _normalize_audio_2d(refer_audio)
                        # Use tiled_encode for memory-efficient encoding of long audio
                        with torch.inference_mode():
                            refer_audio_latent = self.tiled_encode(refer_audio, offload_latent_to_cpu=True)
                        # Move to device and cast to model dtype
                        refer_audio_latent = refer_audio_latent.to(self.device).to(self.dtype)
                        # Ensure 3D before transpose: [C, T] -> [1, C, T] -> [1, T, C]
                        if refer_audio_latent.dim() == 2:
                            refer_audio_latent = refer_audio_latent.unsqueeze(0)
                        refer_audio_latent = _ensure_latent_3d(refer_audio_latent.transpose(1, 2))
                        _refer_encode_cache[cache_key] = refer_audio_latent
                    refer_audio_latents.append(refer_audio_latent)
                    refer_audio_order_mask.append(batch_idx)

        refer_audio_latents = torch.cat(refer_audio_latents, dim=0)
        refer_audio_order_mask = torch.tensor(refer_audio_order_mask, device=self.device, dtype=torch.long)
        return refer_audio_latents, refer_audio_order_mask

    def infer_text_embeddings(self, text_token_idss):
        with torch.inference_mode():
            text_embeddings = self.text_encoder(input_ids=text_token_idss, lyric_attention_mask=None).last_hidden_state
        return text_embeddings

    def infer_lyric_embeddings(self, lyric_token_ids):
        with torch.inference_mode():
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
    
    @torch.inference_mode()
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
        cover_noise_strength: float = 0.0,
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
            cover_noise_strength: Strength of cover noise init (0=pure noise, 1=closest to src audio) (default: 0.0)
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

        # Normalize lyrics to match batch size (so conditioning always has caption + lyric per item, including repaint)
        if len(lyrics) < batch_size:
            fill = lyrics[-1] if lyrics else ""
            lyrics = list(lyrics) + [fill] * (batch_size - len(lyrics))
        elif len(lyrics) > batch_size:
            lyrics = lyrics[:batch_size]

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
            cover_noise_strength=cover_noise_strength,
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
            "cover_noise_strength": cover_noise_strength,
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
            generate_kwargs["timesteps"] = torch.tensor(timesteps, dtype=torch.float32, device=self.device)
        dit_backend = "MLX (native)" if (self.use_mlx_dit and self.mlx_decoder is not None) else f"PyTorch ({self.device})"
        logger.info(f"[service_generate] Generating audio... (DiT backend: {dit_backend})")
        with torch.inference_mode():
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

                # ---- MLX fast-path for the diffusion loop ----
                if self.use_mlx_dit and self.mlx_decoder is not None:
                    try:
                        # For non-cover blend, prepare the non-cover conditions via PyTorch
                        enc_hs_nc, enc_am_nc, ctx_nc = None, None, None
                        if audio_cover_strength < 1.0 and non_cover_text_hidden_states is not None:
                            non_is_covers = torch.zeros_like(is_covers)
                            sil_exp = self.silence_latent[:, :src_latents.shape[1], :].expand(
                                src_latents.shape[0], -1, -1
                            )
                            enc_hs_nc, enc_am_nc, ctx_nc = self.model.prepare_condition(
                                text_hidden_states=non_cover_text_hidden_states,
                                text_attention_mask=non_cover_text_attention_masks,
                                lyric_hidden_states=lyric_hidden_states,
                                lyric_attention_mask=lyric_attention_mask,
                                refer_audio_acoustic_hidden_states_packed=refer_audio_acoustic_hidden_states_packed,
                                refer_audio_order_mask=refer_audio_order_mask,
                                hidden_states=sil_exp,
                                attention_mask=torch.ones(
                                    sil_exp.shape[0], sil_exp.shape[1],
                                    device=sil_exp.device, dtype=sil_exp.dtype,
                                ),
                                silence_latent=self.silence_latent,
                                src_latents=sil_exp,
                                chunk_masks=chunk_mask,
                                is_covers=non_is_covers,
                            )

                        ts_arg = generate_kwargs.get("timesteps")
                        outputs = self._mlx_run_diffusion(
                            encoder_hidden_states=encoder_hidden_states,
                            encoder_attention_mask=encoder_attention_mask,
                            context_latents=context_latents,
                            src_latents=src_latents,
                            seed=seed_param,
                            infer_method=infer_method,
                            shift=shift,
                            timesteps=ts_arg,
                            audio_cover_strength=audio_cover_strength,
                            encoder_hidden_states_non_cover=enc_hs_nc,
                            encoder_attention_mask_non_cover=enc_am_nc,
                            context_latents_non_cover=ctx_nc,
                        )
                        _tc = outputs.get("time_costs", {})
                        _dt = _tc.get("diffusion_time_cost", 0)
                        _ps = _tc.get("diffusion_per_step_time_cost", 0)
                        logger.info(
                            f"[service_generate] DiT diffusion complete via MLX ({_dt:.2f}s total, {_ps:.3f}s/step)."
                        )
                    except Exception as exc:
                        logger.warning(
                            "[service_generate] MLX diffusion failed (%s); falling back to PyTorch.",
                            exc,
                        )
                        outputs = self.model.generate_audio(**generate_kwargs)
                else:
                    logger.info("[service_generate] DiT diffusion via PyTorch (%s)...", self.device)
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

    # MPS-safe chunk parameters (class-level for testability)
    _MPS_DECODE_CHUNK_SIZE = 32
    _MPS_DECODE_OVERLAP = 8

    def tiled_decode(self, latents, chunk_size: Optional[int] = None, overlap: int = 64, offload_wav_to_cpu: Optional[bool] = None):
        """
        Decode latents using tiling to reduce VRAM usage.
        Uses overlap-discard strategy to avoid boundary artifacts.
        
        Args:
            latents: [Batch, Channels, Length]
            chunk_size: Size of latent chunk to process at once (auto-tuned if None)
            overlap: Overlap size in latent frames
            offload_wav_to_cpu: If True, offload decoded wav audio to CPU immediately to save VRAM
        """
        # ---- MLX fast path (macOS Apple Silicon) ----
        if self.use_mlx_vae and self.mlx_vae is not None:
            try:
                result = self._mlx_vae_decode(latents)
                return result
            except Exception as exc:
                logger.warning(
                    f"[tiled_decode] MLX VAE decode failed ({type(exc).__name__}: {exc}), "
                    f"falling back to PyTorch VAE..."
                )

        # ---- PyTorch path (CUDA / MPS / CPU) ----
        if chunk_size is None:
            chunk_size = self._get_auto_decode_chunk_size()
        if offload_wav_to_cpu is None:
            offload_wav_to_cpu = self._should_offload_wav_to_cpu()
        
        logger.info(f"[tiled_decode] chunk_size={chunk_size}, offload_wav_to_cpu={offload_wav_to_cpu}, latents_shape={latents.shape}")
        
        # MPS Conv1d has a hard output-size limit that the OobleckDecoder
        # exceeds during temporal upsampling with large chunks.  Reduce
        # chunk_size to keep each VAE decode within the MPS kernel limits
        # while keeping computation on the fast MPS accelerator.
        _is_mps = (self.device == "mps")
        if _is_mps:
            _mps_chunk = self._MPS_DECODE_CHUNK_SIZE
            _mps_overlap = self._MPS_DECODE_OVERLAP
            _needs_reduction = (chunk_size > _mps_chunk) or (overlap > _mps_overlap)
            if _needs_reduction:
                logger.info(
                    f"[tiled_decode] VAE decode via PyTorch MPS; reducing chunk_size from {chunk_size} "
                    f"to {min(chunk_size, _mps_chunk)} and overlap from {overlap} "
                    f"to {min(overlap, _mps_overlap)} to avoid MPS conv output limit."
                )
                chunk_size = min(chunk_size, _mps_chunk)
                overlap = min(overlap, _mps_overlap)
        
        try:
            return self._tiled_decode_inner(latents, chunk_size, overlap, offload_wav_to_cpu)
        except (NotImplementedError, RuntimeError) as exc:
            if not _is_mps:
                raise  # only catch MPS-related errors
            # Safety fallback: if the MPS tiled path still fails (e.g. very
            # short latent that went through direct decode, or a future PyTorch
            # MPS regression), transparently retry on CPU.
            logger.warning(
                f"[tiled_decode] MPS decode failed ({type(exc).__name__}: {exc}), "
                f"falling back to CPU VAE decode..."
            )
            return self._tiled_decode_cpu_fallback(latents)

    def _tiled_decode_cpu_fallback(self, latents):
        """Last-resort CPU VAE decode when MPS fails unexpectedly."""
        _first_param = next(self.vae.parameters())
        vae_device = _first_param.device
        vae_dtype = _first_param.dtype
        try:
            self.vae = self.vae.cpu().float()
            latents_cpu = latents.to(device="cpu", dtype=torch.float32)
            decoder_output = self.vae.decode(latents_cpu)
            result = decoder_output.sample
            del decoder_output
            return result
        finally:
            # Always restore VAE to original device/dtype
            self.vae = self.vae.to(vae_dtype).to(vae_device)

    def _tiled_decode_inner(self, latents, chunk_size, overlap, offload_wav_to_cpu):
        """Core tiled decode logic (extracted for fallback wrapping)."""
        B, C, T = latents.shape
        
        # ---- Batch-sequential decode ----
        # VAE decode VRAM scales linearly with batch size.  On tight-VRAM GPUs
        # (e.g. 8 GB) decoding the whole batch at once can OOM.  Process one
        # sample at a time so peak VRAM stays constant regardless of batch size.
        if B > 1:
            logger.info(f"[tiled_decode] Batch size {B} > 1 — decoding samples sequentially to save VRAM")
            per_sample_results = []
            for b_idx in range(B):
                single = latents[b_idx : b_idx + 1]  # [1, C, T]
                decoded = self._tiled_decode_inner(single, chunk_size, overlap, offload_wav_to_cpu)
                # Move to CPU immediately to free GPU VRAM for next sample
                per_sample_results.append(decoded.cpu() if decoded.device.type != "cpu" else decoded)
                self._empty_cache()
            # Concatenate on CPU then move back if needed
            result = torch.cat(per_sample_results, dim=0)  # [B, channels, samples]
            if latents.device.type != "cpu" and not offload_wav_to_cpu:
                result = result.to(latents.device)
            return result
        
        # Adjust overlap for very small chunk sizes to ensure positive stride
        effective_overlap = overlap
        while chunk_size - 2 * effective_overlap <= 0 and effective_overlap > 0:
            effective_overlap = effective_overlap // 2
        if effective_overlap != overlap:
            logger.warning(f"[tiled_decode] Reduced overlap from {overlap} to {effective_overlap} for chunk_size={chunk_size}")
        overlap = effective_overlap
        
        # If short enough, decode directly
        if T <= chunk_size:
            try:
                decoder_output = self.vae.decode(latents)
                result = decoder_output.sample
                del decoder_output
                return result
            except torch.cuda.OutOfMemoryError:
                logger.warning("[tiled_decode] OOM on direct decode, falling back to CPU VAE decode")
                self._empty_cache()
                return self._decode_on_cpu(latents)

        # Calculate stride (core size)
        stride = chunk_size - 2 * overlap
        if stride <= 0:
            raise ValueError(f"chunk_size {chunk_size} must be > 2 * overlap {overlap}")
        
        num_steps = math.ceil(T / stride)
        
        if offload_wav_to_cpu:
            # Optimized path: offload wav to CPU immediately to save VRAM
            try:
                return self._tiled_decode_offload_cpu(latents, B, T, stride, overlap, num_steps)
            except torch.cuda.OutOfMemoryError:
                logger.warning(f"[tiled_decode] OOM during offload_cpu decode with chunk_size={chunk_size}, falling back to CPU VAE decode")
                self._empty_cache()
                return self._decode_on_cpu(latents)
        else:
            # Default path: keep everything on GPU
            try:
                return self._tiled_decode_gpu(latents, B, T, stride, overlap, num_steps)
            except torch.cuda.OutOfMemoryError:
                logger.warning(f"[tiled_decode] OOM during GPU decode with chunk_size={chunk_size}, falling back to CPU offload path")
                self._empty_cache()
                try:
                    return self._tiled_decode_offload_cpu(latents, B, T, stride, overlap, num_steps)
                except torch.cuda.OutOfMemoryError:
                    logger.warning("[tiled_decode] OOM even with offload path, falling back to full CPU VAE decode")
                    self._empty_cache()
                    return self._decode_on_cpu(latents)
    
    def _tiled_decode_gpu(self, latents, B, T, stride, overlap, num_steps):
        """Standard tiled decode keeping all data on GPU."""
        decoded_audio_list = []
        upsample_factor = None
        
        for i in tqdm(range(num_steps), desc="Decoding audio chunks", disable=self.disable_tqdm):
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
        for i in tqdm(range(1, num_steps), desc="Decoding audio chunks", disable=self.disable_tqdm):
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
    
    def _decode_on_cpu(self, latents):
        """
        Emergency fallback: move VAE to CPU, decode there, then restore.
        
        This is used when GPU VRAM is too tight for even the smallest tiled decode.
        Slower but guarantees no OOM on GPU.
        """
        logger.warning("[_decode_on_cpu] Moving VAE to CPU for decode (VRAM too tight for GPU decode)")
        
        # Remember original device
        try:
            original_device = next(self.vae.parameters()).device
        except StopIteration:
            original_device = torch.device("cpu")
        
        # Move VAE to CPU
        vae_cpu_dtype = self._get_vae_dtype("cpu")
        self._recursive_to_device(self.vae, "cpu", vae_cpu_dtype)
        self._empty_cache()
        
        # Move latents to CPU
        latents_cpu = latents.cpu().to(vae_cpu_dtype)
        
        # Decode on CPU (no tiling needed — CPU has plenty of RAM)
        try:
            with torch.inference_mode():
                decoder_output = self.vae.decode(latents_cpu)
                result = decoder_output.sample
                del decoder_output
        finally:
            # Restore VAE to original device
            if original_device.type != "cpu":
                vae_gpu_dtype = self._get_vae_dtype(str(original_device))
                self._recursive_to_device(self.vae, original_device, vae_gpu_dtype)
        
        logger.info(f"[_decode_on_cpu] CPU decode complete, result shape={result.shape}")
        return result  # result stays on CPU — fine for audio post-processing
    
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
        # ---- MLX fast path (macOS Apple Silicon) ----
        if self.use_mlx_vae and self.mlx_vae is not None:
            # Handle 2D input [Channels, Samples]
            input_was_2d = (audio.dim() == 2)
            if input_was_2d:
                audio = audio.unsqueeze(0)
            try:
                result = self._mlx_vae_encode_sample(audio)
                if input_was_2d:
                    result = result.squeeze(0)
                return result
            except Exception as exc:
                logger.warning(
                    f"[tiled_encode] MLX VAE encode failed ({type(exc).__name__}: {exc}), "
                    f"falling back to PyTorch VAE..."
                )
                if input_was_2d:
                    audio = audio.squeeze(0)

        # ---- PyTorch path (CUDA / MPS / CPU) ----
        # Default values for 48kHz audio, adaptive to GPU memory
        if chunk_size is None:
            gpu_memory = get_gpu_memory_gb()
            if gpu_memory <= 0 and self.device == "mps":
                mem_gb = self._get_effective_mps_memory_gb()
                if mem_gb is not None:
                    gpu_memory = mem_gb
            if gpu_memory <= 8:
                chunk_size = 48000 * 15  # 15 seconds for low VRAM
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
            with torch.inference_mode():
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
        
        for i in tqdm(range(num_steps), desc="Encoding audio chunks", disable=self.disable_tqdm):
            # Core range in audio samples
            core_start = i * stride
            core_end = min(core_start + stride, S)
            
            # Window range (with overlap)
            win_start = max(0, core_start - overlap)
            win_end = min(S, core_end + overlap)
            
            # Extract chunk and move to GPU
            audio_chunk = audio[:, :, win_start:win_end].to(self.device).to(self.vae.dtype)
            
            # Encode
            with torch.inference_mode():
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
        with torch.inference_mode():
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
        for i in tqdm(range(1, num_steps), desc="Encoding audio chunks", disable=self.disable_tqdm):
            # Core range in audio samples
            core_start = i * stride
            core_end = min(core_start + stride, S)
            
            # Window range (with overlap)
            win_start = max(0, core_start - overlap)
            win_end = min(S, core_end + overlap)
            
            # Extract chunk and move to GPU
            audio_chunk = audio[:, :, win_start:win_end].to(self.device).to(self.vae.dtype)
            
            # Encode on GPU
            with torch.inference_mode():
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
        cover_noise_strength: float = 0.0,
        task_type: str = "text2music",
        use_adg: bool = False,
        cfg_interval_start: float = 0.0,
        cfg_interval_end: float = 1.0,
        shift: float = 1.0,
        infer_method: str = "ode",
        use_tiled_decode: bool = True,
        timesteps: Optional[List[float]] = None,
        latent_shift: float = 0.0,
        latent_rescale: float = 1.0,
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

        # ---- Pre-inference VRAM guard ----
        # Estimate whether the requested batch_size fits in free VRAM and
        # auto-reduce if it does not.  This prevents OOM crashes at the cost
        # of generating fewer samples.
        actual_batch_size = self._vram_guard_reduce_batch(
            actual_batch_size,
            audio_duration=audio_duration,
        )

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
            
            # Prepare audio_code_hints - use if audio_code_string is provided
            # This works for both text2music (auto-switched to cover) and cover tasks
            audio_code_hints_batch = None
            if _has_audio_codes(audio_code_string):
                if isinstance(audio_code_string, list):
                    audio_code_hints_batch = audio_code_string
                else:
                    audio_code_hints_batch = [audio_code_string] * actual_batch_size

            should_return_intermediate = (task_type == "text2music")
            progress_desc = f"Generating music (batch size: {actual_batch_size})..."
            infer_steps_for_progress = len(timesteps) if timesteps else inference_steps
            progress(0.52, desc=progress_desc)
            stop_event = None
            progress_thread = None
            try:
                stop_event, progress_thread = self._start_diffusion_progress_estimator(
                    progress=progress,
                    start=0.52,
                    end=0.79,
                    infer_steps=infer_steps_for_progress,
                    batch_size=actual_batch_size,
                    duration_sec=audio_duration if audio_duration and audio_duration > 0 else None,
                    desc=progress_desc,
                )
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
                    cover_noise_strength=cover_noise_strength,  # Pass cover noise strength
                    use_adg=use_adg,  # Pass use_adg parameter
                    cfg_interval_start=cfg_interval_start,  # Pass CFG interval start
                    cfg_interval_end=cfg_interval_end,  # Pass CFG interval end
                    shift=shift,  # Pass shift parameter
                    infer_method=infer_method,  # Pass infer method (ode or sde)
                    audio_code_hints=audio_code_hints_batch,  # Pass audio code hints as list
                    return_intermediate=should_return_intermediate,
                    timesteps=timesteps,  # Pass custom timesteps if provided
                )
            finally:
                if stop_event is not None:
                    stop_event.set()
                if progress_thread is not None:
                    progress_thread.join(timeout=1.0)
            
            logger.info("[generate_music] Model generation completed. Decoding latents...")
            pred_latents = outputs["target_latents"]  # [batch, latent_length, latent_dim]
            time_costs = outputs["time_costs"]
            time_costs["offload_time_cost"] = self.current_offload_cost
            per_step = time_costs.get("diffusion_per_step_time_cost")
            if isinstance(per_step, (int, float)) and per_step > 0:
                self._last_diffusion_per_step_sec = float(per_step)
                self._update_progress_estimate(
                    per_step_sec=float(per_step),
                    infer_steps=infer_steps_for_progress,
                    batch_size=actual_batch_size,
                    duration_sec=audio_duration if audio_duration and audio_duration > 0 else None,
                )
            if self.debug_stats:
                logger.debug(
                    f"[generate_music] pred_latents: {pred_latents.shape}, dtype={pred_latents.dtype} "
                    f"{pred_latents.min()=}, {pred_latents.max()=}, {pred_latents.mean()=} {pred_latents.std()=}"
                )
            else:
                logger.debug(f"[generate_music] pred_latents: {pred_latents.shape}, dtype={pred_latents.dtype}")
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
            
            # Apply latent shift and rescale before VAE decode (for anti-clipping control)
            if latent_shift != 0.0 or latent_rescale != 1.0:
                logger.info(f"[generate_music] Applying latent post-processing: shift={latent_shift}, rescale={latent_rescale}")
                if self.debug_stats:
                    logger.debug(f"[generate_music] Latent BEFORE shift/rescale: min={pred_latents.min():.4f}, max={pred_latents.max():.4f}, mean={pred_latents.mean():.4f}, std={pred_latents.std():.4f}")
                pred_latents = pred_latents * latent_rescale + latent_shift
                if self.debug_stats:
                    logger.debug(f"[generate_music] Latent AFTER shift/rescale: min={pred_latents.min():.4f}, max={pred_latents.max():.4f}, mean={pred_latents.mean():.4f}, std={pred_latents.std():.4f}")
            
            # Decode latents to audio
            start_time = time.time()
            with torch.inference_mode():
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
                    
                    # When native MLX VAE is active, bypass VRAM checks and CPU
                    # offload entirely — MLX uses unified memory, not PyTorch VRAM.
                    _using_mlx_vae = self.use_mlx_vae and self.mlx_vae is not None
                    _vae_cpu = False

                    if not _using_mlx_vae:
                        # Check effective free VRAM and auto-enable CPU decode if extremely tight
                        import os as _os
                        _vae_cpu = _os.environ.get("ACESTEP_VAE_ON_CPU", "0").lower() in ("1", "true", "yes")
                        if not _vae_cpu:
                            # MPS (Apple Silicon) uses unified memory — get_effective_free_vram_gb()
                            # relies on CUDA and always returns 0 on Mac, which would incorrectly
                            # force VAE decode onto the CPU.  Skip the auto-CPU logic for MPS.
                            if self.device == "mps":
                                logger.info("[generate_music] MPS device: skipping VRAM check (unified memory), keeping VAE on MPS")
                            else:
                                _effective_free = get_effective_free_vram_gb()
                                logger.info(f"[generate_music] Effective free VRAM before VAE decode: {_effective_free:.2f} GB")
                                # If less than 0.5 GB free, VAE decode on GPU will almost certainly OOM
                                if _effective_free < 0.5:
                                    logger.warning(f"[generate_music] Only {_effective_free:.2f} GB free VRAM — auto-enabling CPU VAE decode")
                                    _vae_cpu = True
                        if _vae_cpu:
                            logger.info("[generate_music] Moving VAE to CPU for decode (ACESTEP_VAE_ON_CPU=1)...")
                            _vae_device = next(self.vae.parameters()).device
                            self.vae = self.vae.cpu()
                            pred_latents_for_decode = pred_latents_for_decode.cpu()
                            self._empty_cache()
                    
                    if use_tiled_decode:
                        logger.info("[generate_music] Using tiled VAE decode to reduce VRAM usage...")
                        pred_wavs = self.tiled_decode(pred_latents_for_decode)  # [batch, channels, samples]
                    elif _using_mlx_vae:
                        # Direct decode via native MLX (no tiling needed)
                        try:
                            pred_wavs = self._mlx_vae_decode(pred_latents_for_decode)
                        except Exception as exc:
                            logger.warning(f"[generate_music] MLX direct decode failed ({exc}), falling back to PyTorch")
                            decoder_output = self.vae.decode(pred_latents_for_decode)
                            pred_wavs = decoder_output.sample
                            del decoder_output
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
                    
                    # Anti-clipping normalization: only scale if peak exceeds [-1, 1].
                    peak = pred_wavs.abs().amax(dim=[1, 2], keepdim=True)
                    if torch.any(peak > 1.0):
                        pred_wavs = pred_wavs / peak.clamp(min=1.0)
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
                audio_tensor = pred_wavs[i].cpu()
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

    @torch.inference_mode()
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

    @torch.inference_mode()
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
