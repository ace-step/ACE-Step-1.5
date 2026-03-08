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

import yaml
import torch
from loguru import logger
from tqdm import tqdm
from transformers import AutoTokenizer
from transformers.generation.streamers import BaseStreamer
from transformers.generation.logits_process import (
    LogitsProcessorList,
    RepetitionPenaltyLogitsProcessor,
)
from acestep.constrained_logits_processor import MetadataConstrainedLogitsProcessor
from acestep.constants import DEFAULT_LM_INSTRUCTION, DEFAULT_LM_UNDERSTAND_INSTRUCTION, DEFAULT_LM_INSPIRED_INSTRUCTION, DEFAULT_LM_REWRITE_INSTRUCTION, DURATION_MIN, DURATION_MAX
from acestep.gpu_config import get_lm_gpu_memory_ratio, get_gpu_memory_gb, get_lm_model_size, get_global_gpu_config, resolve_device
from acestep.lm_output_parser import parse_lm_output as _parse_lm_output
from acestep.lm_prompts import (
    build_formatted_prompt as _build_formatted_prompt,
    build_formatted_prompt_for_format as _build_formatted_prompt_for_format,
    build_formatted_prompt_for_inspiration as _build_formatted_prompt_for_inspiration,
    build_formatted_prompt_for_understanding as _build_formatted_prompt_for_understanding,
    build_formatted_prompt_with_cot as _build_formatted_prompt_with_cot,
    has_meaningful_negative_prompt as _has_meaningful_negative_prompt,
)

# Re-export constants from the canonical location for backward compatibility.
from acestep.llm.constants import (  # noqa: F401
    BYTES_PER_GB,
    CODES_PER_SECOND,
    CODES_PHASE_TOKEN_BUFFER,
    COT_PHASE_TOKEN_BUFFER,
    DEFAULT_MAX_MODEL_LEN,
    LOW_GPU_MAX_MODEL_LEN,
    MODEL_LEN_HEADROOM,
    VRAM_SAFE_FREE_GB,
)

# Backend mixins (imported here so LLMHandler can inherit from them).
from acestep.llm.mlx_backend import MlxBackendMixin
from acestep.llm.memory import MemoryMixin
from acestep.llm.pt_backend import PytorchBackendMixin
from acestep.llm.vllm_backend import VllmBackendMixin


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


