"""
5Hz LM (Language Model) Handler
Handles all LM-related operations including initialization and generation
"""
import os
import sys
import traceback
import time
import random
import warnings
from typing import Optional, Dict, Any, Tuple, List, Union
from contextlib import contextmanager

import yaml
import torch
from loguru import logger
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers.generation.streamers import BaseStreamer
from transformers.generation.logits_process import (
    LogitsProcessorList,
    RepetitionPenaltyLogitsProcessor,
)
from acestep.constrained_logits_processor import MetadataConstrainedLogitsProcessor
from acestep.constants import DEFAULT_LM_INSTRUCTION, DEFAULT_LM_UNDERSTAND_INSTRUCTION, DEFAULT_LM_INSPIRED_INSTRUCTION, DEFAULT_LM_REWRITE_INSTRUCTION, DURATION_MIN, DURATION_MAX
from acestep.gpu_config import get_lm_gpu_memory_ratio, get_gpu_memory_gb, get_lm_model_size, get_global_gpu_config

# Minimum free VRAM (GB) required to attempt vLLM initialization.
# vLLM's KV cache allocator adapts to available memory, so we only need a
# basic sanity check — not a hard total-VRAM gate.
VRAM_SAFE_FREE_GB = 2.0


def _warn_if_prerelease_python():
    v = sys.version_info
    if getattr(v, "releaselevel", "final") != "final" and sys.platform.startswith("linux"):
        warnings.warn(
            f"Detected pre-release Python {sys.version.split()[0]} ({getattr(v, 'releaselevel', '')}). "
            "This is known to cause segmentation faults with vLLM/nano-vllm on Linux. "
            "Please install a stable Python release (e.g. 3.11.12+), or use --backend pt as a workaround.",
            RuntimeWarning,
            stacklevel=2,
        )


class LLMHandler:
    """5Hz LM Handler for audio code generation"""

    STOP_REASONING_TAG = "</think>"

    # HuggingFace Space environment detection
    IS_HUGGINGFACE_SPACE = os.environ.get("SPACE_ID") is not None

    def __init__(self, persistent_storage_path: Optional[str] = None):
        """Initialize LLMHandler with default values"""
        self.llm = None
        self.llm_tokenizer = None
        self.llm_initialized = False
        self.llm_backend = None
        self.max_model_len = 4096
        self.device = "cpu"
        self.dtype = torch.float32
        self.offload_to_cpu = False
        self.disable_tqdm = os.environ.get("ACESTEP_DISABLE_TQDM", "").lower() in ("1", "true", "yes") or not (hasattr(sys.stderr, 'isatty') and sys.stderr.isatty())

        # HuggingFace Space persistent storage support
        if persistent_storage_path is None and self.IS_HUGGINGFACE_SPACE:
            persistent_storage_path = "/data"
        self.persistent_storage_path = persistent_storage_path

        # Shared constrained decoding processor
        self.constrained_processor: Optional[MetadataConstrainedLogitsProcessor] = None

        # Shared HuggingFace model for perplexity calculation
        self._hf_model_for_scoring = None

        # MLX model reference (used when llm_backend == "mlx")
        self._mlx_model = None
        self._mlx_model_path = None

    def unload(self) -> None:
        """Release LM weights/tokenizer and clear caches to free memory."""
        try:
            if self.llm_backend == "vllm":
                try:
                    if hasattr(self.llm, "reset"):
                        self.llm.reset()
                except Exception:
                    pass
                self._cleanup_torch_distributed_state()
            self.llm = None
            self.llm_tokenizer = None
            self.constrained_processor = None
            self.llm_initialized = False
            self.llm_backend = None
            self._mlx_model = None
            self._mlx_model_path = None
            try:
                import gc
                gc.collect()
            except Exception:
                pass
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            elif hasattr(torch, "mps") and torch.backends.mps.is_available():
                if hasattr(torch.mps, "synchronize"):
                    torch.mps.synchronize()
                if hasattr(torch.mps, "empty_cache"):
                    torch.mps.empty_cache()
            elif hasattr(torch, "xpu") and torch.xpu.is_available():
                torch.xpu.empty_cache()
                torch.xpu.synchronize()
        except Exception:
            pass

    def _cleanup_torch_distributed_state(self) -> None:
        """Destroy default torch distributed process group when already initialized."""
        try:
            import torch.distributed as dist
            if dist.is_available() and dist.is_initialized():
                logger.warning("[LLM vLLM] Destroying stale default process group before/after vLLM lifecycle")
                dist.destroy_process_group()
        except Exception as exc:
            logger.warning(f"[LLM vLLM] Failed to clean torch distributed state: {exc}")

    def _get_checkpoint_dir(self) -> str:
        """Get checkpoint directory, prioritizing persistent storage"""
        if self.persistent_storage_path:
            return os.path.join(self.persistent_storage_path, "checkpoints")
        current_file = os.path.abspath(__file__)
        project_root = os.path.dirname(os.path.dirname(current_file))
        return os.path.join(project_root, "checkpoints")

    def get_available_5hz_lm_models(self) -> List[str]:
        """Scan and return all model directory names starting with 'acestep-5Hz-lm-'"""
        checkpoint_dir = self._get_checkpoint_dir()

        models = []
        if os.path.exists(checkpoint_dir):
            for item in os.listdir(checkpoint_dir):
                item_path = os.path.join(checkpoint_dir, item)
                if os.path.isdir(item_path) and item.startswith("acestep-5Hz-lm-"):
                    models.append(item)

        models.sort()
        return models

    def get_gpu_memory_utilization(self, model_path: str = None, minimal_gpu: float = 8, min_ratio: float = 0.2, max_ratio: float = 0.9) -> Tuple[float, bool]:
        """
        Get GPU memory utilization ratio based on LM model size and available GPU memory.

        Args:
            model_path: LM model path (e.g., "acestep-5Hz-lm-0.6B"). Used to determine target memory.
            minimal_gpu: Minimum GPU memory requirement in GB (fallback)
            min_ratio: Minimum memory utilization ratio
            max_ratio: Maximum memory utilization ratio

        Returns:
            Tuple of (gpu_memory_utilization_ratio, low_gpu_memory_mode)
        """
        try:
            device = torch.device("cuda:0")
            total_gpu_mem_bytes = torch.cuda.get_device_properties(device).total_memory
            total_gpu = total_gpu_mem_bytes / 1024**3

            low_gpu_memory_mode = False

            # Use adaptive GPU memory ratio based on model size
            if model_path:
                ratio, target_memory_gb = get_lm_gpu_memory_ratio(model_path, total_gpu)
                logger.info(f"Adaptive LM memory allocation: model={model_path}, target={target_memory_gb}GB, ratio={ratio:.3f}, total_gpu={total_gpu:.1f}GB")

                # Enable low memory mode for small GPUs
                if total_gpu < 8:
                    low_gpu_memory_mode = True

                return ratio, low_gpu_memory_mode

            # Fallback to original logic if no model_path provided
            reserved_mem_bytes = torch.cuda.memory_reserved(device)
            reserved_gpu = reserved_mem_bytes / 1024**3
            available_gpu = total_gpu - reserved_gpu

            if total_gpu < minimal_gpu:
                minimal_gpu = 0.5 * total_gpu
                low_gpu_memory_mode = True

            if available_gpu >= minimal_gpu:
                ratio = min(max_ratio, max(min_ratio, minimal_gpu / total_gpu))
            else:
                ratio = min(max_ratio, max(min_ratio, (available_gpu * 0.8) / total_gpu))

            return ratio, low_gpu_memory_mode
        except Exception as e:
            logger.warning(f"Failed to calculate GPU memory utilization: {e}")
            return 0.9, False

    def _compute_max_new_tokens(
        self,
        target_duration: Optional[float],
        generation_phase: str,
        fallback_max: Optional[int] = None,
    ) -> int:
        """
        Compute max_new_tokens based on target duration and generation phase.

        In the two-phase architecture:
        - CoT phase: generates metadata (~50-200 tokens) + needs buffer for safety.
        - Codes phase: CoT is already in the prompt; only audio codes are generated.
          The constrained decoder forces EOS at exactly target_codes, so only a
          small buffer (10 tokens) is needed to avoid a misleading progress bar.

        Duration is clamped to ``[DURATION_MIN, max_dur]`` where *max_dur* is the
        GPU-config-dependent maximum (from ``get_global_gpu_config()``) capped at
        ``DURATION_MAX``.  This keeps the progress-bar total aligned with what the
        constrained decoder actually enforces.

        Args:
            target_duration: Target duration in seconds (5 codes = 1 second).
            generation_phase: "cot" or "codes".
            fallback_max: Fallback value when target_duration is not set.

        Returns:
            Computed max_new_tokens value, capped at model's max length.
        """
        if target_duration is not None and target_duration > 0:
            # Determine the effective upper bound from GPU config (if available)
            # so that max_new_tokens does not exceed what the constrained decoder
            # will actually enforce on lower-tier GPUs.
            gpu_max_dur = DURATION_MAX
            try:
                gpu_cfg = get_global_gpu_config()
                gpu_max_dur = min(gpu_cfg.max_duration_with_lm, DURATION_MAX)
            except Exception:
                pass  # Fallback to DURATION_MAX if GPU config unavailable

            effective_duration = max(DURATION_MIN, min(gpu_max_dur, target_duration))
            target_codes = int(effective_duration * 5)
            if generation_phase == "codes":
                # Codes phase: CoT already in prompt, only audio codes generated.
                # Constrained decoder forces EOS at target_codes, so small buffer suffices.
                max_new_tokens = target_codes + 10
            else:
                # CoT phase or mixed: add larger buffer for metadata overhead.
                max_new_tokens = target_codes + 500
        else:
            if fallback_max is not None:
                max_new_tokens = fallback_max
            else:
                max_new_tokens = getattr(self, "max_model_len", 4096) - 64

        # Cap at model's max length
        if hasattr(self, "max_model_len"):
            max_new_tokens = min(max_new_tokens, self.max_model_len - 64)

        return max_new_tokens

    def _has_meaningful_negative_prompt(self, negative_prompt: str) -> bool:
        """Check if negative prompt is meaningful (not default/empty)"""
        return negative_prompt and negative_prompt.strip() and negative_prompt.strip() != "NO USER INPUT"

    def _build_logits_processor(self, repetition_penalty: float) -> LogitsProcessorList:
        """Build logits processor list with repetition penalty if needed"""
        logits_processor = LogitsProcessorList()
        if repetition_penalty != 1.0:
            logits_processor.append(RepetitionPenaltyLogitsProcessor(penalty=repetition_penalty))
        return logits_processor

    def _setup_constrained_processor(
        self,
        use_constrained_decoding: bool,
        constrained_decoding_debug: bool,
        target_duration: Optional[float],
        user_metadata: Optional[Dict[str, Optional[str]]],
        stop_at_reasoning: bool,
        skip_genres: bool,
        skip_caption: bool,
        skip_language: bool,
        generation_phase: str,
        is_batch: bool = False,
        metadata_temperature: Optional[float] = None,
        codes_temperature: Optional[float] = None,
    ) -> Optional[MetadataConstrainedLogitsProcessor]:
        """Setup and configure constrained processor for generation"""
        use_phase_temperatures = not is_batch and (metadata_temperature is not None or codes_temperature is not None)

        if not use_constrained_decoding and not use_phase_temperatures:
            return None

        # Reset processor state for new generation
        self.constrained_processor.reset()

        # Use shared processor, just update settings
        self.constrained_processor.enabled = use_constrained_decoding
        self.constrained_processor.debug = constrained_decoding_debug

        # Phase temperatures only supported in single mode
        if use_phase_temperatures:
            self.constrained_processor.metadata_temperature = metadata_temperature
            self.constrained_processor.codes_temperature = codes_temperature
        else:
            self.constrained_processor.metadata_temperature = None
            self.constrained_processor.codes_temperature = None

        self.constrained_processor.set_target_duration(target_duration)

        # Batch mode uses default/disabled settings for these options
        if is_batch:
            self.constrained_processor.set_user_metadata(None)
            self.constrained_processor.set_stop_at_reasoning(False)
            self.constrained_processor.set_skip_genres(True)
            self.constrained_processor.set_skip_caption(True)
            self.constrained_processor.set_skip_language(True)
        else:
            # Single mode uses provided settings
            self.constrained_processor.set_user_metadata(user_metadata)
            self.constrained_processor.set_stop_at_reasoning(stop_at_reasoning)
            self.constrained_processor.set_skip_genres(skip_genres)
            self.constrained_processor.set_skip_caption(skip_caption)
            self.constrained_processor.set_skip_language(skip_language)

        # Set generation phase for phase-aware processing
        self.constrained_processor.set_generation_phase(generation_phase)

        return self.constrained_processor

    def _build_unconditional_prompt(
        self,
        caption: str,
        lyrics: str,
        cot_text: str,
        negative_prompt: str,
        generation_phase: str,
        is_batch: bool = False,
    ) -> str:
        """Build unconditional prompt for CFG based on generation phase and batch mode"""
        if is_batch or generation_phase == "codes":
            # Codes phase or batch mode: use empty CoT in unconditional prompt
            return self.build_formatted_prompt_with_cot(
                caption, lyrics, cot_text, is_negative_prompt=True, negative_prompt=negative_prompt
            )
        else:
            # CoT phase (single mode only): unconditional prompt
            # If negative_prompt is provided, use it as caption; otherwise remove caption and keep only lyrics
            return self.build_formatted_prompt(
                caption, lyrics, is_negative_prompt=True, generation_phase="cot", negative_prompt=negative_prompt
            )

    def _load_pytorch_model(self, model_path: str, device: str) -> Tuple[bool, str]:
        """Load PyTorch model from path and return (success, status_message)"""
        try:
            self.llm = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True)
            if not self.offload_to_cpu:
                self.llm = self.llm.to(device).to(self.dtype)
            else:
                self.llm = self.llm.to("cpu").to(self.dtype)
            self.llm.eval()
            self.llm_backend = "pt"
            self.llm_initialized = True
            logger.info(f"5Hz LM initialized successfully using PyTorch backend on {device}")
            status_msg = f"✅ 5Hz LM initialized successfully\nModel: {model_path}\nBackend: PyTorch\nDevice: {device}"
            return True, status_msg
        except Exception as e:
            return False, f"❌ Error initializing 5Hz LM: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"

    def _apply_top_k_filter(self, logits: torch.Tensor, top_k: Optional[int]) -> torch.Tensor:
        """Apply top-k filtering to logits"""
        if top_k is not None and top_k > 0:
            indices_to_remove = logits < torch.topk(logits, top_k)[0][..., -1, None]
            logits[indices_to_remove] = float('-inf')
        return logits

    def _apply_top_p_filter(self, logits: torch.Tensor, top_p: Optional[float]) -> torch.Tensor:
        """Apply top-p (nucleus) filtering to logits"""
        if top_p is not None and 0.0 < top_p < 1.0:
            sorted_logits, sorted_indices = torch.sort(logits, descending=True)
            # Upcast to float32 for stable softmax/cumsum (critical for float16/MPS)
            cumulative_probs = torch.cumsum(torch.softmax(sorted_logits.float(), dim=-1), dim=-1)
            sorted_indices_to_remove = cumulative_probs > top_p
            sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
            sorted_indices_to_remove[..., 0] = 0
            indices_to_remove = sorted_indices_to_remove.scatter(1, sorted_indices, sorted_indices_to_remove)
            logits[indices_to_remove] = float('-inf')
        return logits

    def _sample_tokens(self, logits: torch.Tensor, temperature: float) -> torch.Tensor:
        """Sample tokens from logits with temperature.

        Upcasts to float32 for numerical stability (float16 logits can overflow
        during softmax, especially after CFG scaling).
        """
        if temperature > 0:
            # Upcast to float32 for stable softmax (critical for float16/MPS)
            logits = logits.float() / temperature
            probs = torch.softmax(logits, dim=-1)
            return torch.multinomial(probs, num_samples=1).squeeze(1)
        else:
            return torch.argmax(logits, dim=-1)

    def _check_eos_token(self, tokens: torch.Tensor, eos_token_id: int, pad_token_id: Optional[int]) -> bool:
        """Check if any token in the batch is EOS or pad token"""
        if torch.any(tokens == eos_token_id):
            return True
        if pad_token_id is not None and pad_token_id != eos_token_id:
            if torch.any(tokens == pad_token_id):
                return True
        return False

    def _update_constrained_processor_state(self, constrained_processor: Optional[MetadataConstrainedLogitsProcessor], tokens: torch.Tensor):
        """Update constrained processor state with generated tokens"""
        if constrained_processor is not None:
            for b in range(tokens.shape[0]):
                constrained_processor.update_state(tokens[b].item())

    def _forward_pass(
        self,
        model: Any,
        generated_ids: torch.Tensor,
        model_kwargs: Dict[str, Any],
        past_key_values: Optional[Any],
        use_cache: bool,
    ) -> Any:
        """Perform forward pass with KV cache support"""
        if past_key_values is None:
            outputs = model(
                input_ids=generated_ids,
                **model_kwargs,
                use_cache=use_cache,
            )
        else:
            outputs = model(
                input_ids=generated_ids[:, -1:],
                past_key_values=past_key_values,
                **model_kwargs,
                use_cache=use_cache,
            )
        return outputs

    def _normalize_batch_input(self, formatted_prompts: Union[str, List[str]]) -> Tuple[List[str], bool]:
        """Normalize batch input: convert single string to list and return (list, is_batch)"""
        is_batch = isinstance(formatted_prompts, list)
        if is_batch:
            return formatted_prompts, is_batch
        else:
            return [formatted_prompts], is_batch

    def initialize(
        self,
        checkpoint_dir: str,
        lm_model_path: str,
        backend: str = "vllm",
        device: str = "auto",
        offload_to_cpu: bool = False,
        dtype: Optional[torch.dtype] = None,
    ) -> Tuple[str, bool]:
        """
        Initialize 5Hz LM model

        Args:
            checkpoint_dir: Checkpoint directory path
            lm_model_path: LM model path (relative to checkpoint_dir)
            backend: Backend type ("vllm" or "pt")
            device: Device type ("auto", "cuda", "mps", "xpu", or "cpu")
            offload_to_cpu: Whether to offload to CPU
            dtype: Data type (if None, auto-detect based on device)

        Returns:
            (status_message, success)
        """
        try:
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
                    logger.warning("[initialize] CUDA requested but unavailable. Falling back to MPS.")
                    device = "mps"
                elif hasattr(torch, 'xpu') and torch.xpu.is_available():
                    logger.warning("[initialize] CUDA requested but unavailable. Falling back to XPU.")
                    device = "xpu"
                else:
                    logger.warning("[initialize] CUDA requested but unavailable. Falling back to CPU.")
                    device = "cpu"
            elif device == "mps" and not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
                if torch.cuda.is_available():
                    logger.warning("[initialize] MPS requested but unavailable. Falling back to CUDA.")
                    device = "cuda"
                elif hasattr(torch, 'xpu') and torch.xpu.is_available():
                    logger.warning("[initialize] MPS requested but unavailable. Falling back to XPU.")
                    device = "xpu"
                else:
                    logger.warning("[initialize] MPS requested but unavailable. Falling back to CPU.")
                    device = "cpu"
            elif device == "xpu" and not (hasattr(torch, 'xpu') and torch.xpu.is_available()):
                if torch.cuda.is_available():
                    logger.warning("[initialize] XPU requested but unavailable. Falling back to CUDA.")
                    device = "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    logger.warning("[initialize] XPU requested but unavailable. Falling back to MPS.")
                    device = "mps"
                else:
                    logger.warning("[initialize] XPU requested but unavailable. Falling back to CPU.")
                    device = "cpu"

            self.device = device
            self.offload_to_cpu = offload_to_cpu

            # Set dtype based on device: bfloat16 for cuda/xpu, float32 for mps/cpu
            # Note: LLM stays in float32 on MPS because autoregressive generation is
            # latency-bound (not compute-bound), and many LLM weights trained in bfloat16
            # produce NaN/inf when naively converted to float16 (different exponent range).
            # The DiT and VAE use float16 on MPS where it actually helps throughput.
            if dtype is None:
                if device in ["cuda", "xpu"]:
                    self.dtype = torch.bfloat16
                else:
                    self.dtype = torch.float32
            else:
                self.dtype = dtype
                # Keep LM in float32 on MPS for stability.
                if device == "mps" and self.dtype != torch.float32:
                    logger.warning(
                        f"[initialize] Overriding requested dtype {self.dtype} to float32 for LM on MPS."
                    )
                    self.dtype = torch.float32

            # If lm_model_path is None, use default
            if lm_model_path is None:
                lm_model_path = "acestep-5Hz-lm-1.7B"
                logger.info(f"[initialize] lm_model_path is None, using default: {lm_model_path}")

            full_lm_model_path = os.path.join(checkpoint_dir, lm_model_path)
            if not os.path.exists(full_lm_model_path):
                return f"❌ 5Hz LM model not found at {full_lm_model_path}", False

            # Proactive CUDA cleanup before LM load to reduce fragmentation on mode/model switch
            if device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            logger.info("loading 5Hz LM tokenizer... it may take 80~90s")
            start_time = time.time()
            # TODO: load tokenizer too slow, not found solution yet
            llm_tokenizer = AutoTokenizer.from_pretrained(full_lm_model_path, use_fast=True)
            logger.info(f"5Hz LM tokenizer loaded successfully in {time.time() - start_time:.2f} seconds")
            self.llm_tokenizer = llm_tokenizer

            # Initialize shared constrained decoding processor (one-time initialization)
            # Use GPU-based max_duration to limit duration values in constrained decoding
            logger.info("Initializing constrained decoding processor...")
            processor_start = time.time()

            gpu_config = get_global_gpu_config()
            # Use max_duration_with_lm since LM is being initialized
            max_duration_for_constraint = gpu_config.max_duration_with_lm
            logger.info(f"Setting constrained decoding max_duration to {max_duration_for_constraint}s based on GPU config (tier: {gpu_config.tier})")

            self.constrained_processor = MetadataConstrainedLogitsProcessor(
                tokenizer=self.llm_tokenizer,
                enabled=True,
                debug=False,
                max_duration=max_duration_for_constraint,
            )
            logger.info(f"Constrained processor initialized in {time.time() - processor_start:.2f} seconds")

            # Disable CUDA/HIP graph capture on ROCm (unverified on RDNA3 Windows)
            is_rocm = hasattr(torch.version, 'hip') and torch.version.hip is not None
            enforce_eager_for_vllm = bool(is_rocm)

            # Auto-detect best backend on Apple Silicon
            if backend == "mlx" or (backend == "vllm" and device == "mps"):
                # On Apple Silicon, prefer MLX (native acceleration) over PyTorch MPS
                if self._is_mlx_available():
                    logger.info("Attempting MLX backend for Apple Silicon acceleration...")
                    mlx_success, mlx_status = self._load_mlx_model(full_lm_model_path)
                    if mlx_success:
                        return mlx_status, True
                    else:
                        logger.warning(f"MLX backend failed: {mlx_status}")
                        if backend == "mlx":
                            # User explicitly requested MLX, fall back to PyTorch
                            logger.warning("MLX explicitly requested but failed, falling back to PyTorch backend")
                            success, status_msg = self._load_pytorch_model(full_lm_model_path, device)
                            if not success:
                                return status_msg, False
                            status_msg = f"✅ 5Hz LM initialized (PyTorch fallback from MLX)\nModel: {full_lm_model_path}\nBackend: PyTorch"
                            return status_msg, True
                        # else: backend was "vllm" on MPS, continue to vllm attempt below
                elif backend == "mlx":
                    logger.warning("MLX not available (requires Apple Silicon + mlx-lm package)")
                    # Fall back to PyTorch
                    success, status_msg = self._load_pytorch_model(full_lm_model_path, device)
                    if not success:
                        return status_msg, False
                    status_msg = f"✅ 5Hz LM initialized (PyTorch fallback, MLX not available)\nModel: {full_lm_model_path}\nBackend: PyTorch"
                    return status_msg, True

            if backend == "vllm" and device != "cuda":
                logger.info(
                    f"[initialize] vllm backend requires CUDA, using PyTorch backend for device={device}."
                )
                backend = "pt"

            # Initialize based on user-selected backend
            if backend == "vllm":
                _warn_if_prerelease_python()
                total_gb = get_gpu_memory_gb() if device == "cuda" else 0.0
                free_gb = 0.0
                if device == "cuda" and torch.cuda.is_available():
                    try:
                        if hasattr(torch.cuda, "mem_get_info"):
                            free_bytes, _ = torch.cuda.mem_get_info()
                            free_gb = free_bytes / (1024**3)
                        else:
                            total_bytes = torch.cuda.get_device_properties(0).total_memory
                            free_gb = (total_bytes - torch.cuda.memory_reserved(0)) / (1024**3)
                    except Exception:
                        free_gb = 0.0
                if device == "cuda" and free_gb < VRAM_SAFE_FREE_GB:
                    logger.warning(
                        f"vLLM disabled due to insufficient free VRAM (total={total_gb:.2f}GB, free={free_gb:.2f}GB, need>={VRAM_SAFE_FREE_GB}GB free) — falling back to PyTorch backend"
                    )
                    success, status_msg = self._load_pytorch_model(full_lm_model_path, device)
                    if not success:
                        return status_msg, False
                    status_msg = f"✅ 5Hz LM initialized successfully (PyTorch fallback)\nModel: {full_lm_model_path}\nBackend: PyTorch"
                else:
                    status_msg = self._initialize_5hz_lm_vllm(
                        full_lm_model_path,
                        enforce_eager=enforce_eager_for_vllm,
                    )
                    logger.info(f"5Hz LM status message: {status_msg}")
                    if status_msg.startswith("❌"):
                        if not self.llm_initialized:
                            if device == "mps" and self._is_mlx_available():
                                logger.warning("vllm failed on MPS, trying MLX backend...")
                                mlx_success, mlx_status = self._load_mlx_model(full_lm_model_path)
                                if mlx_success:
                                    return mlx_status, True
                                logger.warning(f"MLX also failed: {mlx_status}, falling back to PyTorch")
                            logger.warning("Falling back to PyTorch backend")
                            success, status_msg = self._load_pytorch_model(full_lm_model_path, device)
                            if not success:
                                return status_msg, False
                            status_msg = f"✅ 5Hz LM initialized successfully (PyTorch fallback)\nModel: {full_lm_model_path}\nBackend: PyTorch"
            elif backend != "mlx":
                success, status_msg = self._load_pytorch_model(full_lm_model_path, device)
                if not success:
                    return status_msg, False

            return status_msg, True

        except Exception as e:
            return f"❌ Error initializing 5Hz LM: {str(e)}\n\nTraceback:\n{traceback.format_exc()}", False

    def _initialize_5hz_lm_vllm(self, model_path: str, enforce_eager: bool = False) -> str:
        """Initialize 5Hz LM model using vllm backend. When enforce_eager is True, CUDA graph
        capture is disabled (required when LoRA training may run in the same process)."""
        if not torch.cuda.is_available():
            self.llm_initialized = False
            logger.error("CUDA/ROCm is not available. Please check your GPU setup.")
            return "❌ CUDA/ROCm is not available. Please check your GPU setup."
        try:
            from nanovllm import LLM, SamplingParams
        except ImportError:
            self.llm_initialized = False
            logger.error("nano-vllm is not installed. Please install it using 'cd acestep/third_parts/nano-vllm && pip install .")
            return "❌ nano-vllm is not installed. Please install it using 'cd acestep/third_parts/nano-vllm && pip install ."

        try:
            current_device = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(current_device)

            torch.cuda.empty_cache()
            self._cleanup_torch_distributed_state()

            # Use adaptive GPU memory utilization based on model size
            gpu_memory_utilization, low_gpu_memory_mode = self.get_gpu_memory_utilization(
                model_path=model_path,
                minimal_gpu=3,
                min_ratio=0.1,
                max_ratio=0.9
            )

            if low_gpu_memory_mode:
                self.max_model_len = 2048
            else:
                self.max_model_len = 4096

            logger.info(f"Initializing 5Hz LM with model: {model_path}, enforce_eager: {enforce_eager}, tensor_parallel_size: 1, max_model_len: {self.max_model_len}, gpu_memory_utilization: {gpu_memory_utilization:.3f}")
            start_time = time.time()
            self.llm = LLM(
                model=model_path,
                enforce_eager=enforce_eager,
                tensor_parallel_size=1,
                max_model_len=self.max_model_len,
                gpu_memory_utilization=gpu_memory_utilization,
                tokenizer=self.llm_tokenizer,
            )
            logger.info(f"5Hz LM initialized successfully in {time.time() - start_time:.2f} seconds")
            self.llm_initialized = True
            self.llm_backend = "vllm"
            return f"✅ 5Hz LM initialized successfully\nModel: {model_path}\nDevice: {device_name}\nGPU Memory Utilization: {gpu_memory_utilization:.3f}\nLow GPU Memory Mode: {low_gpu_memory_mode}"
        except Exception as e:
            self.llm_initialized = False
            return f"❌ Error initializing 5Hz LM: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"

    def _run_vllm(
        self,
        formatted_prompts: Union[str, List[str]],
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool = True,
        constrained_decoding_debug: bool = False,
        metadata_temperature: Optional[float] = None,
        codes_temperature: Optional[float] = None,
        target_duration: Optional[float] = None,
        user_metadata: Optional[Dict[str, Optional[str]]] = None,
        stop_at_reasoning: bool = False,
        skip_genres: bool = True,
        skip_caption: bool = False,
        skip_language: bool = False,
        generation_phase: str = "cot",
        caption: str = "",
        lyrics: str = "",
        cot_text: str = "",
        seeds: Optional[List[int]] = None,
    ) -> Union[str, List[str]]:
        """
        Unified vllm generation function supporting both single and batch modes.
        Accepts either a single formatted prompt (str) or a list of formatted prompts (List[str]).
        Returns a single string for single mode, or a list of strings for batch mode.
        """
        from nanovllm import SamplingParams

        # Determine if batch mode
        formatted_prompt_list, is_batch = self._normalize_batch_input(formatted_prompts)
        batch_size = len(formatted_prompt_list)

        # Determine effective temperature for sampler
        # Batch mode doesn't support phase temperatures, so use simple temperature
        # Single mode supports phase temperatures
        use_phase_temperatures = not is_batch and (metadata_temperature is not None or codes_temperature is not None)
        effective_sampler_temp = 1.0 if use_phase_temperatures else temperature

        # Setup constrained processor
        constrained_processor = self._setup_constrained_processor(
            use_constrained_decoding=use_constrained_decoding or use_phase_temperatures,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            is_batch=is_batch,
            metadata_temperature=metadata_temperature,
            codes_temperature=codes_temperature,
        )

        # Calculate max_tokens based on target_duration and generation phase
        max_tokens = self._compute_max_new_tokens(
            target_duration=target_duration,
            generation_phase=generation_phase,
            fallback_max=self.max_model_len - 64,
        )

        sampling_params = SamplingParams(
            max_tokens=max_tokens,
            temperature=effective_sampler_temp,
            cfg_scale=cfg_scale,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            logits_processor=constrained_processor,
            logits_processor_update_state=constrained_processor.update_state if constrained_processor else None,
        )

        if cfg_scale > 1.0:
            # Build unconditional prompt based on generation phase
            formatted_unconditional_prompt = self._build_unconditional_prompt(
                caption=caption,
                lyrics=lyrics,
                cot_text=cot_text,
                negative_prompt=negative_prompt,
                generation_phase=generation_phase,
                is_batch=is_batch,
            )
            unconditional_prompts = [formatted_unconditional_prompt] * batch_size

            outputs = self.llm.generate(
                formatted_prompt_list,
                sampling_params,
                unconditional_prompts=unconditional_prompts,
            )
        else:
            outputs = self.llm.generate(formatted_prompt_list, sampling_params)

        # Extract text from outputs
        output_texts = []
        for output in outputs:
            if hasattr(output, "outputs") and len(output.outputs) > 0:
                output_texts.append(output.outputs[0].text)
            elif hasattr(output, "text"):
                output_texts.append(output.text)
            elif isinstance(output, dict) and "text" in output:
                output_texts.append(output["text"])
            else:
                output_texts.append(str(output))

        # Return single string for single mode, list for batch mode
        return output_texts[0] if not is_batch else output_texts

    def _run_pt_single(
        self,
        formatted_prompt: str,
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool,
        constrained_decoding_debug: bool,
        target_duration: Optional[float],
        user_metadata: Optional[Dict[str, Optional[str]]],
        stop_at_reasoning: bool,
        skip_genres: bool,
        skip_caption: bool,
        skip_language: bool,
        generation_phase: str,
        caption: str,
        lyrics: str,
        cot_text: str,
    ) -> str:
        """Internal helper function for single-item PyTorch generation."""
        inputs = self.llm_tokenizer(
            formatted_prompt,
            return_tensors="pt",
            padding=False,
            truncation=True,
        )

        # Setup constrained processor
        constrained_processor = self._setup_constrained_processor(
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            is_batch=False,
        )

        with self._load_model_context():
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Calculate max_new_tokens based on target_duration and generation phase
            max_new_tokens = self._compute_max_new_tokens(
                target_duration=target_duration,
                generation_phase=generation_phase,
                fallback_max=getattr(self.llm.config, "max_new_tokens", 4096),
            )

            # Build logits processor list (only for CFG and repetition penalty)
            logits_processor = self._build_logits_processor(repetition_penalty)

            if cfg_scale > 1.0:
                # Build unconditional prompt based on generation phase
                formatted_unconditional_prompt = self._build_unconditional_prompt(
                    caption=caption,
                    lyrics=lyrics,
                    cot_text=cot_text,
                    negative_prompt=negative_prompt,
                    generation_phase=generation_phase,
                    is_batch=False,
                )

                # Tokenize both prompts together to ensure same length (with left padding)
                # Left padding is important for generation tasks
                batch_texts = [formatted_prompt, formatted_unconditional_prompt]
                original_padding_side = self.llm_tokenizer.padding_side
                self.llm_tokenizer.padding_side = 'left'
                batch_inputs_tokenized = self.llm_tokenizer(
                    batch_texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                )
                self.llm_tokenizer.padding_side = original_padding_side
                batch_inputs_tokenized = {k: v.to(self.device) for k, v in batch_inputs_tokenized.items()}

                # Extract batch inputs
                batch_input_ids = batch_inputs_tokenized['input_ids']
                batch_attention_mask = batch_inputs_tokenized.get('attention_mask', None)

                # Use custom CFG generation loop with constrained decoding
                outputs = self._generate_with_cfg_custom(
                    batch_input_ids=batch_input_ids,
                    batch_attention_mask=batch_attention_mask,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    cfg_scale=cfg_scale,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    pad_token_id=self.llm_tokenizer.pad_token_id or self.llm_tokenizer.eos_token_id,
                    streamer=None,
                    constrained_processor=constrained_processor,
                )

                # Extract only the conditional output (first in batch)
                outputs = outputs[0:1]  # Keep only conditional output
            elif use_constrained_decoding:
                # Use custom constrained decoding loop for non-CFG
                outputs = self._generate_with_constrained_decoding(
                    input_ids=inputs["input_ids"],
                    attention_mask=inputs.get("attention_mask"),
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    pad_token_id=self.llm_tokenizer.pad_token_id or self.llm_tokenizer.eos_token_id,
                    streamer=None,
                    constrained_processor=constrained_processor,
                )
            else:
                # Generate without CFG using native generate() parameters
                with torch.inference_mode():
                    outputs = self.llm.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature if temperature > 0 else 1.0,
                        do_sample=True if temperature > 0 else False,
                        top_k=top_k if top_k is not None and top_k > 0 else None,
                        top_p=top_p if top_p is not None and 0.0 < top_p < 1.0 else None,
                        logits_processor=logits_processor if len(logits_processor) > 0 else None,
                        pad_token_id=self.llm_tokenizer.pad_token_id or self.llm_tokenizer.eos_token_id,
                        streamer=None,
                    )

        # Decode the generated tokens
        # outputs is a tensor with shape [batch_size, seq_len], extract first sequence
        if isinstance(outputs, torch.Tensor):
            if outputs.dim() == 2:
                generated_ids = outputs[0]
            else:
                generated_ids = outputs
        else:
            generated_ids = outputs[0]

        # Only decode the newly generated tokens (skip the input prompt)
        # Use the original input length (before batch processing for CFG)
        if cfg_scale > 1.0:
            # In CFG case, we need to use the conditional input length from batch_inputs_tokenized
            # Both sequences have the same length due to padding
            input_length = batch_inputs_tokenized['input_ids'].shape[1]
        else:
            input_length = inputs["input_ids"].shape[1]

        generated_ids = generated_ids[input_length:]

        # Move to CPU for decoding (tokenizer needs CPU tensors)
        if generated_ids.device.type != "cpu":
            generated_ids = generated_ids.cpu()

        output_text = self.llm_tokenizer.decode(generated_ids, skip_special_tokens=False)
        return output_text

    def _run_pt(
        self,
        formatted_prompts: Union[str, List[str]],
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool = True,
        constrained_decoding_debug: bool = False,
        target_duration: Optional[float] = None,
        user_metadata: Optional[Dict[str, Optional[str]]] = None,
        stop_at_reasoning: bool = False,
        skip_genres: bool = True,
        skip_caption: bool = False,
        skip_language: bool = False,
        generation_phase: str = "cot",
        caption: str = "",
        lyrics: str = "",
        cot_text: str = "",
        seeds: Optional[List[int]] = None,
    ) -> Union[str, List[str]]:
        """
        Unified PyTorch generation function supporting both single and batch modes.
        Accepts either a single formatted prompt (str) or a list of formatted prompts (List[str]).
        Returns a single string for single mode, or a list of strings for batch mode.
        Note: PyTorch backend processes batch items sequentially (doesn't support true batching efficiently).
        """
        # Determine if batch mode
        formatted_prompt_list, is_batch = self._normalize_batch_input(formatted_prompts)

        # For batch mode, process each item sequentially with different seeds.
        # Wrap the entire loop in a single _load_model_context() so the model
        # loads to GPU once and offloads once, instead of per-item.
        if is_batch:
            output_texts = []

            with self._load_model_context():
                for i, formatted_prompt in enumerate(formatted_prompt_list):
                    # Set seed for this item if provided
                    if seeds and i < len(seeds):
                        torch.manual_seed(seeds[i])
                        if torch.cuda.is_available():
                            torch.cuda.manual_seed_all(seeds[i])
                        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                            torch.mps.manual_seed(seeds[i])

                    # Generate using single-item method with batch-mode defaults
                    output_text = self._run_pt_single(
                        formatted_prompt=formatted_prompt,
                        temperature=temperature,
                        cfg_scale=cfg_scale,
                        negative_prompt=negative_prompt,
                        top_k=top_k,
                        top_p=top_p,
                        repetition_penalty=repetition_penalty,
                        use_constrained_decoding=use_constrained_decoding,
                        constrained_decoding_debug=constrained_decoding_debug,
                        target_duration=target_duration,
                        user_metadata=None,
                        stop_at_reasoning=False,
                        skip_genres=True,
                        skip_caption=True,
                        skip_language=True,
                        generation_phase=generation_phase,
                        caption=caption,
                        lyrics=lyrics,
                        cot_text=cot_text,
                    )

                    output_texts.append(output_text)

            return output_texts

        # Single mode: process the formatted prompt
        formatted_prompt = formatted_prompt_list[0]

        return self._run_pt_single(
            formatted_prompt=formatted_prompt,
            temperature=temperature,
            cfg_scale=cfg_scale,
            negative_prompt=negative_prompt,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            caption=caption,
            lyrics=lyrics,
            cot_text=cot_text,
        )

    def has_all_metas(self, user_metadata: Optional[Dict[str, Optional[str]]]) -> bool:
        """Check if all required metadata are present."""
        if user_metadata is None:
            return False
        if 'bpm' in user_metadata and 'keyscale' in user_metadata and 'timesignature' in user_metadata and 'duration' in user_metadata:
            return True
        return False

    def _format_metadata_as_cot(self, metadata: Dict[str, Any]) -> str:
        """
        Format parsed metadata as CoT text using YAML format (matching training format).

        Args:
            metadata: Dictionary with keys: bpm, caption, duration, keyscale, language, timesignature

        Returns:
            Formatted CoT text: "<think>\n{yaml_content}\n</think>"
        """
        # Build cot_items dict with only non-None values
        cot_items = {}
        for key in ['bpm', 'caption', 'duration', 'keyscale', 'language', 'timesignature']:
            if key in metadata and metadata[key] is not None:
                value = metadata[key]
                if key == "timesignature" and value.endswith("/4"):
                    value = value.split("/")[0]
                if isinstance(value, str) and value.isdigit():
                    value = int(value)
                cot_items[key] = value

        # Format as YAML (sorted keys, unicode support)
        if len(cot_items) > 0:
            cot_yaml = yaml.dump(cot_items, allow_unicode=True, sort_keys=True).strip()
        else:
            cot_yaml = ""

        return f"<think>\n{cot_yaml}\n</think>"

    def generate_with_stop_condition(
        self,
        caption: str,
        lyrics: str,
        infer_type: str,
        temperature: float = 0.85,
        cfg_scale: float = 1.0,
        negative_prompt: str = "NO USER INPUT",
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        repetition_penalty: float = 1.0,
        use_constrained_decoding: bool = True,
        constrained_decoding_debug: bool = False,
        target_duration: Optional[float] = None,
        user_metadata: Optional[Dict[str, Optional[str]]] = None,
        use_cot_metas: bool = True,
        use_cot_caption: bool = True,
        use_cot_language: bool = True,
        batch_size: Optional[int] = None,
        seeds: Optional[List[int]] = None,
        progress=None,
    ) -> Dict[str, Any]:
        """Two-phase LM generation: CoT generation followed by audio codes generation.

        - infer_type='dit': Phase 1 only - generate CoT and return metas (no audio codes)
        - infer_type='llm_dit': Phase 1 + Phase 2 - generate CoT then audio codes

        Args:
            target_duration: Target duration in seconds for codes generation constraint.
                            5 codes = 1 second. If specified, blocks EOS until target reached.
            user_metadata: User-provided metadata fields (e.g. bpm/duration/keyscale/timesignature).
                           If specified, constrained decoding will inject these values directly.
            use_cot_caption: Whether to generate caption in CoT (default True).
            use_cot_language: Whether to generate language in CoT (default True).
            batch_size: Optional batch size for batch generation. If None or 1, returns single result.
                       If > 1, returns batch results (lists).
            seeds: Optional list of seeds for batch generation (for reproducibility).
                  Only used when batch_size > 1. TODO: not used yet

        Returns:
            Dictionary containing:
                - metadata: Dict or List[Dict] - Generated metadata
                - audio_codes: str or List[str] - Generated audio codes
                - success: bool - Whether generation succeeded
                - error: Optional[str] - Error message if failed
                - extra_outputs: Dict with time_costs and other info
        """
        if progress is None:
            def progress(*args, **kwargs):
                pass

        infer_type = (infer_type or "").strip().lower()
        if infer_type not in {"dit", "llm_dit"}:
            error_msg = f"invalid infer_type: {infer_type!r} (expected 'dit' or 'llm_dit')"
            return {
                "metadata": [] if (batch_size and batch_size > 1) else {},
                "audio_codes": [] if (batch_size and batch_size > 1) else "",
                "success": False,
                "error": error_msg,
                "extra_outputs": {"time_costs": {}},
            }

        # Determine if batch mode
        is_batch = batch_size and batch_size > 1
        actual_batch_size = batch_size if is_batch else 1

        # Initialize variables
        metadata = {}
        audio_codes = ""
        has_all_metas = self.has_all_metas(user_metadata)
        phase1_time = 0.0
        phase2_time = 0.0

        # Handle seeds for batch mode
        if is_batch:
            if seeds is None:
                seeds = [random.randint(0, 2**32 - 1) for _ in range(actual_batch_size)]
            elif len(seeds) < actual_batch_size:
                seeds = list(seeds) + [random.randint(0, 2**32 - 1) for _ in range(actual_batch_size - len(seeds))]
            else:
                seeds = seeds[:actual_batch_size]

        # ========== PHASE 1: CoT Generation ==========
        # Skip CoT if all metadata are user-provided OR caption is already formatted
        progress(0.1, f"Phase 1: Generating CoT metadata (once for all items)...")
        if not has_all_metas and use_cot_metas:
            if is_batch:
                logger.info("Batch Phase 1: Generating CoT metadata (once for all items)...")
            else:
                logger.info("Phase 1: Generating CoT metadata...")
            phase1_start = time.time()

            # Build formatted prompt for CoT phase
            formatted_prompt = self.build_formatted_prompt(caption, lyrics, generation_phase="cot")

            logger.info(f"generate_with_stop_condition: formatted_prompt={formatted_prompt}")
            # Generate CoT (stop at </think>)
            cot_output_text, status = self.generate_from_formatted_prompt(
                formatted_prompt=formatted_prompt,
                cfg={
                    "temperature": temperature,
                    "cfg_scale": cfg_scale,
                    "negative_prompt": negative_prompt,
                    "top_k": top_k,
                    "top_p": top_p,
                    "repetition_penalty": repetition_penalty,
                    "target_duration": None,  # No duration constraint for CoT phase
                    "user_metadata": user_metadata,
                    "skip_caption": not use_cot_caption,
                    "skip_language": not use_cot_language,
                    "skip_genres": True,  # Generate genres
                    "generation_phase": "cot",
                    # Pass context for building unconditional prompt in CoT phase
                    "caption": caption,
                    "lyrics": lyrics,
                },
                use_constrained_decoding=use_constrained_decoding,
                constrained_decoding_debug=constrained_decoding_debug,
                stop_at_reasoning=True,  # Always stop at </think> in Phase 1
            )

            phase1_time = time.time() - phase1_start

            if not cot_output_text:
                return {
                    "metadata": [] if is_batch else {},
                    "audio_codes": [] if is_batch else "",
                    "success": False,
                    "error": status,
                    "extra_outputs": {"time_costs": {"phase1_time": phase1_time}},
                }

            # Parse metadata from CoT output
            metadata, _ = self.parse_lm_output(cot_output_text)
            if is_batch:
                logger.info(f"Batch Phase 1 completed in {phase1_time:.2f}s. Generated metadata: {list(metadata.keys())}")
            else:
                logger.info(f"Phase 1 completed in {phase1_time:.2f}s. Generated metadata: {list(metadata.keys())}")
        else:
            # Use user-provided metadata
            if is_batch:
                logger.info("Batch Phase 1: Using user-provided metadata (skipping generation)")
            else:
                logger.info("Phase 1: Using user-provided metadata (skipping generation)")
            metadata = {k: v for k, v in user_metadata.items() if v is not None}

        # If infer_type is 'dit', stop here and return only metadata
        if infer_type == "dit":
            if is_batch:
                metadata_list = [metadata.copy() for _ in range(actual_batch_size)]
                return {
                    "metadata": metadata_list,
                    "audio_codes": [""] * actual_batch_size,
                    "success": True,
                    "error": None,
                    "extra_outputs": {
                        "time_costs": {
                            "phase1_time": phase1_time,
                            "total_time": phase1_time,
                        }
                    },
                }
            else:
                return {
                    "metadata": metadata,
                    "audio_codes": "",
                    "success": True,
                    "error": None,
                    "extra_outputs": {
                        "time_costs": {
                            "phase1_time": phase1_time,
                            "total_time": phase1_time,
                        }
                    },
                }

        # ========== PHASE 2: Audio Codes Generation ==========
        if is_batch:
            logger.info(f"Batch Phase 2: Generating audio codes for {actual_batch_size} items...")
        else:
            logger.info("Phase 2: Generating audio codes...")
        phase2_start = time.time()

        # Format metadata as CoT using YAML (matching training format)
        cot_text = self._format_metadata_as_cot(metadata)

        # Build formatted prompt with CoT for codes generation phase
        formatted_prompt_with_cot = self.build_formatted_prompt_with_cot(caption, lyrics, cot_text)
        logger.info(f"generate_with_stop_condition: formatted_prompt_with_cot={formatted_prompt_with_cot}")

        progress(0.5, f"Phase 2: Generating audio codes for {actual_batch_size} items...")
        if is_batch:
            # Batch mode: generate codes for all items
            formatted_prompts = [formatted_prompt_with_cot] * actual_batch_size

            # Call backend-specific batch generation
            try:
                if self.llm_backend == "vllm":
                    codes_outputs = self._run_vllm(
                        formatted_prompts=formatted_prompts,
                        temperature=temperature,
                        cfg_scale=cfg_scale,
                        negative_prompt=negative_prompt,
                        top_k=top_k,
                        top_p=top_p,
                        repetition_penalty=repetition_penalty,
                        use_constrained_decoding=use_constrained_decoding,
                        constrained_decoding_debug=constrained_decoding_debug,
                        target_duration=target_duration,
                        generation_phase="codes",
                        caption=caption,
                        lyrics=lyrics,
                        cot_text=cot_text,
                        seeds=seeds,
                    )
                elif self.llm_backend == "mlx":
                    codes_outputs = self._run_mlx(
                        formatted_prompts=formatted_prompts,
                        temperature=temperature,
                        cfg_scale=cfg_scale,
                        negative_prompt=negative_prompt,
                        top_k=top_k,
                        top_p=top_p,
                        repetition_penalty=repetition_penalty,
                        use_constrained_decoding=use_constrained_decoding,
                        constrained_decoding_debug=constrained_decoding_debug,
                        target_duration=target_duration,
                        generation_phase="codes",
                        caption=caption,
                        lyrics=lyrics,
                        cot_text=cot_text,
                        seeds=seeds,
                    )
                else:  # pt backend
                    codes_outputs = self._run_pt(
                        formatted_prompts=formatted_prompts,
                        temperature=temperature,
                        cfg_scale=cfg_scale,
                        negative_prompt=negative_prompt,
                        top_k=top_k,
                        top_p=top_p,
                        repetition_penalty=repetition_penalty,
                        use_constrained_decoding=use_constrained_decoding,
                        constrained_decoding_debug=constrained_decoding_debug,
                        target_duration=target_duration,
                        generation_phase="codes",
                        caption=caption,
                        lyrics=lyrics,
                        cot_text=cot_text,
                        seeds=seeds,
                    )
            except Exception as e:
                error_msg = f"Error in batch codes generation: {str(e)}"
                logger.error(error_msg)
                return {
                    "metadata": [],
                    "audio_codes": [],
                    "success": False,
                    "error": error_msg,
                    "extra_outputs": {
                        "time_costs": {
                            "phase1_time": phase1_time,
                            "phase2_time": 0.0,
                            "total_time": phase1_time,
                        }
                    },
                }

            # Parse audio codes from each output
            audio_codes_list = []
            metadata_list = []
            for output_text in codes_outputs:
                _, audio_codes_item = self.parse_lm_output(output_text)
                audio_codes_list.append(audio_codes_item)
                metadata_list.append(metadata.copy())  # Same metadata for all

            phase2_time = time.time() - phase2_start

            # Log results
            codes_counts = [len(codes.split('<|audio_code_')) - 1 if codes else 0 for codes in audio_codes_list]
            logger.info(f"Batch Phase 2 completed in {phase2_time:.2f}s. Generated codes: {codes_counts}")

            total_time = phase1_time + phase2_time
            return {
                "metadata": metadata_list,
                "audio_codes": audio_codes_list,
                "success": True,
                "error": None,
                "extra_outputs": {
                    "time_costs": {
                        "phase1_time": phase1_time,
                        "phase2_time": phase2_time,
                        "total_time": total_time,
                    },
                    "codes_counts": codes_counts,
                    "total_codes": sum(codes_counts),
                },
            }
        else:
            # Single mode: generate codes for one item
            codes_output_text, status = self.generate_from_formatted_prompt(
                formatted_prompt=formatted_prompt_with_cot,
                cfg={
                    "temperature": temperature,
                    "cfg_scale": cfg_scale,
                    "negative_prompt": negative_prompt,
                    "top_k": top_k,
                    "top_p": top_p,
                    "repetition_penalty": repetition_penalty,
                    "target_duration": target_duration,
                    "user_metadata": None,  # No user metadata injection in Phase 2
                    "skip_caption": True,  # Skip caption since CoT is already included
                    "skip_language": True,  # Skip language since CoT is already included
                    "generation_phase": "codes",
                    # Pass context for building unconditional prompt in codes phase
                    "caption": caption,
                    "lyrics": lyrics,
                    "cot_text": cot_text,
                },
                use_constrained_decoding=use_constrained_decoding,
                constrained_decoding_debug=constrained_decoding_debug,
                stop_at_reasoning=False,  # Generate codes until EOS
            )

            if not codes_output_text:
                total_time = phase1_time + phase2_time
                return {
                    "metadata": metadata,
                    "audio_codes": "",
                    "success": False,
                    "error": status,
                    "extra_outputs": {
                        "time_costs": {
                            "phase1_time": phase1_time,
                            "phase2_time": phase2_time,
                            "total_time": total_time,
                        }
                    },
                }

            phase2_time = time.time() - phase2_start

            # Parse audio codes from output (metadata should be same as Phase 1)
            _, audio_codes = self.parse_lm_output(codes_output_text)

            codes_count = len(audio_codes.split('<|audio_code_')) - 1 if audio_codes else 0
            logger.info(f"Phase 2 completed in {phase2_time:.2f}s. Generated {codes_count} audio codes")

            total_time = phase1_time + phase2_time
            return {
                "metadata": metadata,
                "audio_codes": audio_codes,
                "success": True,
                "error": None,
                "extra_outputs": {
                    "time_costs": {
                        "phase1_time": phase1_time,
                        "phase2_time": phase2_time,
                        "total_time": total_time,
                    },
                    "codes_count": codes_count,
                },
            }

    def build_formatted_prompt(self, caption: str, lyrics: str = "", is_negative_prompt: bool = False, generation_phase: str = "cot", negative_prompt: str = "NO USER INPUT") -> str:
        """
        Build the chat-formatted prompt for 5Hz LM from caption/lyrics.
        Raises a ValueError if the tokenizer is not initialized.

        Args:
            caption: Caption text
            lyrics: Lyrics text
            is_negative_prompt: If True, builds unconditional prompt for CFG
            generation_phase: "cot" or "codes" - affects unconditional prompt format
            negative_prompt: Negative prompt for CFG (used when is_negative_prompt=True)

        Example:
            prompt = handler.build_formatted_prompt("calm piano", "hello world")
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")

        if is_negative_prompt:
            # Unconditional prompt for CFG
            # Check if user provided a meaningful negative prompt (not the default)
            has_negative_prompt = self._has_meaningful_negative_prompt(negative_prompt)

            if generation_phase == "cot":
                # CoT phase unconditional prompt
                if has_negative_prompt:
                    # If negative prompt provided, use it as caption
                    prompt = f"# Caption\n{negative_prompt}\n\n# Lyric\n{lyrics}\n"
                else:
                    # No negative prompt: remove caption, keep only lyrics
                    prompt = f"# Lyric\n{lyrics}\n"
            else:
                # Codes phase: will be handled by build_formatted_prompt_with_cot
                # For backward compatibility, use simple caption as before
                prompt = caption
        else:
            # Conditional prompt: include both caption and lyrics
            prompt = f"# Caption\n{caption}\n\n# Lyric\n{lyrics}\n"

        return self.llm_tokenizer.apply_chat_template(
            [
                {"role": "system", "content": f"# Instruction\n{DEFAULT_LM_INSTRUCTION}\n\n"},
                {"role": "user", "content": prompt},
            ],
            tokenize=False,
            add_generation_prompt=True,
        )

    def build_formatted_prompt_with_cot(self, caption: str, lyrics: str, cot_text: str, is_negative_prompt: bool = False, negative_prompt: str = "NO USER INPUT") -> str:
        """
        Build the chat-formatted prompt for codes generation phase with pre-generated CoT.

        Args:
            caption: Caption text
            lyrics: Lyrics text
            cot_text: Pre-generated CoT text (e.g., "<think>\\nbpm: 120\\n...\\n</think>")
            is_negative_prompt: If True, uses empty CoT for CFG unconditional prompt
            negative_prompt: Negative prompt for CFG (used when is_negative_prompt=True)

        Returns:
            Formatted prompt string

        Example:
            cot = "<think>\\nbpm: 120\\ncaption: calm piano\\n...\\n</think>"
            prompt = handler.build_formatted_prompt_with_cot("calm piano", "hello", cot)
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")

        if is_negative_prompt:
            # Unconditional prompt for codes phase
            # Check if user provided a meaningful negative prompt
            has_negative_prompt = self._has_meaningful_negative_prompt(negative_prompt)

            # Use empty CoT for unconditional
            cot_for_prompt = "<think>\n</think>"

            if has_negative_prompt:
                # If negative prompt provided, use it as caption
                caption_for_prompt = negative_prompt
            else:
                # No negative prompt: use original caption
                caption_for_prompt = caption
        else:
            # Conditional prompt: use the full CoT and original caption
            cot_for_prompt = cot_text
            caption_for_prompt = caption

        # Build user prompt with caption and lyrics ONLY (no COT)
        # COT should be in the assistant's message, not user's
        user_prompt = f"# Caption\n{caption_for_prompt}\n\n# Lyric\n{lyrics}\n"

        # Build the chat with assistant message containing the COT
        # The model will continue generation after the COT
        formatted = self.llm_tokenizer.apply_chat_template(
            [
                {"role": "system", "content": f"# Instruction\n{DEFAULT_LM_INSTRUCTION}\n\n"},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": cot_for_prompt},
            ],
            tokenize=False,
            add_generation_prompt=False,  # Don't add generation prompt, COT is already in assistant
        )

        # Add a newline after </think> so model generates audio codes on next line
        if not formatted.endswith('\n'):
            formatted += '\n'

        return formatted

    def build_formatted_prompt_for_understanding(
        self,
        audio_codes: str,
        is_negative_prompt: bool = False,
        negative_prompt: str = "NO USER INPUT"
    ) -> str:
        """
        Build the chat-formatted prompt for audio understanding from codes.

        This is the reverse of generation: given audio codes, generate metadata and lyrics.

        Args:
            audio_codes: Audio code string (e.g., "<|audio_code_123|><|audio_code_456|>...")
            is_negative_prompt: If True, builds unconditional prompt for CFG
            negative_prompt: Negative prompt for CFG (used when is_negative_prompt=True)

        Returns:
            Formatted prompt string

        Example:
            codes = "<|audio_code_18953|><|audio_code_13833|>..."
            prompt = handler.build_formatted_prompt_for_understanding(codes)
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")

        # For understanding task, user provides audio codes
        # Unconditional prompt uses negative_prompt or empty string
        if is_negative_prompt:
            user_content = negative_prompt if negative_prompt and negative_prompt.strip() else ""
        else:
            user_content = audio_codes

        return self.llm_tokenizer.apply_chat_template(
            [
                {
                    "role": "system",
                    "content": f"# Instruction\n{DEFAULT_LM_UNDERSTAND_INSTRUCTION}\n\n"
                },
                {
                    "role": "user",
                    "content": user_content
                },
            ],
            tokenize=False,
            add_generation_prompt=True,
        )

    def understand_audio_from_codes(
        self,
        audio_codes: str,
        temperature: float = 0.3,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        repetition_penalty: float = 1.0,
        use_constrained_decoding: bool = True,
        constrained_decoding_debug: bool = False,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Understand audio codes and generate metadata + lyrics.

        This is the reverse of the normal generation flow:
        - Input: Audio codes
        - Output: Metadata (bpm, caption, duration, etc.) + Lyrics

        Note: cfg_scale and negative_prompt are not supported in understand mode.

        Args:
            audio_codes: String of audio code tokens (e.g., "<|audio_code_123|><|audio_code_456|>...")
            temperature: Sampling temperature for generation
            top_k: Top-K sampling (None = disabled)
            top_p: Top-P (nucleus) sampling (None = disabled)
            repetition_penalty: Repetition penalty (1.0 = no penalty)
            use_constrained_decoding: Whether to use FSM-based constrained decoding for metadata
            constrained_decoding_debug: Whether to enable debug logging for constrained decoding

        Returns:
            Tuple of (metadata_dict, status_message)
            metadata_dict contains:
                - bpm: int or str
                - caption: str
                - duration: int or str
                - keyscale: str
                - language: str
                - timesignature: str
                - lyrics: str (extracted from output after </think>)

        Example:
            codes = "<|audio_code_18953|><|audio_code_13833|>..."
            metadata, status = handler.understand_audio_from_codes(codes)
            print(metadata['caption'])  # "A cinematic orchestral piece..."
            print(metadata['lyrics'])   # "[Intro: ...]\\n..."
        """
        if not getattr(self, "llm_initialized", False):
            return {}, "❌ 5Hz LM not initialized. Please initialize it first."

        if not audio_codes or not audio_codes.strip():
            return {}, "❌ No audio codes provided. Please paste audio codes first."

        logger.info(f"Understanding audio codes (length: {len(audio_codes)} chars)")

        # Build formatted prompt for understanding
        formatted_prompt = self.build_formatted_prompt_for_understanding(audio_codes)
        print(f"formatted_prompt: {formatted_prompt}")
        # Generate using constrained decoding (understand phase)
        # We want to generate metadata first (CoT), then lyrics (natural text)
        # Note: cfg_scale and negative_prompt are not used in understand mode
        output_text, status = self.generate_from_formatted_prompt(
            formatted_prompt=formatted_prompt,
            cfg={
                "temperature": temperature,
                "top_k": top_k,
                "top_p": top_p,
                "repetition_penalty": repetition_penalty,
                "target_duration": None,  # No duration constraint for understanding
                "user_metadata": None,  # No user metadata injection
                "skip_caption": False,  # Generate caption
                "skip_language": False,  # Generate language
                "skip_genres": False,  # Generate genres
                "generation_phase": "understand",  # Understanding phase: generate CoT metadata, then free-form lyrics
                # Context for building unconditional prompt
                "caption": "",
                "lyrics": "",
            },
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            stop_at_reasoning=False,  # Continue after </think> to generate lyrics
        )

        if not output_text:
            return {}, status

        # Parse metadata and extract lyrics
        metadata, _ = self.parse_lm_output(output_text)

        # Extract lyrics section (everything after </think>)
        lyrics = self._extract_lyrics_from_output(output_text)
        if lyrics:
            metadata['lyrics'] = lyrics

        logger.info(f"Understanding completed. Generated {len(metadata)} metadata fields")
        if constrained_decoding_debug:
            logger.debug(f"Generated metadata: {list(metadata.keys())}")
            logger.debug(f"Output text preview: {output_text[:200]}...")

        status_msg = f"✅ Understanding completed successfully\nGenerated fields: {', '.join(metadata.keys())}"
        return metadata, status_msg

    def _extract_lyrics_from_output(self, output_text: str) -> str:
        """
        Extract lyrics section from LLM output.

        The lyrics appear after the </think> tag and typically start with "# Lyric"
        or directly with lyric content.

        Args:
            output_text: Full LLM output text

        Returns:
            Extracted lyrics string, or empty string if no lyrics found
        """
        import re

        # Find the </think> tag
        think_end_pattern = r'</think>'
        match = re.search(think_end_pattern, output_text)

        if not match:
            # No </think> tag found, no lyrics
            return ""

        # Extract everything after </think>
        after_think = output_text[match.end():].strip()

        if not after_think:
            return ""

        # Remove "# Lyric" header if present
        lyric_header_pattern = r'^#\s*Lyri[c|cs]?\s*\n'
        after_think = re.sub(lyric_header_pattern, '', after_think, flags=re.IGNORECASE)

        # Remove <|im_end|> tag at the end if present
        after_think = re.sub(r'<\|im_end\|>\s*$', '', after_think)

        return after_think.strip()

    def build_formatted_prompt_for_inspiration(
        self,
        query: str,
        instrumental: bool = False,
        is_negative_prompt: bool = False,
        negative_prompt: str = "NO USER INPUT"
    ) -> str:
        """
        Build the chat-formatted prompt for inspiration/simple mode.

        This generates a complete sample (caption, lyrics, metadata) from a user's
        natural language music description query.

        Args:
            query: User's natural language music description
            instrumental: Whether to generate instrumental music (no vocals)
            is_negative_prompt: If True, builds unconditional prompt for CFG
            negative_prompt: Negative prompt for CFG (used when is_negative_prompt=True)

        Returns:
            Formatted prompt string

        Example:
            query = "a soft Bengali love song for a quiet evening"
            prompt = handler.build_formatted_prompt_for_inspiration(query, instrumental=False)
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")

        # Build user content with query and instrumental flag
        instrumental_str = "true" if instrumental else "false"

        if is_negative_prompt:
            # For CFG unconditional prompt
            user_content = negative_prompt if negative_prompt and negative_prompt.strip() else ""
        else:
            # Normal prompt: query + instrumental flag
            user_content = f"{query}\n\ninstrumental: {instrumental_str}"

        return self.llm_tokenizer.apply_chat_template(
            [
                {
                    "role": "system",
                    "content": f"# Instruction\n{DEFAULT_LM_INSPIRED_INSTRUCTION}\n\n"
                },
                {
                    "role": "user",
                    "content": user_content
                },
            ],
            tokenize=False,
            add_generation_prompt=True,
        )

    def create_sample_from_query(
        self,
        query: str,
        instrumental: bool = False,
        vocal_language: Optional[str] = None,
        temperature: float = 0.85,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        repetition_penalty: float = 1.0,
        use_constrained_decoding: bool = True,
        constrained_decoding_debug: bool = False,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Create a complete music sample from a user's natural language query.

        This is the "Simple Mode" / "Inspiration Mode" feature that generates:
        - Metadata (bpm, caption, duration, keyscale, language, timesignature)
        - Lyrics (unless instrumental=True)

        Args:
            query: User's natural language music description
            instrumental: Whether to generate instrumental music (no vocals)
            vocal_language: Allowed vocal language for constrained decoding (e.g., "en", "zh").
                           If provided and not "unknown", it will be used.
            temperature: Sampling temperature for generation (0.0-2.0)
            top_k: Top-K sampling (None = disabled)
            top_p: Top-P (nucleus) sampling (None = disabled)
            repetition_penalty: Repetition penalty (1.0 = no penalty)
            use_constrained_decoding: Whether to use FSM-based constrained decoding
            constrained_decoding_debug: Whether to enable debug logging

        Returns:
            Tuple of (metadata_dict, status_message)
            metadata_dict contains:
                - bpm: int or str
                - caption: str
                - duration: int or str
                - keyscale: str
                - language: str
                - timesignature: str
                - lyrics: str (extracted from output after </think>)
                - instrumental: bool (echoed back)

        Example:
            query = "a soft Bengali love song for a quiet evening"
            metadata, status = handler.create_sample_from_query(query, instrumental=False, vocal_language="bn")
            print(metadata['caption'])  # "A gentle romantic acoustic pop ballad..."
            print(metadata['lyrics'])   # "[Intro: ...]\\n..."
        """
        if not getattr(self, "llm_initialized", False):
            return {}, "❌ 5Hz LM not initialized. Please initialize it first."

        if not query or not query.strip():
            query = "NO USER INPUT"

        logger.info(f"Creating sample from query: {query[:100]}... (instrumental={instrumental}, vocal_language={vocal_language})")

        # Build formatted prompt for inspiration
        formatted_prompt = self.build_formatted_prompt_for_inspiration(
            query=query,
            instrumental=instrumental,
        )
        logger.debug(f"Formatted prompt for inspiration: {formatted_prompt}")

        # Build user_metadata if vocal_language is specified and is not "unknown"
        user_metadata = None
        skip_language = False
        if vocal_language and vocal_language.strip() and vocal_language.strip().lower() != "unknown":
            # Use the specified language for constrained decoding
            user_metadata = {"language": vocal_language.strip()}
            # skip_language = True  # Skip language generation since we're injecting it
            logger.info(f"Using user-specified language: {vocal_language.strip()}")

        # Generate using constrained decoding (inspiration phase)
        # Similar to understand mode - generate metadata first (CoT), then lyrics
        # Note: cfg_scale and negative_prompt are not used in create_sample mode
        output_text, status = self.generate_from_formatted_prompt(
            formatted_prompt=formatted_prompt,
            cfg={
                "temperature": temperature,
                "top_k": top_k,
                "top_p": top_p,
                "repetition_penalty": repetition_penalty,
                "target_duration": None,  # No duration constraint
                "user_metadata": user_metadata,  # Inject language if specified
                "skip_caption": False,  # Generate caption
                "skip_language": False,
                "skip_genres": False,  # Generate genres
                "generation_phase": "understand",  # Use understand phase for metadata + free-form lyrics
                "caption": "",
                "lyrics": "",
            },
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            stop_at_reasoning=False,  # Continue after </think> to generate lyrics
        )

        if not output_text:
            return {}, status

        # Parse metadata and extract lyrics
        metadata, _ = self.parse_lm_output(output_text)

        # Extract lyrics section (everything after </think>)
        lyrics = self._extract_lyrics_from_output(output_text)
        if lyrics:
            metadata['lyrics'] = lyrics
        elif instrumental:
            # For instrumental, set empty lyrics or placeholder
            metadata['lyrics'] = "[Instrumental]"

        # Echo back the instrumental flag
        metadata['instrumental'] = instrumental

        logger.info(f"Sample created successfully. Generated {metadata} fields")
        if constrained_decoding_debug:
            logger.debug(f"Generated metadata: {list(metadata.keys())}")
            logger.debug(f"Output text preview: {output_text[:300]}...")

        status_msg = f"✅ Sample created successfully\nGenerated fields: {metadata}"
        return metadata, status_msg

    def build_formatted_prompt_for_format(
        self,
        caption: str,
        lyrics: str,
        is_negative_prompt: bool = False,
        negative_prompt: str = "NO USER INPUT"
    ) -> str:
        """
        Build the chat-formatted prompt for format/rewrite mode.

        This formats user-provided caption and lyrics into a more detailed and specific
        musical description with metadata.

        Args:
            caption: User's caption/description of the music
            lyrics: User's lyrics
            is_negative_prompt: If True, builds unconditional prompt for CFG
            negative_prompt: Negative prompt for CFG (used when is_negative_prompt=True)

        Returns:
            Formatted prompt string

        Example:
            caption = "Latin pop, reggaeton, flamenco-pop"
            lyrics = "[Verse 1]\\nTengo un nudo..."
            prompt = handler.build_formatted_prompt_for_format(caption, lyrics)
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")

        if is_negative_prompt:
            # For CFG unconditional prompt
            user_content = negative_prompt if negative_prompt and negative_prompt.strip() else ""
        else:
            # Normal prompt: caption + lyrics
            user_content = f"# Caption\n{caption}\n\n# Lyric\n{lyrics}"

        return self.llm_tokenizer.apply_chat_template(
            [
                {
                    "role": "system",
                    "content": f"# Instruction\n{DEFAULT_LM_REWRITE_INSTRUCTION}\n\n"
                },
                {
                    "role": "user",
                    "content": user_content
                },
            ],
            tokenize=False,
            add_generation_prompt=True,
        )

    def format_sample_from_input(
        self,
        caption: str,
        lyrics: str,
        user_metadata: Optional[Dict[str, Any]] = None,
        temperature: float = 0.85,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        repetition_penalty: float = 1.0,
        use_constrained_decoding: bool = True,
        constrained_decoding_debug: bool = False,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Format user-provided caption and lyrics into structured music metadata.

        This is the "Format" feature that takes user input and generates:
        - Enhanced caption with detailed music description
        - Metadata (bpm, duration, keyscale, language, timesignature)
        - Formatted lyrics (preserved from input)

        Note: cfg_scale and negative_prompt are not supported in format mode.

        Args:
            caption: User's caption/description (e.g., "Latin pop, reggaeton")
            lyrics: User's lyrics with structure tags
            user_metadata: Optional dict with user-provided metadata to constrain decoding.
                          Supported keys: bpm, duration, keyscale, timesignature, language
            temperature: Sampling temperature for generation (0.0-2.0)
            top_k: Top-K sampling (None = disabled)
            top_p: Top-P (nucleus) sampling (None = disabled)
            repetition_penalty: Repetition penalty (1.0 = no penalty)
            use_constrained_decoding: Whether to use FSM-based constrained decoding
            constrained_decoding_debug: Whether to enable debug logging

        Returns:
            Tuple of (metadata_dict, status_message)
            metadata_dict contains:
                - bpm: int or str
                - caption: str (enhanced)
                - duration: int or str
                - keyscale: str
                - language: str
                - timesignature: str
                - lyrics: str (from input, possibly formatted)

        Example:
            caption = "Latin pop, reggaeton, flamenco-pop"
            lyrics = "[Verse 1]\\nTengo un nudo en la garganta..."
            metadata, status = handler.format_sample_from_input(caption, lyrics)
            print(metadata['caption'])  # "A dramatic and powerful Latin pop track..."
            print(metadata['bpm'])      # 100
        """
        if not getattr(self, "llm_initialized", False):
            return {}, "❌ 5Hz LM not initialized. Please initialize it first."

        if not caption or not caption.strip():
            caption = "NO USER INPUT"
        if not lyrics or not lyrics.strip():
            lyrics = "[Instrumental]"

        logger.info(f"Formatting sample from input: caption={caption[:50]}..., lyrics length={len(lyrics)}")

        # Build formatted prompt for format task
        formatted_prompt = self.build_formatted_prompt_for_format(
            caption=caption,
            lyrics=lyrics,
        )
        logger.debug(f"Formatted prompt for format: {formatted_prompt}")

        # Build constrained decoding metadata from user_metadata
        constrained_metadata = None
        if user_metadata:
            constrained_metadata = {}
            if user_metadata.get('bpm') is not None:
                try:
                    bpm_val = int(user_metadata['bpm'])
                    if bpm_val > 0:
                        constrained_metadata['bpm'] = bpm_val
                except (ValueError, TypeError):
                    pass
            if user_metadata.get('duration') is not None:
                try:
                    dur_val = int(user_metadata['duration'])
                    if dur_val > 0:
                        constrained_metadata['duration'] = dur_val
                except (ValueError, TypeError):
                    pass
            if user_metadata.get('keyscale'):
                constrained_metadata['keyscale'] = user_metadata['keyscale']
            if user_metadata.get('timesignature'):
                constrained_metadata['timesignature'] = user_metadata['timesignature']
            if user_metadata.get('language'):
                constrained_metadata['language'] = user_metadata['language']

            # Only use if we have at least one field
            if not constrained_metadata:
                constrained_metadata = None
            else:
                logger.info(f"Using user-provided metadata constraints: {constrained_metadata}")

        # Generate using constrained decoding (format phase)
        # Similar to understand/inspiration mode - generate metadata first (CoT), then formatted lyrics
        # Note: cfg_scale and negative_prompt are not used in format mode
        output_text, status = self.generate_from_formatted_prompt(
            formatted_prompt=formatted_prompt,
            cfg={
                "temperature": temperature,
                "top_k": top_k,
                "top_p": top_p,
                "repetition_penalty": repetition_penalty,
                "target_duration": None,  # No duration constraint for generation length
                "user_metadata": constrained_metadata,  # Inject user-provided metadata
                "skip_caption": False,  # Generate caption
                "skip_language": constrained_metadata.get('language') is not None if constrained_metadata else False,
                "skip_genres": False,  # Generate genres
                "generation_phase": "understand",  # Use understand phase for metadata + free-form lyrics
                "caption": "",
                "lyrics": "",
            },
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            stop_at_reasoning=False,  # Continue after </think> to get formatted lyrics
        )

        if not output_text:
            return {}, status

        # Parse metadata and extract lyrics
        metadata, _ = self.parse_lm_output(output_text)

        # Extract formatted lyrics section (everything after </think>)
        formatted_lyrics = self._extract_lyrics_from_output(output_text)
        if formatted_lyrics:
            metadata['lyrics'] = formatted_lyrics
        else:
            # If no lyrics generated, keep original input
            metadata['lyrics'] = lyrics

        logger.info(f"Format completed successfully. Generated {metadata} fields")
        if constrained_decoding_debug:
            logger.debug(f"Generated metadata: {list(metadata.keys())}")
            logger.debug(f"Output text preview: {output_text[:300]}...")

        status_msg = f"✅ Format completed successfully\nGenerated fields: {', '.join(metadata.keys())}"
        return metadata, status_msg

    def generate_from_formatted_prompt(
        self,
        formatted_prompt: str,
        cfg: Optional[Dict[str, Any]] = None,
        use_constrained_decoding: bool = True,
        constrained_decoding_debug: bool = False,
        stop_at_reasoning: bool = False,
    ) -> Tuple[str, str]:
        """
        Generate raw LM text output from a pre-built formatted prompt.

        Args:
            formatted_prompt: Prompt that is already formatted by `build_formatted_prompt`.
            cfg: Optional dict supporting keys:
                - temperature (float)
                - cfg_scale (float)
                - negative_prompt (str) used when cfg_scale > 1
                - top_k (int), top_p (float), repetition_penalty (float)
                - target_duration (float): Target duration in seconds for codes generation
                - generation_phase (str): "cot" or "codes" for phase-aware CFG
            use_constrained_decoding: Whether to use FSM-based constrained decoding
            constrained_decoding_debug: Whether to enable debug logging for constrained decoding
            stop_at_reasoning: If True, stop generation immediately after </think> tag (no audio codes)

        Returns:
            (output_text, status_message)

        Example:
            prompt = handler.build_formatted_prompt(caption, lyric)
            text, status = handler.generate_from_formatted_prompt(prompt, {"temperature": 0.7})
        """
        if not getattr(self, "llm_initialized", False):
            return "", "❌ 5Hz LM not initialized. Please initialize it first."
        # Check that the appropriate model is loaded for the active backend
        if self.llm_backend == "mlx":
            if self._mlx_model is None or self.llm_tokenizer is None:
                return "", "❌ 5Hz LM is missing MLX model or tokenizer."
        elif self.llm is None or self.llm_tokenizer is None:
            return "", "❌ 5Hz LM is missing model or tokenizer."

        cfg = cfg or {}
        temperature = cfg.get("temperature", 0.6)
        cfg_scale = cfg.get("cfg_scale", 1.0)
        negative_prompt = cfg.get("negative_prompt", "NO USER INPUT")
        top_k = cfg.get("top_k")
        top_p = cfg.get("top_p")
        repetition_penalty = cfg.get("repetition_penalty", 1.0)
        target_duration = cfg.get("target_duration")
        user_metadata = cfg.get("user_metadata")  # User-provided metadata fields
        skip_caption = cfg.get("skip_caption", False)  # Skip caption generation in CoT
        skip_language = cfg.get("skip_language", False)  # Skip language generation in CoT
        skip_genres = cfg.get("skip_genres", False)  # Skip genres generation in CoT
        generation_phase = cfg.get("generation_phase", "cot")  # "cot" or "codes"
        # Additional context for codes phase unconditional prompt building
        caption = cfg.get("caption", "")
        lyrics = cfg.get("lyrics", "")
        cot_text = cfg.get("cot_text", "")

        try:
            if self.llm_backend == "vllm":
                output_text = self._run_vllm(
                    formatted_prompts=formatted_prompt,
                    temperature=temperature,
                    cfg_scale=cfg_scale,
                    negative_prompt=negative_prompt,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    use_constrained_decoding=use_constrained_decoding,
                    constrained_decoding_debug=constrained_decoding_debug,
                    target_duration=target_duration,
                    user_metadata=user_metadata,
                    stop_at_reasoning=stop_at_reasoning,
                    skip_genres=skip_genres,
                    skip_caption=skip_caption,
                    skip_language=skip_language,
                    generation_phase=generation_phase,
                    caption=caption,
                    lyrics=lyrics,
                    cot_text=cot_text,
                )
                return output_text, f"✅ Generated successfully (vllm) | length={len(output_text)}"

            elif self.llm_backend == "mlx":
                # MLX backend (Apple Silicon native)
                output_text = self._run_mlx(
                    formatted_prompts=formatted_prompt,
                    temperature=temperature,
                    cfg_scale=cfg_scale,
                    negative_prompt=negative_prompt,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    use_constrained_decoding=use_constrained_decoding,
                    constrained_decoding_debug=constrained_decoding_debug,
                    target_duration=target_duration,
                    user_metadata=user_metadata,
                    stop_at_reasoning=stop_at_reasoning,
                    skip_genres=skip_genres,
                    skip_caption=skip_caption,
                    skip_language=skip_language,
                    generation_phase=generation_phase,
                    caption=caption,
                    lyrics=lyrics,
                    cot_text=cot_text,
                )
                return output_text, f"✅ Generated successfully (mlx) | length={len(output_text)}"

            # PyTorch backend (fallback)
            output_text = self._run_pt(
                formatted_prompts=formatted_prompt,
                temperature=temperature,
                cfg_scale=cfg_scale,
                negative_prompt=negative_prompt,
                top_k=top_k,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                use_constrained_decoding=use_constrained_decoding,
                constrained_decoding_debug=constrained_decoding_debug,
                target_duration=target_duration,
                user_metadata=user_metadata,
                stop_at_reasoning=stop_at_reasoning,
                skip_genres=skip_genres,
                skip_caption=skip_caption,
                skip_language=skip_language,
                generation_phase=generation_phase,
                caption=caption,
                lyrics=lyrics,
                cot_text=cot_text,
            )
            return output_text, f"✅ Generated successfully (pt) | length={len(output_text)}"

        except Exception as e:
            # Log full traceback for debugging
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"Error in generate_from_formatted_prompt: {type(e).__name__}: {e}\n{error_detail}")
            # Reset nano-vllm state on error to prevent stale context from causing
            # subsequent CUDA illegal memory access errors
            if self.llm_backend == "vllm":
                try:
                    from nanovllm.utils.context import reset_context
                    reset_context()
                except ImportError:
                    pass
                # Also reset the LLM scheduler to release allocated KV cache blocks
                # This prevents 'deque index out of range' errors from block leaks
                try:
                    if hasattr(self.llm, 'reset'):
                        self.llm.reset()
                except Exception:
                    pass  # Ignore errors during cleanup
            # Clear accelerator cache to release any corrupted memory
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            elif hasattr(torch, 'xpu') and torch.xpu.is_available():
                torch.xpu.empty_cache()
                torch.xpu.synchronize()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                torch.mps.empty_cache()
                torch.mps.synchronize()
            return "", f"❌ Error generating from formatted prompt: {type(e).__name__}: {e or error_detail.splitlines()[-1]}"

    def _generate_with_constrained_decoding(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor],
        max_new_tokens: int,
        temperature: float,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        pad_token_id: int,
        streamer: Optional[BaseStreamer],
        constrained_processor: Optional[MetadataConstrainedLogitsProcessor] = None,
    ) -> torch.Tensor:
        """
        Custom generation loop with constrained decoding support (non-CFG).
        This allows us to call update_state() after each token generation.
        """
        model = self.llm
        device = self.device

        # Initialize generated sequences
        generated_ids = input_ids.clone()
        if attention_mask is not None:
            attn_mask = attention_mask.clone()
        else:
            attn_mask = torch.ones_like(input_ids)

        # Prepare model inputs
        model_kwargs = {'attention_mask': attn_mask}

        # Past key values for KV cache
        past_key_values = None
        use_cache = hasattr(model, 'generation_config') and getattr(model.generation_config, 'use_cache', True)

        # Get EOS token ID
        eos_token_id = self.llm_tokenizer.eos_token_id
        if eos_token_id is None:
            eos_token_id = pad_token_id

        # Build logits processor for repetition penalty
        logits_processor = self._build_logits_processor(repetition_penalty)

        with torch.inference_mode():
            for step in tqdm(range(max_new_tokens), desc="LLM Constrained Decoding", unit="token", disable=self.disable_tqdm):
                # Forward pass
                outputs = self._forward_pass(model, generated_ids, model_kwargs, past_key_values, use_cache)

                # Get logits for the last position
                next_token_logits = outputs.logits[:, -1, :]  # [batch_size, vocab_size]

                # Apply constrained processor FIRST (modifies logits based on FSM state)
                if constrained_processor is not None:
                    next_token_logits = constrained_processor(generated_ids, next_token_logits)

                # Apply other logits processors (repetition penalty)
                for processor in logits_processor:
                    next_token_logits = processor(generated_ids, next_token_logits)

                # Apply top-k and top-p filtering
                next_token_logits = self._apply_top_k_filter(next_token_logits, top_k)
                next_token_logits = self._apply_top_p_filter(next_token_logits, top_p)

                # Apply temperature and sample
                next_tokens = self._sample_tokens(next_token_logits, temperature)

                # Update constrained processor state
                self._update_constrained_processor_state(constrained_processor, next_tokens)

                # Check for EOS token
                should_stop = self._check_eos_token(next_tokens, eos_token_id, pad_token_id)

                # Append token to sequence
                next_tokens_unsqueezed = next_tokens.unsqueeze(1)
                generated_ids = torch.cat([generated_ids, next_tokens_unsqueezed], dim=1)
                attn_mask = torch.cat([attn_mask, torch.ones((input_ids.shape[0], 1), device=device, dtype=attn_mask.dtype)], dim=1)
                model_kwargs['attention_mask'] = attn_mask

                # Update KV cache
                if use_cache and hasattr(outputs, 'past_key_values'):
                    past_key_values = outputs.past_key_values

                # Update streamer
                if streamer is not None:
                    streamer.put(next_tokens_unsqueezed)

                if should_stop:
                    break

        if streamer is not None:
            streamer.end()

        return generated_ids

    def _generate_with_cfg_custom(
        self,
        batch_input_ids: torch.Tensor,
        batch_attention_mask: Optional[torch.Tensor],
        max_new_tokens: int,
        temperature: float,
        cfg_scale: float,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        pad_token_id: int,
        streamer: Optional[BaseStreamer],
        constrained_processor: Optional[MetadataConstrainedLogitsProcessor] = None,
    ) -> torch.Tensor:
        """
        Custom CFG generation loop that:
        1. Processes both conditional and unconditional sequences in parallel
        2. Applies CFG formula to logits
        3. Samples tokens only for conditional sequences
        4. Applies the same sampled tokens to both conditional and unconditional sequences
        5. Optionally applies constrained decoding via FSM-based logits processor

        Batch format: [cond_input, uncond_input]
        """
        model = self.llm
        device = self.device
        batch_size = batch_input_ids.shape[0] // 2  # Half are conditional, half are unconditional
        cond_start_idx = 0
        uncond_start_idx = batch_size

        # Initialize generated sequences
        generated_ids = batch_input_ids.clone()
        if batch_attention_mask is not None:
            attention_mask = batch_attention_mask.clone()
        else:
            attention_mask = torch.ones_like(batch_input_ids)

        # Prepare model inputs
        model_kwargs = {}
        if batch_attention_mask is not None:
            model_kwargs['attention_mask'] = attention_mask

        # Past key values for KV cache (if model supports it)
        past_key_values = None
        use_cache = hasattr(model, 'generation_config') and getattr(model.generation_config, 'use_cache', True)

        # Get EOS token ID for stopping condition
        eos_token_id = self.llm_tokenizer.eos_token_id
        if eos_token_id is None:
            eos_token_id = pad_token_id

        # Build logits processor for non-CFG operations (repetition penalty, top_k, top_p)
        logits_processor = self._build_logits_processor(repetition_penalty)

        with torch.inference_mode():
            for step in tqdm(range(max_new_tokens), desc="LLM CFG Generation", unit="token", disable=self.disable_tqdm):
                # Forward pass for the entire batch (conditional + unconditional)
                outputs = self._forward_pass(model, generated_ids, model_kwargs, past_key_values, use_cache)

                # Get logits for the last position
                next_token_logits = outputs.logits[:, -1, :]  # [batch_size*2, vocab_size]

                # Split conditional and unconditional logits
                cond_logits = next_token_logits[cond_start_idx:cond_start_idx+batch_size]
                uncond_logits = next_token_logits[uncond_start_idx:uncond_start_idx+batch_size]

                # Apply CFG formula: cfg_logits = uncond_logits + cfg_scale * (cond_logits - uncond_logits)
                # Upcast to float32 to prevent overflow in float16 (CFG scaling can exceed fp16 range)
                cfg_logits = uncond_logits.float() + cfg_scale * (cond_logits.float() - uncond_logits.float())

                # Apply constrained processor FIRST (modifies logits based on FSM state)
                if constrained_processor is not None:
                    current_input_ids = generated_ids[cond_start_idx:cond_start_idx+batch_size]
                    cfg_logits = constrained_processor(current_input_ids, cfg_logits)

                # Apply logits processors (repetition penalty, top-k, top-p)
                # Get current input_ids for repetition penalty (only conditional part)
                current_input_ids = generated_ids[cond_start_idx:cond_start_idx+batch_size]
                for processor in logits_processor:
                    cfg_logits = processor(current_input_ids, cfg_logits)

                # Apply top-k and top-p filtering
                cfg_logits = self._apply_top_k_filter(cfg_logits, top_k)
                cfg_logits = self._apply_top_p_filter(cfg_logits, top_p)

                # Apply temperature and sample
                next_tokens = self._sample_tokens(cfg_logits, temperature)

                # Update constrained processor state AFTER sampling
                self._update_constrained_processor_state(constrained_processor, next_tokens)

                # Check for EOS token in conditional sequences BEFORE unsqueezing
                # Stop if any conditional sequence generates EOS token
                # next_tokens shape: [batch_size] (only conditional tokens)
                should_stop = self._check_eos_token(next_tokens, eos_token_id, pad_token_id)

                # Apply the same sampled tokens to both conditional and unconditional sequences
                next_tokens_unsqueezed = next_tokens.unsqueeze(1)
                generated_ids = torch.cat([generated_ids, next_tokens_unsqueezed.repeat(2, 1)], dim=1)
                attention_mask = torch.cat([attention_mask, torch.ones((batch_size*2, 1), device=device, dtype=attention_mask.dtype)], dim=1)
                model_kwargs['attention_mask'] = attention_mask

                # Update past_key_values for next iteration
                if use_cache and hasattr(outputs, 'past_key_values'):
                    past_key_values = outputs.past_key_values

                # Update streamer
                if streamer is not None:
                    streamer.put(next_tokens_unsqueezed)  # Stream conditional tokens

                # Stop generation if EOS token detected
                if should_stop:
                    break

        if streamer is not None:
            streamer.end()

        # Return the full batch (both conditional and unconditional)
        # The caller will extract only the conditional output
        return generated_ids

    def parse_lm_output(self, output_text: str) -> Tuple[Dict[str, Any], str]:
        """
        Parse LM output to extract metadata and audio codes.

        Expected format:
        <think>
        bpm: 73
        caption: A calm piano melody
        duration: 273
        genres: Chinese folk
        keyscale: G major
        language: en
        timesignature: 4
        </think>

        <|audio_code_56535|><|audio_code_62918|>...

        Returns:
            Tuple of (metadata_dict, audio_codes_string)
        """
        debug_output_text = output_text.split("</think>")[0]
        logger.debug(f"Debug output text: {debug_output_text}")
        metadata = {}
        audio_codes = ""

        import re

        # Extract audio codes - find all <|audio_code_XXX|> patterns
        code_pattern = r'<\|audio_code_\d+\|>'
        code_matches = re.findall(code_pattern, output_text)
        if code_matches:
            audio_codes = "".join(code_matches)

        # Extract metadata from reasoning section
        # Try different reasoning tag patterns
        reasoning_patterns = [
            r'<think>(.*?)</think>',
            r'<think>(.*?)</think>',
            r'<reasoning>(.*?)</reasoning>',
        ]

        reasoning_text = None
        for pattern in reasoning_patterns:
            match = re.search(pattern, output_text, re.DOTALL)
            if match:
                reasoning_text = match.group(1).strip()
                break

        # If no reasoning tags found, try to parse metadata from the beginning of output
        if not reasoning_text:
            # Look for metadata lines before audio codes
            lines_before_codes = output_text.split('<|audio_code_')[0] if '<|audio_code_' in output_text else output_text
            reasoning_text = lines_before_codes.strip()

        # Parse metadata fields with YAML multi-line value support
        if reasoning_text:
            lines = reasoning_text.split('\n')
            current_key = None
            current_value_lines = []

            def save_current_field():
                """Save the accumulated field value"""
                nonlocal current_key, current_value_lines
                if current_key and current_value_lines:
                    # Join multi-line value
                    value = '\n'.join(current_value_lines)

                    if current_key == 'bpm':
                        try:
                            metadata['bpm'] = int(value.strip())
                        except:
                            metadata['bpm'] = value.strip()
                    elif current_key == 'caption':
                        # Post-process caption to remove YAML multi-line formatting
                        metadata['caption'] = MetadataConstrainedLogitsProcessor.postprocess_caption(value)
                    elif current_key == 'duration':
                        try:
                            metadata['duration'] = int(value.strip())
                        except:
                            metadata['duration'] = value.strip()
                    elif current_key == 'genres':
                        metadata['genres'] = value.strip()
                    elif current_key == 'keyscale':
                        metadata['keyscale'] = value.strip()
                    elif current_key == 'language':
                        metadata['language'] = value.strip()
                    elif current_key == 'timesignature':
                        metadata['timesignature'] = value.strip()

                current_key = None
                current_value_lines = []

            for line in lines:
                # Skip lines starting with '<' (tags)
                if line.strip().startswith('<'):
                    continue

                # Check if this is a new field (no leading spaces and contains ':')
                if line and not line[0].isspace() and ':' in line:
                    # Save previous field if any
                    save_current_field()

                    # Parse new field
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        current_key = parts[0].strip().lower()
                        # First line of value (after colon)
                        first_value = parts[1]
                        if first_value.strip():
                            current_value_lines.append(first_value)
                elif line.startswith(' ') or line.startswith('\t'):
                    # Continuation line (YAML multi-line value)
                    if current_key:
                        current_value_lines.append(line)

            # Don't forget to save the last field
            save_current_field()

        return metadata, audio_codes

    # =========================================================================
    # MLX Backend Methods (Apple Silicon native acceleration)
    # =========================================================================

    @staticmethod
    def _is_mlx_available() -> bool:
        """Check if MLX framework is available (Apple Silicon)."""
        try:
            import mlx.core as mx
            import mlx_lm
            return True
        except ImportError:
            return False

    def _load_mlx_model(self, model_path: str) -> Tuple[bool, str]:
        """
        Load the 5Hz LM model using mlx-lm for native Apple Silicon acceleration.

        Args:
            model_path: Path to the HuggingFace model directory

        Returns:
            Tuple of (success, status_message)
        """
        try:
            import mlx.core as mx
            from mlx_lm.utils import load as mlx_load

            logger.info(f"Loading MLX model from {model_path}")
            start_time = time.time()

            # Try standard mlx-lm load first
            try:
                self._mlx_model, _ = mlx_load(model_path)
            except Exception as first_err:
                # The ACE-Step 5Hz LM checkpoints store safetensors keys without
                # the "model." prefix (e.g. "layers.0.xxx" instead of
                # "model.layers.0.xxx") which is what mlx-lm's Qwen3 model
                # expects.  When the standard load fails we retry with the
                # prefix remapped.
                logger.info(
                    f"Standard MLX load failed ({first_err}), "
                    "retrying with 'model.' prefix remapping..."
                )
                import glob as _glob
                from pathlib import Path
                from mlx_lm.utils import load_model, load_config, load_tokenizer, _get_classes

                _model_path = Path(model_path)
                config = load_config(_model_path)

                # Load raw weights from safetensors
                weight_files = _glob.glob(str(_model_path / "model*.safetensors"))
                if not weight_files:
                    raise FileNotFoundError(f"No safetensors found in {model_path}") from first_err

                weights = {}
                for wf in weight_files:
                    weights.update(mx.load(wf))

                # Check if keys need "model." prefix by inspecting first key
                sample_key = next(iter(weights))
                if not sample_key.startswith("model."):
                    logger.info("Adding 'model.' prefix to weight keys for MLX compatibility")
                    weights = {f"model.{k}": v for k, v in weights.items()}

                # Build model from config
                model_class, model_args_class = _get_classes(config=config)
                model_args = model_args_class.from_dict(config)
                model = model_class(model_args)

                if hasattr(model, "sanitize"):
                    weights = model.sanitize(weights)

                model.load_weights(list(weights.items()), strict=True)
                mx.eval(model.parameters())
                model.eval()
                self._mlx_model = model

            mx.eval(self._mlx_model.parameters())
            # Store model path for get_hf_model_for_scoring
            self._mlx_model_path = model_path

            load_time = time.time() - start_time
            logger.info(f"MLX model loaded successfully in {load_time:.2f}s")

            self.llm_backend = "mlx"
            self.llm_initialized = True
            status_msg = (
                f"✅ 5Hz LM initialized successfully\n"
                f"Model: {model_path}\n"
                f"Backend: MLX (Apple Silicon native)\n"
                f"Device: Apple Silicon GPU"
            )
            return True, status_msg

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.warning(f"Failed to load MLX model: {e}\n{error_detail}")
            return False, f"❌ MLX load failed: {str(e)}"

    def _make_mlx_cache(self):
        """Create a KV cache for the MLX model."""
        import mlx.core as mx
        try:
            from mlx_lm.models.cache import make_prompt_cache
            return make_prompt_cache(self._mlx_model)
        except (ImportError, AttributeError):
            # Fallback: try model's own cache creation
            try:
                return self._mlx_model.make_cache()
            except AttributeError:
                raise RuntimeError(
                    "Cannot create MLX KV cache. Ensure mlx-lm version >= 0.20.0"
                )

    def _run_mlx_batch_native(
        self,
        formatted_prompt: str,
        batch_size: int,
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool,
        constrained_decoding_debug: bool,
        target_duration: Optional[float],
        caption: str,
        lyrics: str,
        cot_text: str,
        seeds: Optional[List[int]] = None,
    ) -> List[str]:
        """
        Optimized native MLX batch generation for codes phase.

        Strategy: shared prefill + clone cache + interleaved B=1 decode.

        On Apple Silicon, LLM decode is memory-bandwidth-bound. Batching the
        forward pass (B>1) doubles the KV cache reads per step and actually
        *slows down* throughput for 1.7B-class models. Instead, we:

        1. Prefill ONCE with B=1, then clone the KV caches for each item.
           This saves ~50% of prefill time vs sequential generation.
        2. Interleave B=1 forward passes across items within each step.
           Each item gets its own cache, constrained state, and seed.

        This achieves ~1.25x speedup over fully sequential generation while
        maintaining the full ~44 tok/s per-item decode speed.

        Only used for codes generation phase where all prompts are identical.
        Raises on failure so the caller can fall back to sequential mode.
        """
        import mlx.core as mx
        import numpy as np
        from mlx_lm.models.cache import make_prompt_cache, KVCache
        from mlx_lm.sample_utils import make_sampler

        # ---- Tokenize (single prompt, shared by all items) ----
        inputs = self.llm_tokenizer(
            formatted_prompt,
            return_tensors="np",
            padding=False,
            truncation=True,
        )
        input_ids_np = inputs["input_ids"]  # [1, seq_len]
        prompt_length = input_ids_np.shape[1]
        prompt = mx.array(input_ids_np[0])  # 1D [seq_len]

        # ---- Calculate max_new_tokens ----
        # Batch native is always codes phase
        max_new_tokens = self._compute_max_new_tokens(
            target_duration=target_duration,
            generation_phase="codes",
        )

        # ---- EOS tokens ----
        eos_token_id = self.llm_tokenizer.eos_token_id
        pad_token_id = self.llm_tokenizer.pad_token_id or eos_token_id

        # ---- Native MLX sampler ----
        sampler = make_sampler(
            temp=temperature if temperature > 0 else 0.0,
            top_p=top_p if top_p is not None and 0.0 < top_p < 1.0 else 1.0,
            top_k=top_k if top_k is not None and top_k > 0 else 0,
        )

        # ---- Repetition penalty config ----
        use_rep_penalty = repetition_penalty != 1.0
        rep_penalty_val = float(repetition_penalty)

        use_cfg = cfg_scale > 1.0
        cfg_label = "CFG " if use_cfg else ""
        prefill_step_size = 2048

        # ---- Pre-convert constrained masks to MLX (shared by all items) ----
        from acestep.constrained_logits_processor import FSMState
        _mlx_non_audio_mask = None
        _mlx_eos_id = None
        _target_codes = None

        # Setup a temporary constrained processor to get masks
        constrained_processor = self._setup_constrained_processor(
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=None,
            stop_at_reasoning=False,
            skip_genres=True,
            skip_caption=True,
            skip_language=True,
            generation_phase="codes",
            is_batch=True,
        )

        if constrained_processor is not None:
            if hasattr(constrained_processor, 'non_audio_code_mask') and constrained_processor.non_audio_code_mask is not None:
                _mlx_non_audio_mask = mx.array(constrained_processor.non_audio_code_mask.float().numpy())
            if hasattr(constrained_processor, 'eos_token_id') and constrained_processor.eos_token_id is not None:
                _mlx_eos_id = int(constrained_processor.eos_token_id)
            if hasattr(constrained_processor, 'target_codes'):
                _target_codes = constrained_processor.target_codes

            # Pre-transition FSM to CODES_GENERATION
            if constrained_processor.state == FSMState.THINK_TAG:
                if "</think>" in formatted_prompt:
                    constrained_processor.state = FSMState.CODES_GENERATION
                    constrained_processor.codes_count = 0

        # ===== SHARED PREFILL PHASE (done ONCE for all batch items) =====
        prefill_start = time.time()
        logger.info(f"MLX batch native: prefilling once for {batch_size} items (shared prompt)")

        def _clone_cache_list(cache_list):
            """Deep-copy a list of KVCache objects so each batch item gets independent state."""
            cloned = []
            for c in cache_list:
                new_c = KVCache()
                if c.keys is not None:
                    # mx.array(...) on an existing array creates a copy
                    new_c.keys = mx.array(c.keys)
                    new_c.values = mx.array(c.values)
                    new_c.offset = c.offset
                cloned.append(new_c)
            return cloned

        if use_cfg:
            # Build unconditional prompt
            uncond_text = self._build_unconditional_prompt(
                caption=caption, lyrics=lyrics, cot_text=cot_text,
                negative_prompt=negative_prompt, generation_phase="codes", is_batch=True,
            )
            uncond_inputs = self.llm_tokenizer(
                uncond_text, return_tensors="np", padding=False, truncation=True,
            )
            uncond_prompt = mx.array(uncond_inputs["input_ids"][0])
            uncond_length = len(uncond_prompt)

            # Create single KV caches and prefill once
            base_cond_cache = make_prompt_cache(self._mlx_model)
            base_uncond_cache = make_prompt_cache(self._mlx_model)

            # Chunked prefill for conditional prompt
            cond_remaining = prompt
            while len(cond_remaining) > 1:
                chunk_size = min(prefill_step_size, len(cond_remaining) - 1)
                self._mlx_model(cond_remaining[:chunk_size][None], cache=base_cond_cache)
                mx.eval([c.state for c in base_cond_cache])
                cond_remaining = cond_remaining[chunk_size:]
                mx.clear_cache()

            # Chunked prefill for unconditional prompt
            uncond_remaining = uncond_prompt
            while len(uncond_remaining) > 1:
                chunk_size = min(prefill_step_size, len(uncond_remaining) - 1)
                self._mlx_model(uncond_remaining[:chunk_size][None], cache=base_uncond_cache)
                mx.eval([c.state for c in base_uncond_cache])
                uncond_remaining = uncond_remaining[chunk_size:]
                mx.clear_cache()

            # Process last tokens of both prompts to get initial logits
            base_cond_logits = self._mlx_model(cond_remaining[None], cache=base_cond_cache)
            base_uncond_logits = self._mlx_model(uncond_remaining[None], cache=base_uncond_cache)
            mx.eval(base_cond_logits, base_uncond_logits)

            # Clone caches for each batch item (item 0 reuses the base cache)
            item_cond_caches = [base_cond_cache]
            item_uncond_caches = [base_uncond_cache]
            for i in range(1, batch_size):
                item_cond_caches.append(_clone_cache_list(base_cond_cache))
                item_uncond_caches.append(_clone_cache_list(base_uncond_cache))
            # Eval cloned caches
            for i in range(1, batch_size):
                mx.eval(*[c.keys for c in item_cond_caches[i] if c.keys is not None])
                mx.eval(*[c.keys for c in item_uncond_caches[i] if c.keys is not None])

            # Initial logits for each item (same values, but we need separate references)
            item_last_cond = [base_cond_logits[:, -1:, :]] * batch_size
            item_last_uncond = [base_uncond_logits[:, -1:, :]] * batch_size

            prefill_time = time.time() - prefill_start
            total_prefill_tokens = prompt_length + uncond_length
            prefill_tps = total_prefill_tokens / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX batch native prefill: {total_prefill_tokens} tokens "
                f"(cond={prompt_length}, uncond={uncond_length}) "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s) "
                f"[shared across {batch_size} items, saved {(batch_size-1)*total_prefill_tokens} redundant tokens]"
            )
        else:
            # Non-CFG mode
            base_cache = make_prompt_cache(self._mlx_model)
            remaining = prompt
            while len(remaining) > 1:
                chunk_size = min(prefill_step_size, len(remaining) - 1)
                self._mlx_model(remaining[:chunk_size][None], cache=base_cache)
                mx.eval([c.state for c in base_cache])
                remaining = remaining[chunk_size:]
                mx.clear_cache()

            base_logits = self._mlx_model(remaining[None], cache=base_cache)
            mx.eval(base_logits)

            item_caches = [base_cache]
            for i in range(1, batch_size):
                item_caches.append(_clone_cache_list(base_cache))
            for i in range(1, batch_size):
                mx.eval(*[c.keys for c in item_caches[i] if c.keys is not None])

            item_last_logits = [base_logits[:, -1:, :]] * batch_size

            prefill_time = time.time() - prefill_start
            prefill_tps = prompt_length / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX batch native prefill: {prompt_length} tokens "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s) "
                f"[shared across {batch_size} items]"
            )

        # ===== INTERLEAVED AUTOREGRESSIVE GENERATION LOOP =====
        # Each item has independent: tokens, codes_count, finished flag, KV cache, random key
        # But they share: model weights, masks, sampler
        #
        # Why interleaved B=1 instead of true batch B=N?
        # On Apple Silicon, LLM decode is memory-bandwidth-bound.
        # B=2 doubles KV cache reads per step, causing ~3x slowdown per step
        # for 1.7B models. Interleaved B=1 keeps the full ~44 tok/s speed
        # while still sharing the prefill computation.
        base_token_ids = list(input_ids_np[0])
        item_all_token_ids = [list(base_token_ids) for _ in range(batch_size)]
        item_new_tokens = [[] for _ in range(batch_size)]
        item_codes_count = [0] * batch_size
        item_finished = [False] * batch_size

        # Pre-compute per-item seed bases (large primes to avoid correlation)
        item_seed_bases = []
        for i in range(batch_size):
            if seeds and i < len(seeds):
                item_seed_bases.append(seeds[i])
            else:
                item_seed_bases.append(42 + i * 1000003)

        decode_start = time.time()
        pbar = tqdm(total=max_new_tokens, desc=f"MLX {cfg_label}Batch Gen (native, n={batch_size})", unit="tok")

        for step in range(max_new_tokens):
            # Check if all items are done
            if all(item_finished):
                break

            # Process each active item (interleaved B=1 forward passes)
            for i in range(batch_size):
                if item_finished[i]:
                    continue

                # ---- Set deterministic per-item seed for this step ----
                # This ensures reproducibility: item i at step s always uses the same seed
                mx.random.seed(item_seed_bases[i] + step * 1000003)

                # ---- Combine logits (CFG) ----
                if use_cfg:
                    step_logits = item_last_uncond[i] + cfg_scale * (item_last_cond[i] - item_last_uncond[i])
                else:
                    step_logits = item_last_logits[i]

                step_logits = step_logits.reshape(1, -1)  # [1, vocab_size]

                # ---- Repetition penalty ----
                if use_rep_penalty and len(item_all_token_ids[i]) > 0:
                    token_indices = mx.array(item_all_token_ids[i])
                    selected = step_logits[:, token_indices]
                    modified = mx.where(
                        selected > 0,
                        selected / rep_penalty_val,
                        selected * rep_penalty_val,
                    )
                    step_logits[:, token_indices] = modified

                # ---- Constrained decoding (native MLX fast path) ----
                if _mlx_non_audio_mask is not None:
                    step_logits = step_logits + _mlx_non_audio_mask
                if _target_codes is not None and _mlx_eos_id is not None:
                    if item_codes_count[i] < _target_codes:
                        step_logits = mx.concatenate([
                            step_logits[:, :_mlx_eos_id],
                            mx.array([[float('-inf')]]),
                            step_logits[:, _mlx_eos_id + 1:],
                        ], axis=1)
                    else:
                        eos_val = step_logits[:, _mlx_eos_id:_mlx_eos_id + 1]
                        step_logits = mx.full(step_logits.shape, float('-inf'))
                        step_logits = mx.concatenate([
                            step_logits[:, :_mlx_eos_id],
                            eos_val,
                            step_logits[:, _mlx_eos_id + 1:],
                        ], axis=1)

                # ---- Sample ----
                logprobs = step_logits - mx.logsumexp(step_logits, keepdims=True)
                token_arr = sampler(logprobs)
                mx.eval(token_arr)
                token_id = token_arr.item()

                item_new_tokens[i].append(token_id)
                item_all_token_ids[i].append(token_id)

                # Update codes count
                item_codes_count[i] += 1

                # Check EOS
                if token_id == eos_token_id:
                    item_finished[i] = True
                    continue
                if pad_token_id is not None and pad_token_id != eos_token_id and token_id == pad_token_id:
                    item_finished[i] = True
                    continue

                # ---- Next forward step (B=1 per item) ----
                next_input = mx.array([[token_id]])
                if use_cfg:
                    cond_logits = self._mlx_model(next_input, cache=item_cond_caches[i])
                    uncond_logits = self._mlx_model(next_input, cache=item_uncond_caches[i])
                    item_last_cond[i] = cond_logits[:, -1:, :]
                    item_last_uncond[i] = uncond_logits[:, -1:, :]
                else:
                    logits_out = self._mlx_model(next_input, cache=item_caches[i])
                    item_last_logits[i] = logits_out[:, -1:, :]

            pbar.update(1)

            # Periodic memory cleanup
            if step % 256 == 0 and step > 0:
                mx.clear_cache()

        pbar.close()

        # ---- Log generation summary ----
        decode_time = time.time() - decode_start
        total_tokens = sum(len(t) for t in item_new_tokens)
        avg_tokens = total_tokens / batch_size if batch_size > 0 else 0
        decode_tps = total_tokens / decode_time if decode_time > 0 else 0
        total_time = prefill_time + decode_time
        logger.info(
            f"MLX batch native generation complete: {batch_size} items, "
            f"{total_tokens} total tokens ({avg_tokens:.0f} avg) in {decode_time:.2f}s "
            f"({decode_tps:.1f} tok/s) | prefill {prefill_time:.2f}s + decode {decode_time:.2f}s = {total_time:.2f}s total"
        )

        # Decode each item's tokens
        output_texts = []
        for i in range(batch_size):
            output_text = self.llm_tokenizer.decode(item_new_tokens[i], skip_special_tokens=False)
            output_texts.append(output_text)

        return output_texts

    def _run_mlx_single_native(
        self,
        formatted_prompt: str,
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool,
        constrained_decoding_debug: bool,
        target_duration: Optional[float],
        user_metadata: Optional[Dict[str, Optional[str]]],
        stop_at_reasoning: bool,
        skip_genres: bool,
        skip_caption: bool,
        skip_language: bool,
        generation_phase: str,
        caption: str,
        lyrics: str,
        cot_text: str,
    ) -> str:
        """
        Optimized native MLX generation using mlx-lm infrastructure.

        Key improvements over the hybrid approach:
        1. Native MLX sampling (temperature, top-k, top-p) via mlx-lm make_sampler
           - Eliminates numpy/PyTorch round-trip for EVERY generated token
        2. Native MLX repetition penalty (no per-step PyTorch conversion)
        3. Chunked prefill for memory-efficient long prompt processing
        4. Periodic memory cleanup (mx.clear_cache) matching mlx-lm patterns
        5. Bridges to PyTorch ONLY for constrained decoding FSM when active

        Raises on failure so the caller can fall back to the legacy hybrid method.
        """
        import mlx.core as mx
        import numpy as np
        from mlx_lm.models.cache import make_prompt_cache
        from mlx_lm.sample_utils import make_sampler

        # ---- Tokenize ----
        inputs = self.llm_tokenizer(
            formatted_prompt,
            return_tensors="np",
            padding=False,
            truncation=True,
        )
        input_ids_np = inputs["input_ids"]  # [1, seq_len]
        prompt_length = input_ids_np.shape[1]
        prompt = mx.array(input_ids_np[0])  # 1D [seq_len]

        # ---- Setup constrained processor ----
        constrained_processor = self._setup_constrained_processor(
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            is_batch=False,
        )

        # ---- Calculate max_new_tokens ----
        max_new_tokens = self._compute_max_new_tokens(
            target_duration=target_duration,
            generation_phase=generation_phase,
        )

        # ---- EOS tokens ----
        eos_token_id = self.llm_tokenizer.eos_token_id
        pad_token_id = self.llm_tokenizer.pad_token_id or eos_token_id

        # ---- Native MLX sampler (replaces PyTorch top-k/top-p/temperature) ----
        sampler = make_sampler(
            temp=temperature if temperature > 0 else 0.0,
            top_p=top_p if top_p is not None and 0.0 < top_p < 1.0 else 1.0,
            top_k=top_k if top_k is not None and top_k > 0 else 0,
        )

        # ---- Repetition penalty config ----
        use_rep_penalty = repetition_penalty != 1.0
        rep_penalty_val = float(repetition_penalty)

        use_cfg = cfg_scale > 1.0
        cfg_label = "CFG " if use_cfg else ""
        tqdm_desc = f"MLX {cfg_label}Gen (native)"
        prefill_step_size = 2048

        # ---- Pre-convert constrained processor masks to MLX (one-time) ----
        # This enables native MLX fast-path for CODES_GENERATION state,
        # eliminating the PyTorch bridge for 99%+ of Phase 2 tokens.
        from acestep.constrained_logits_processor import FSMState
        _mlx_non_audio_mask = None
        _mlx_eos_id = None
        _target_codes = None
        _use_native_codes_path = False

        if constrained_processor is not None:
            # Pre-convert the non-audio-code mask to MLX (blocks everything except audio codes + EOS)
            if hasattr(constrained_processor, 'non_audio_code_mask') and constrained_processor.non_audio_code_mask is not None:
                _mlx_non_audio_mask = mx.array(constrained_processor.non_audio_code_mask.float().numpy())
            if hasattr(constrained_processor, 'eos_token_id') and constrained_processor.eos_token_id is not None:
                _mlx_eos_id = int(constrained_processor.eos_token_id)
            if hasattr(constrained_processor, 'target_codes'):
                _target_codes = constrained_processor.target_codes

            # For codes phase, the prompt already contains </think>.
            # Pre-transition FSM to CODES_GENERATION so the native fast path
            # activates from the very first generated token.
            if generation_phase == "codes" and constrained_processor.state == FSMState.THINK_TAG:
                if "</think>" in formatted_prompt:
                    constrained_processor.state = FSMState.CODES_GENERATION
                    constrained_processor.codes_count = 0
                    _use_native_codes_path = True
                    logger.info("MLX native: pre-transitioned FSM to CODES_GENERATION (native fast path)")

        # ===== PREFILL PHASE =====
        prefill_start = time.time()

        if use_cfg:
            # Build unconditional prompt
            uncond_text = self._build_unconditional_prompt(
                caption=caption,
                lyrics=lyrics,
                cot_text=cot_text,
                negative_prompt=negative_prompt,
                generation_phase=generation_phase,
                is_batch=False,
            )
            uncond_inputs = self.llm_tokenizer(
                uncond_text,
                return_tensors="np",
                padding=False,
                truncation=True,
            )
            uncond_prompt = mx.array(uncond_inputs["input_ids"][0])
            uncond_length = len(uncond_prompt)

            # Create KV caches via mlx-lm infrastructure
            cond_cache = make_prompt_cache(self._mlx_model)
            uncond_cache = make_prompt_cache(self._mlx_model)

            # Chunked prefill for conditional prompt
            cond_remaining = prompt
            while len(cond_remaining) > 1:
                chunk_size = min(prefill_step_size, len(cond_remaining) - 1)
                self._mlx_model(cond_remaining[:chunk_size][None], cache=cond_cache)
                mx.eval([c.state for c in cond_cache])
                cond_remaining = cond_remaining[chunk_size:]
                mx.clear_cache()

            # Chunked prefill for unconditional prompt
            uncond_remaining = uncond_prompt
            while len(uncond_remaining) > 1:
                chunk_size = min(prefill_step_size, len(uncond_remaining) - 1)
                self._mlx_model(uncond_remaining[:chunk_size][None], cache=uncond_cache)
                mx.eval([c.state for c in uncond_cache])
                uncond_remaining = uncond_remaining[chunk_size:]
                mx.clear_cache()

            # Process last tokens of both prompts
            cond_logits = self._mlx_model(cond_remaining[None], cache=cond_cache)
            uncond_logits = self._mlx_model(uncond_remaining[None], cache=uncond_cache)
            mx.eval(cond_logits, uncond_logits)

            last_cond = cond_logits[:, -1:, :]
            last_uncond = uncond_logits[:, -1:, :]

            prefill_time = time.time() - prefill_start
            total_prefill_tokens = prompt_length + uncond_length
            prefill_tps = total_prefill_tokens / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX native prefill: {total_prefill_tokens} tokens "
                f"(cond={prompt_length}, uncond={uncond_length}) "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s)"
            )
        else:
            # Non-CFG: single cache
            cache = make_prompt_cache(self._mlx_model)

            # Chunked prefill
            remaining = prompt
            while len(remaining) > 1:
                chunk_size = min(prefill_step_size, len(remaining) - 1)
                self._mlx_model(remaining[:chunk_size][None], cache=cache)
                mx.eval([c.state for c in cache])
                remaining = remaining[chunk_size:]
                mx.clear_cache()

            logits_out = self._mlx_model(remaining[None], cache=cache)
            mx.eval(logits_out)
            last_logits = logits_out[:, -1:, :]

            prefill_time = time.time() - prefill_start
            prefill_tps = prompt_length / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX native prefill: {prompt_length} tokens "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s)"
            )

        # ===== AUTOREGRESSIVE GENERATION LOOP =====
        all_token_ids = list(input_ids_np[0])
        new_tokens = []
        decode_start = time.time()

        pbar = tqdm(total=max_new_tokens, desc=tqdm_desc, unit="tok")
        for step in range(max_new_tokens):
            # ---- Combine logits (CFG formula in MLX, lazy) ----
            if use_cfg:
                step_logits = last_uncond + cfg_scale * (last_cond - last_uncond)
            else:
                step_logits = last_logits

            step_logits = step_logits.reshape(1, -1)  # [1, vocab_size]

            # ---- Native MLX repetition penalty (lazy) ----
            if use_rep_penalty and len(all_token_ids) > 0:
                token_indices = mx.array(all_token_ids)
                selected = step_logits[:, token_indices]
                modified = mx.where(
                    selected > 0,
                    selected / rep_penalty_val,
                    selected * rep_penalty_val,
                )
                step_logits[:, token_indices] = modified

            # ---- Constrained decoding: native MLX fast path vs PyTorch bridge ----
            if constrained_processor is not None:
                _cp_state = constrained_processor.state

                if _cp_state == FSMState.CODES_GENERATION:
                    # === NATIVE MLX FAST PATH (no PyTorch bridge!) ===
                    # Apply non-audio-code mask (blocks everything except audio codes + EOS)
                    if _mlx_non_audio_mask is not None:
                        step_logits = step_logits + _mlx_non_audio_mask
                    # Duration constraint: block or force EOS
                    if _target_codes is not None and _mlx_eos_id is not None:
                        if constrained_processor.codes_count < _target_codes:
                            # Block EOS until target codes reached
                            step_logits = mx.concatenate([
                                step_logits[:, :_mlx_eos_id],
                                mx.array([[float('-inf')]]),
                                step_logits[:, _mlx_eos_id + 1:],
                            ], axis=1)
                        else:
                            # Force EOS when target reached
                            eos_val = step_logits[:, _mlx_eos_id:_mlx_eos_id + 1]
                            step_logits = mx.full(step_logits.shape, float('-inf'))
                            step_logits = mx.concatenate([
                                step_logits[:, :_mlx_eos_id],
                                eos_val,
                                step_logits[:, _mlx_eos_id + 1:],
                            ], axis=1)

                elif _cp_state == FSMState.COMPLETED:
                    # No-op: COMPLETED state in codes/cot phase is passthrough
                    pass

                else:
                    # === PYTORCH BRIDGE (metadata states during CoT phase) ===
                    step_logits_f32 = step_logits.astype(mx.float32)
                    np_logits = np.array(step_logits_f32, copy=True)
                    t_logits = torch.from_numpy(np_logits)
                    t_ids = torch.tensor([all_token_ids], dtype=torch.long)
                    t_logits = constrained_processor(t_ids, t_logits)
                    step_logits = mx.array(t_logits.numpy())

            # ---- Native MLX sampling (temperature + top-k + top-p) ----
            logprobs = step_logits - mx.logsumexp(step_logits, keepdims=True)
            token_arr = sampler(logprobs)
            mx.eval(token_arr)  # SINGLE sync point per token
            token_id = token_arr.item()

            new_tokens.append(token_id)
            all_token_ids.append(token_id)
            pbar.update(1)

            # Update constrained processor FSM state
            if constrained_processor is not None:
                constrained_processor.update_state(token_id)

            # Check EOS
            if token_id == eos_token_id:
                break
            if pad_token_id is not None and pad_token_id != eos_token_id and token_id == pad_token_id:
                break

            # ---- Next forward step in MLX (LAZY - no eval!) ----
            # By deferring evaluation, the entire pipeline (forward + CFG + mask + sample)
            # executes as one fused graph when mx.eval(token_arr) is called next iteration.
            next_input = mx.array([[token_id]])
            if use_cfg:
                cond_logits = self._mlx_model(next_input, cache=cond_cache)
                uncond_logits = self._mlx_model(next_input, cache=uncond_cache)
                last_cond = cond_logits[:, -1:, :]
                last_uncond = uncond_logits[:, -1:, :]
            else:
                logits_out = self._mlx_model(next_input, cache=cache)
                last_logits = logits_out[:, -1:, :]

            # Periodic memory cleanup (every 256 tokens, matching mlx-lm pattern)
            if step % 256 == 0 and step > 0:
                mx.clear_cache()

        pbar.close()

        # ---- Log generation summary ----
        decode_time = time.time() - decode_start
        num_generated = len(new_tokens)
        decode_tps = num_generated / decode_time if decode_time > 0 else 0
        total_time = prefill_time + decode_time
        logger.info(
            f"MLX native generation complete: {num_generated} tokens in {decode_time:.2f}s "
            f"({decode_tps:.1f} tok/s) | prefill {prefill_time:.2f}s + decode {decode_time:.2f}s = {total_time:.2f}s total"
        )

        # Decode new tokens only
        output_text = self.llm_tokenizer.decode(new_tokens, skip_special_tokens=False)
        return output_text

    def _run_mlx_single(
        self,
        formatted_prompt: str,
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool,
        constrained_decoding_debug: bool,
        target_duration: Optional[float],
        user_metadata: Optional[Dict[str, Optional[str]]],
        stop_at_reasoning: bool,
        skip_genres: bool,
        skip_caption: bool,
        skip_language: bool,
        generation_phase: str,
        caption: str,
        lyrics: str,
        cot_text: str,
    ) -> str:
        """
        MLX-accelerated single-item generation.

        Tries optimized native MLX generation first (using mlx-lm infrastructure
        for sampling, repetition penalty, and chunked prefill). Falls back to
        hybrid MLX/PyTorch approach if native generation fails.
        """
        # ---- Try optimized native MLX generation ----
        try:
            return self._run_mlx_single_native(
                formatted_prompt=formatted_prompt,
                temperature=temperature,
                cfg_scale=cfg_scale,
                negative_prompt=negative_prompt,
                top_k=top_k,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                use_constrained_decoding=use_constrained_decoding,
                constrained_decoding_debug=constrained_decoding_debug,
                target_duration=target_duration,
                user_metadata=user_metadata,
                stop_at_reasoning=stop_at_reasoning,
                skip_genres=skip_genres,
                skip_caption=skip_caption,
                skip_language=skip_language,
                generation_phase=generation_phase,
                caption=caption,
                lyrics=lyrics,
                cot_text=cot_text,
            )
        except Exception as _native_err:
            logger.warning(
                f"Native MLX generation failed ({type(_native_err).__name__}: {_native_err}), "
                f"falling back to hybrid mode"
            )

        # ---- Fallback: Legacy hybrid MLX/PyTorch generation ----
        import mlx.core as mx
        import numpy as np

        # Tokenize prompt
        inputs = self.llm_tokenizer(
            formatted_prompt,
            return_tensors="np",
            padding=False,
            truncation=True,
        )
        input_ids_np = inputs["input_ids"]  # [1, seq_len]
        prompt_length = input_ids_np.shape[1]
        prompt = mx.array(input_ids_np)

        # Setup constrained processor
        constrained_processor = self._setup_constrained_processor(
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            is_batch=False,
        )

        # Calculate max_new_tokens
        max_new_tokens = self._compute_max_new_tokens(
            target_duration=target_duration,
            generation_phase=generation_phase,
        )

        # EOS token
        eos_token_id = self.llm_tokenizer.eos_token_id
        pad_token_id = self.llm_tokenizer.pad_token_id or eos_token_id

        use_cfg = cfg_scale > 1.0
        cfg_label = "CFG " if use_cfg else ""
        tqdm_desc = f"MLX {cfg_label}Generation"

        # ---- Prefill phase ----
        prefill_start = time.time()
        if use_cfg:
            # Build unconditional prompt
            uncond_text = self._build_unconditional_prompt(
                caption=caption,
                lyrics=lyrics,
                cot_text=cot_text,
                negative_prompt=negative_prompt,
                generation_phase=generation_phase,
                is_batch=False,
            )
            uncond_inputs = self.llm_tokenizer(
                uncond_text,
                return_tensors="np",
                padding=False,
                truncation=True,
            )
            uncond_prompt = mx.array(uncond_inputs["input_ids"])
            uncond_length = uncond_prompt.shape[1]

            # Create separate caches for conditional and unconditional
            cond_cache = self._make_mlx_cache()
            uncond_cache = self._make_mlx_cache()

            # Prefill both prompts
            cond_logits = self._mlx_model(prompt, cache=cond_cache)
            uncond_logits = self._mlx_model(uncond_prompt, cache=uncond_cache)
            mx.eval(cond_logits, uncond_logits)

            last_cond = cond_logits[:, -1:, :]
            last_uncond = uncond_logits[:, -1:, :]

            prefill_time = time.time() - prefill_start
            total_prefill_tokens = prompt_length + uncond_length
            prefill_tps = total_prefill_tokens / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX prefill: {total_prefill_tokens} tokens "
                f"(cond={prompt_length}, uncond={uncond_length}) "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s)"
            )
        else:
            cache = self._make_mlx_cache()
            logits_out = self._mlx_model(prompt, cache=cache)
            mx.eval(logits_out)
            last_logits = logits_out[:, -1:, :]

            prefill_time = time.time() - prefill_start
            prefill_tps = prompt_length / prefill_time if prefill_time > 0 else 0
            logger.info(
                f"MLX prefill: {prompt_length} tokens "
                f"in {prefill_time:.2f}s ({prefill_tps:.1f} tok/s)"
            )

        # ---- Autoregressive generation loop ----
        # Track all token IDs for constrained processor context
        all_token_ids = list(input_ids_np[0])
        new_tokens = []
        decode_start = time.time()

        pbar = tqdm(total=max_new_tokens, desc=tqdm_desc, unit="tok")
        for step in range(max_new_tokens):
            # Apply CFG formula in MLX
            if use_cfg:
                step_logits = last_uncond + cfg_scale * (last_cond - last_uncond)
            else:
                step_logits = last_logits

            step_logits = step_logits.reshape(1, -1)  # [1, vocab_size]

            # Bridge to PyTorch for logits processing and sampling
            # This reuses all existing tested code (constrained decoding, top-k/p, etc.)
            # Cast to float32 in MLX first: numpy doesn't support bfloat16
            step_logits_f32 = step_logits.astype(mx.float32)
            np_logits = np.array(step_logits_f32, copy=True)
            t_logits = torch.from_numpy(np_logits)
            t_ids = torch.tensor([all_token_ids], dtype=torch.long)

            # Apply constrained processor
            if constrained_processor is not None:
                t_logits = constrained_processor(t_ids, t_logits)

            # Apply repetition penalty
            if repetition_penalty != 1.0:
                from transformers.generation.logits_process import RepetitionPenaltyLogitsProcessor
                rep_proc = RepetitionPenaltyLogitsProcessor(penalty=repetition_penalty)
                t_logits = rep_proc(t_ids, t_logits)

            # Apply top-k and top-p filtering (reuse existing methods)
            t_logits = self._apply_top_k_filter(t_logits, top_k)
            t_logits = self._apply_top_p_filter(t_logits, top_p)

            # Sample token (reuse existing method)
            t_token = self._sample_tokens(t_logits, temperature)
            token_id = t_token.item()

            new_tokens.append(token_id)
            all_token_ids.append(token_id)
            pbar.update(1)

            # Update constrained processor state
            if constrained_processor is not None:
                constrained_processor.update_state(token_id)

            # Check EOS
            if token_id == eos_token_id:
                break
            if pad_token_id is not None and pad_token_id != eos_token_id and token_id == pad_token_id:
                break

            # Next forward step in MLX (fast)
            next_input = mx.array([[token_id]])
            if use_cfg:
                cond_logits = self._mlx_model(next_input, cache=cond_cache)
                uncond_logits = self._mlx_model(next_input, cache=uncond_cache)
                mx.eval(cond_logits, uncond_logits)
                last_cond = cond_logits[:, -1:, :]
                last_uncond = uncond_logits[:, -1:, :]
            else:
                logits_out = self._mlx_model(next_input, cache=cache)
                mx.eval(logits_out)
                last_logits = logits_out[:, -1:, :]

        pbar.close()

        # Log generation summary
        decode_time = time.time() - decode_start
        num_generated = len(new_tokens)
        decode_tps = num_generated / decode_time if decode_time > 0 else 0
        total_time = prefill_time + decode_time
        logger.info(
            f"MLX generation complete: {num_generated} tokens in {decode_time:.2f}s "
            f"({decode_tps:.1f} tok/s) | prefill {prefill_time:.2f}s + decode {decode_time:.2f}s = {total_time:.2f}s total"
        )

        # Decode new tokens only
        output_text = self.llm_tokenizer.decode(new_tokens, skip_special_tokens=False)
        return output_text

    def _run_mlx(
        self,
        formatted_prompts: Union[str, List[str]],
        temperature: float,
        cfg_scale: float,
        negative_prompt: str,
        top_k: Optional[int],
        top_p: Optional[float],
        repetition_penalty: float,
        use_constrained_decoding: bool = True,
        constrained_decoding_debug: bool = False,
        target_duration: Optional[float] = None,
        user_metadata: Optional[Dict[str, Optional[str]]] = None,
        stop_at_reasoning: bool = False,
        skip_genres: bool = True,
        skip_caption: bool = False,
        skip_language: bool = False,
        generation_phase: str = "cot",
        caption: str = "",
        lyrics: str = "",
        cot_text: str = "",
        seeds: Optional[List[int]] = None,
    ) -> Union[str, List[str]]:
        """
        Unified MLX generation function supporting both single and batch modes.

        For batch mode in codes generation phase, uses optimized batch native path
        that shares prefill across all items (saving ~50% prefill time).
        Falls back to sequential processing if batch native fails.
        """
        import mlx.core as mx

        # Normalize input
        formatted_prompt_list, is_batch = self._normalize_batch_input(formatted_prompts)

        if is_batch:
            batch_size = len(formatted_prompt_list)

            # ---- Try optimized batch native path ----
            # Conditions: codes generation phase + all prompts identical (which they are in batch codes phase)
            all_prompts_identical = len(set(formatted_prompt_list)) == 1
            can_use_batch_native = (
                generation_phase == "codes"
                and all_prompts_identical
                and batch_size > 1
                and hasattr(self, '_mlx_model')
                and self._mlx_model is not None
            )

            if can_use_batch_native:
                try:
                    logger.info(
                        f"MLX batch: using optimized batch native path "
                        f"(batch_size={batch_size}, shared prefill)"
                    )
                    return self._run_mlx_batch_native(
                        formatted_prompt=formatted_prompt_list[0],
                        batch_size=batch_size,
                        temperature=temperature,
                        cfg_scale=cfg_scale,
                        negative_prompt=negative_prompt,
                        top_k=top_k,
                        top_p=top_p,
                        repetition_penalty=repetition_penalty,
                        use_constrained_decoding=use_constrained_decoding,
                        constrained_decoding_debug=constrained_decoding_debug,
                        target_duration=target_duration,
                        caption=caption,
                        lyrics=lyrics,
                        cot_text=cot_text,
                        seeds=seeds,
                    )
                except Exception as e:
                    logger.warning(
                        f"MLX batch native failed ({type(e).__name__}: {e}), "
                        f"falling back to sequential mode"
                    )

            # ---- Fallback: sequential processing ----
            logger.info(f"MLX batch: using sequential mode (batch_size={batch_size})")
            output_texts = []
            for i, formatted_prompt in enumerate(formatted_prompt_list):
                # Set MLX seed for reproducibility
                if seeds and i < len(seeds):
                    mx.random.seed(seeds[i])

                output_text = self._run_mlx_single(
                    formatted_prompt=formatted_prompt,
                    temperature=temperature,
                    cfg_scale=cfg_scale,
                    negative_prompt=negative_prompt,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    use_constrained_decoding=use_constrained_decoding,
                    constrained_decoding_debug=constrained_decoding_debug,
                    target_duration=target_duration,
                    user_metadata=None,
                    stop_at_reasoning=False,
                    skip_genres=True,
                    skip_caption=True,
                    skip_language=True,
                    generation_phase=generation_phase,
                    caption=caption,
                    lyrics=lyrics,
                    cot_text=cot_text,
                )
                output_texts.append(output_text)
            return output_texts

        # Single mode
        formatted_prompt = formatted_prompt_list[0]
        return self._run_mlx_single(
            formatted_prompt=formatted_prompt,
            temperature=temperature,
            cfg_scale=cfg_scale,
            negative_prompt=negative_prompt,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            use_constrained_decoding=use_constrained_decoding,
            constrained_decoding_debug=constrained_decoding_debug,
            target_duration=target_duration,
            user_metadata=user_metadata,
            stop_at_reasoning=stop_at_reasoning,
            skip_genres=skip_genres,
            skip_caption=skip_caption,
            skip_language=skip_language,
            generation_phase=generation_phase,
            caption=caption,
            lyrics=lyrics,
            cot_text=cot_text,
        )

    # =========================================================================
    # End of MLX Backend Methods
    # =========================================================================

    @contextmanager
    def _load_model_context(self):
        """
        Context manager to load a model to GPU and offload it back to CPU after use.
        Only used for PyTorch backend when offload_to_cpu is True.
        """
        if not self.offload_to_cpu:
            yield
            return

        # If using nanovllm or MLX, do not offload (managed differently)
        if self.llm_backend in ("vllm", "mlx"):
            yield
            return

        model = self.llm
        if model is None:
            yield
            return

        # Reentrancy guard: if an outer context already loaded the model
        # to the target device, skip the inner load/offload to avoid
        # redundant CPU↔GPU transfers during batch processing.
        try:
            current_device = next(model.parameters()).device.type
        except StopIteration:
            current_device = None
        target_device = str(self.device).split(":")[0]
        if current_device == target_device:
            yield
            return

        # Load to GPU
        logger.info(f"Loading LLM to {self.device}")
        start_time = time.time()
        if hasattr(model, "to"):
            model.to(self.device).to(self.dtype)
        load_time = time.time() - start_time
        logger.info(f"Loaded LLM to {self.device} in {load_time:.4f}s")

        try:
            yield
        finally:
            # Offload to CPU
            logger.info(f"Offloading LLM to CPU")
            start_time = time.time()
            if hasattr(model, "to"):
                model.to("cpu")
            # Clear accelerator cache after offloading
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch, 'xpu') and torch.xpu.is_available():
                torch.xpu.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available() and hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
            offload_time = time.time() - start_time
            logger.info(f"Offloaded LLM to CPU in {offload_time:.4f}s")

    def get_hf_model_for_scoring(self):
        """
        Get HuggingFace model for perplexity scoring.

        For vllm backend, loads HuggingFace model from disk (weights are cached by transformers).
        For pt backend, returns the existing model.
        For mlx backend, loads HuggingFace model from disk (MLX model can't be used for torch scoring).

        Returns:
            HuggingFace model instance
        """
        if self.llm_backend == "pt":
            # For PyTorch backend, directly return the model
            return self.llm

        elif self.llm_backend == "vllm":
            # For vllm backend, load HuggingFace model from disk
            # Note: transformers caches model weights, so this doesn't duplicate disk I/O
            if self._hf_model_for_scoring is None:
                logger.info("Loading HuggingFace model for scoring (from checkpoint)")

                # Get model path from vllm config
                model_runner = self.llm.model_runner
                model_path = model_runner.config.model

                # Load HuggingFace model from the same checkpoint
                # This will load the original unfused weights
                import time
                start_time = time.time()
                self._hf_model_for_scoring = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    trust_remote_code=True,
                    torch_dtype=self.dtype
                )
                load_time = time.time() - start_time
                logger.info(f"HuggingFace model loaded in {load_time:.2f}s")

                # When offload_to_cpu is enabled, keep the model on CPU to save
                # VRAM.  The caller (_load_scoring_model_context in
                # core/scoring/lm_score.py) will move it to the accelerator only
                # for the duration of the forward pass.
                if self.offload_to_cpu:
                    self._hf_model_for_scoring.eval()
                    logger.info("HuggingFace model for scoring kept on CPU (offload_to_cpu=True)")
                else:
                    device = next(model_runner.model.parameters()).device
                    self._hf_model_for_scoring = self._hf_model_for_scoring.to(device)
                    self._hf_model_for_scoring.eval()
                    logger.info(f"HuggingFace model for scoring ready on {device}")

            return self._hf_model_for_scoring

        elif self.llm_backend == "mlx":
            # For MLX backend, load HuggingFace model from disk for PyTorch scoring
            if self._hf_model_for_scoring is None:
                logger.info("Loading HuggingFace model for scoring (MLX backend, need PyTorch model)")

                # Get model path from stored path
                model_path = getattr(self, '_mlx_model_path', None)
                if model_path is None:
                    raise ValueError("MLX model path not stored. Cannot load HuggingFace model for scoring.")

                import time
                start_time = time.time()
                self._hf_model_for_scoring = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    trust_remote_code=True,
                    torch_dtype=self.dtype
                )
                load_time = time.time() - start_time
                logger.info(f"HuggingFace model loaded in {load_time:.2f}s")

                # When offload_to_cpu is enabled, keep on CPU; the scoring
                # context manager will move it to the accelerator as needed.
                if self.offload_to_cpu:
                    self._hf_model_for_scoring.eval()
                    logger.info("HuggingFace model for scoring kept on CPU (offload_to_cpu=True)")
                else:
                    device = "mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"
                    self._hf_model_for_scoring = self._hf_model_for_scoring.to(device)
                    self._hf_model_for_scoring.eval()
                    logger.info(f"HuggingFace model for scoring ready on {device}")

            return self._hf_model_for_scoring

        else:
            raise ValueError(f"Unknown backend: {self.llm_backend}")