class LLMHandler(
    VllmBackendMixin,
    PytorchBackendMixin,
    MlxBackendMixin,
    MemoryMixin,
):
    """5Hz LM Handler for audio code generation.

    Backend-specific methods are provided by mixins:
    - VllmBackendMixin  (vllm_backend.py)
    - PytorchBackendMixin  (pt_backend.py)
    - MlxBackendMixin  (mlx_backend.py)
    - MemoryMixin  (memory.py)
    """

    STOP_REASONING_TAG = "</think>"

    # HuggingFace Space environment detection
    IS_HUGGINGFACE_SPACE = os.environ.get("SPACE_ID") is not None

    def __init__(self, persistent_storage_path: Optional[str] = None):
        """Initialize LLMHandler with default values"""
        self.llm = None
        self.llm_tokenizer = None
        self.llm_initialized = False
        self.llm_backend = None
        self.max_model_len = DEFAULT_MAX_MODEL_LEN
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
            total_gpu = total_gpu_mem_bytes / BYTES_PER_GB

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
            reserved_gpu = reserved_mem_bytes / BYTES_PER_GB
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
            target_codes = int(effective_duration * CODES_PER_SECOND)
            if generation_phase == "codes":
                # Codes phase: CoT already in prompt, only audio codes generated.
                # Constrained decoder forces EOS at target_codes, so small buffer suffices.
                max_new_tokens = target_codes + CODES_PHASE_TOKEN_BUFFER
            else:
                # CoT phase or mixed: add larger buffer for metadata overhead.
                max_new_tokens = target_codes + COT_PHASE_TOKEN_BUFFER
        else:
            if fallback_max is not None:
                max_new_tokens = fallback_max
            else:
                max_new_tokens = getattr(self, "max_model_len", DEFAULT_MAX_MODEL_LEN) - MODEL_LEN_HEADROOM

        # Cap at model's max length
        if hasattr(self, "max_model_len"):
            max_new_tokens = min(max_new_tokens, self.max_model_len - MODEL_LEN_HEADROOM)

        return max_new_tokens

    def _has_meaningful_negative_prompt(self, negative_prompt: str) -> bool:
        """Check if negative prompt is meaningful (not default/empty)"""
        return _has_meaningful_negative_prompt(negative_prompt)

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
            device = resolve_device(device)
            self.device = device
            self.offload_to_cpu = offload_to_cpu
            self.dtype = self._resolve_dtype(device, dtype)

            full_lm_model_path = self._resolve_model_path(checkpoint_dir, lm_model_path)
            if not os.path.exists(full_lm_model_path):
                return f"❌ 5Hz LM model not found at {full_lm_model_path}", False

            # Proactive CUDA cleanup before LM load
            if device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            self._load_tokenizer(full_lm_model_path)
            self._init_constrained_processor()

            return self._initialize_backend(backend, device, full_lm_model_path)

        except Exception as e:
            return f"❌ Error initializing 5Hz LM: {str(e)}\n\nTraceback:\n{traceback.format_exc()}", False

    # ----- initialize() helpers -----

    def _resolve_dtype(self, device: str, dtype: Optional[torch.dtype]) -> torch.dtype:
        """Pick the best dtype for the LM on *device*."""
        if dtype is None:
            return torch.bfloat16 if device in ("cuda", "xpu") else torch.float32
        # Keep LM in float32 on MPS for stability.
        if device == "mps" and dtype != torch.float32:
            logger.warning(
                f"[initialize] Overriding requested dtype {dtype} to float32 for LM on MPS."
            )
            return torch.float32
        return dtype

    @staticmethod
    def _resolve_model_path(checkpoint_dir: str, lm_model_path: Optional[str]) -> str:
        if lm_model_path is None:
            lm_model_path = "acestep-5Hz-lm-1.7B"
            logger.info(f"[initialize] lm_model_path is None, using default: {lm_model_path}")
        return os.path.join(checkpoint_dir, lm_model_path)

    def _load_tokenizer(self, full_lm_model_path: str) -> None:
        logger.info("loading 5Hz LM tokenizer... it may take 80~90s")
        start_time = time.time()
        self.llm_tokenizer = AutoTokenizer.from_pretrained(full_lm_model_path, use_fast=True)
        logger.info(f"5Hz LM tokenizer loaded successfully in {time.time() - start_time:.2f} seconds")

    def _init_constrained_processor(self) -> None:
        logger.info("Initializing constrained decoding processor...")
        processor_start = time.time()
        gpu_config = get_global_gpu_config()
        max_duration_for_constraint = gpu_config.max_duration_with_lm
        logger.info(
            f"Setting constrained decoding max_duration to {max_duration_for_constraint}s "
            f"based on GPU config (tier: {gpu_config.tier})"
        )
        self.constrained_processor = MetadataConstrainedLogitsProcessor(
            tokenizer=self.llm_tokenizer,
            enabled=True,
            debug=False,
            max_duration=max_duration_for_constraint,
        )
        logger.info(f"Constrained processor initialized in {time.time() - processor_start:.2f} seconds")

    @staticmethod
    def _should_enforce_eager(device: str) -> bool:
        """Check if CUDA graph capture should be disabled (ROCm / Jetson)."""
        is_rocm = hasattr(torch.version, "hip") and torch.version.hip is not None
        is_jetson = False
        if device == "cuda" and torch.cuda.is_available():
            try:
                dev_name = torch.cuda.get_device_name(0).lower()
                is_jetson = any(k in dev_name for k in ("orin", "xavier", "tegra"))
                if is_jetson:
                    logger.info(f"Jetson GPU detected ({dev_name}): disabling CUDA graph capture")
            except Exception:
                pass
        return bool(is_rocm or is_jetson)

    def _initialize_backend(
        self, backend: str, device: str, model_path: str
    ) -> Tuple[str, bool]:
        """Dispatch to the appropriate backend (MLX → vLLM → PyTorch)."""
        # MLX path (Apple Silicon)
        if backend == "mlx" or (backend == "vllm" and device == "mps"):
            result = self._try_mlx_backend(backend, device, model_path)
            if result is not None:
                return result
            # If MLX didn't conclusively handle it, fall through to vllm/pt.

        # vLLM requires CUDA
        if backend == "vllm" and device != "cuda":
            logger.info(f"[initialize] vllm requires CUDA, using PyTorch for device={device}.")
            backend = "pt"

        if backend == "vllm":
            return self._try_vllm_backend(device, model_path)

        if backend != "mlx":
            return self._try_pytorch_backend(model_path, device)

        # Should not be reached; MLX path handles its own return.
        return "❌ No suitable backend found.", False

    def _try_mlx_backend(
        self, backend: str, device: str, model_path: str
    ) -> Optional[Tuple[str, bool]]:
        """Attempt MLX; return result tuple or *None* to fall through."""
        if self._is_mlx_available():
            logger.info("Attempting MLX backend for Apple Silicon acceleration...")
            mlx_success, mlx_status = self._load_mlx_model(model_path)
            if mlx_success:
                return mlx_status, True
            logger.warning(f"MLX backend failed: {mlx_status}")
            if backend == "mlx":
                logger.warning("MLX explicitly requested but failed, falling back to PyTorch")
                return self._try_pytorch_backend(model_path, device, label="PyTorch fallback from MLX")
            return None  # fall through to vllm/pt
        if backend == "mlx":
            logger.warning("MLX not available (requires Apple Silicon + mlx-lm package)")
            return self._try_pytorch_backend(model_path, device, label="PyTorch fallback, MLX not available")
        return None

    def _try_vllm_backend(self, device: str, model_path: str) -> Tuple[str, bool]:
        """Try vLLM, falling back to PyTorch on failure."""
        _warn_if_prerelease_python()

        free_gb = self._get_free_gpu_gb(device)
        if device == "cuda" and free_gb < VRAM_SAFE_FREE_GB:
            total_gb = get_gpu_memory_gb()
            logger.warning(
                f"vLLM disabled: insufficient free VRAM "
                f"(total={total_gb:.2f}GB, free={free_gb:.2f}GB, need>={VRAM_SAFE_FREE_GB}GB) "
                f"— falling back to PyTorch"
            )
            return self._try_pytorch_backend(model_path, device, label="PyTorch fallback")

        enforce_eager = self._should_enforce_eager(device)
        status_msg = self._initialize_5hz_lm_vllm(model_path, enforce_eager=enforce_eager)
        logger.info(f"5Hz LM status message: {status_msg}")

        if not status_msg.startswith("❌"):
            return status_msg, True

        # vLLM failed -- attempt fallbacks.
        if not self.llm_initialized:
            if device == "mps" and self._is_mlx_available():
                logger.warning("vllm failed on MPS, trying MLX backend...")
                mlx_ok, mlx_status = self._load_mlx_model(model_path)
                if mlx_ok:
                    return mlx_status, True
                logger.warning(f"MLX also failed: {mlx_status}, falling back to PyTorch")
            logger.warning("Falling back to PyTorch backend")
            return self._try_pytorch_backend(model_path, device, label="PyTorch fallback")

        return status_msg, True

    def _try_pytorch_backend(
        self, model_path: str, device: str, label: str = "PyTorch"
    ) -> Tuple[str, bool]:
        """Load via PyTorch, returning a standard result tuple."""
        success, status_msg = self._load_pytorch_model(model_path, device)
        if not success:
            return status_msg, False
        return (
            f"✅ 5Hz LM initialized successfully ({label})\n"
            f"Model: {model_path}\nBackend: PyTorch"
        ), True

    @staticmethod
    def _get_free_gpu_gb(device: str) -> float:
        """Return free GPU memory in GB (0.0 if unavailable)."""
        if device != "cuda" or not torch.cuda.is_available():
            return 0.0
        try:
            if hasattr(torch.cuda, "mem_get_info"):
                free_bytes, _ = torch.cuda.mem_get_info()
                return free_bytes / BYTES_PER_GB
            total_bytes = torch.cuda.get_device_properties(0).total_memory
            return (total_bytes - torch.cuda.memory_reserved(0)) / BYTES_PER_GB
        except Exception:
            return 0.0

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
        """Build the chat-formatted prompt for 5Hz LM.

        Delegates to :func:`acestep.lm_prompts.build_formatted_prompt`.
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")
        return _build_formatted_prompt(
            self.llm_tokenizer, caption, lyrics,
            is_negative_prompt=is_negative_prompt,
            generation_phase=generation_phase,
            negative_prompt=negative_prompt,
        )

    def build_formatted_prompt_with_cot(self, caption: str, lyrics: str, cot_text: str, is_negative_prompt: bool = False, negative_prompt: str = "NO USER INPUT") -> str:
        """Build codes-generation prompt with pre-generated CoT.

        Delegates to :func:`acestep.lm_prompts.build_formatted_prompt_with_cot`.
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")
        return _build_formatted_prompt_with_cot(
            self.llm_tokenizer, caption, lyrics, cot_text,
            is_negative_prompt=is_negative_prompt,
            negative_prompt=negative_prompt,
        )

    def build_formatted_prompt_for_understanding(
        self,
        audio_codes: str,
        is_negative_prompt: bool = False,
        negative_prompt: str = "NO USER INPUT",
    ) -> str:
        """Build the prompt for audio understanding (codes -> metadata).

        Delegates to :func:`acestep.lm_prompts.build_formatted_prompt_for_understanding`.
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")
        return _build_formatted_prompt_for_understanding(
            self.llm_tokenizer, audio_codes,
            is_negative_prompt=is_negative_prompt,
            negative_prompt=negative_prompt,
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
        negative_prompt: str = "NO USER INPUT",
    ) -> str:
        """Build the prompt for inspiration/simple mode.

        Delegates to :func:`acestep.lm_prompts.build_formatted_prompt_for_inspiration`.
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")
        return _build_formatted_prompt_for_inspiration(
            self.llm_tokenizer, query,
            instrumental=instrumental,
            is_negative_prompt=is_negative_prompt,
            negative_prompt=negative_prompt,
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
        negative_prompt: str = "NO USER INPUT",
    ) -> str:
        """Build the prompt for format/rewrite mode.

        Delegates to :func:`acestep.lm_prompts.build_formatted_prompt_for_format`.
        """
        if self.llm_tokenizer is None:
            raise ValueError("LLM tokenizer is not initialized. Call initialize() first.")
        return _build_formatted_prompt_for_format(
            self.llm_tokenizer, caption, lyrics,
            is_negative_prompt=is_negative_prompt,
            negative_prompt=negative_prompt,
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
        """Parse LM output to extract metadata and audio codes.

        Delegates to :func:`acestep.lm_output_parser.parse_lm_output`.
        """
        return _parse_lm_output(
            output_text,
            postprocess_caption=MetadataConstrainedLogitsProcessor.postprocess_caption,
        )

