"""Memory and VRAM helper methods for handler decomposition."""

import os
from typing import Optional

import torch
from loguru import logger

from acestep.gpu_config import (
    cuda_supports_bfloat16,
    get_effective_free_vram_gb,
    get_global_gpu_config,
    is_rocm_available,
)


def _is_cuda_device(device: object) -> bool:
    """Return whether a device identifier refers to any CUDA device."""
    if device is None:
        return False
    try:
        return torch.device(str(device)).type == "cuda"
    except (TypeError, RuntimeError, ValueError):
        return isinstance(device, str) and device.split(":", 1)[0] == "cuda"

def _cuda_device_index(device: object) -> int:
    """Return the CUDA device index implied by a device identifier."""
    if isinstance(device, torch.device):
        return 0 if device.index is None else device.index
    try:
        parsed = torch.device(str(device))
        if parsed.type == "cuda":
            return 0 if parsed.index is None else parsed.index
    except (TypeError, RuntimeError, ValueError):
        pass
    if isinstance(device, str) and device.startswith("cuda:"):
        try:
            return int(device.split(":", 1)[1])
        except ValueError:
            return 0
    return 0


class MemoryUtilsMixin:
    """Mixin containing memory sizing and VRAM guard helpers.

    Depends on host members:
    - Attribute: ``device``.
    """

    def is_silence(self, audio: torch.Tensor) -> bool:
        """Return True when audio is effectively silent."""
        return bool(torch.all(audio.abs() < 1e-6))

    def _get_system_memory_gb(self) -> Optional[float]:
        """Return total system RAM in GB when available."""
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            page_count = os.sysconf("SC_PHYS_PAGES")
            if page_size and page_count:
                return (page_size * page_count) / (1024**3)
        except (ValueError, OSError, AttributeError):
            return None
        return None

    def _get_effective_mps_memory_gb(self) -> Optional[float]:
        """Best-effort MPS memory estimate (recommended max or system RAM)."""
        if hasattr(torch, "mps") and hasattr(torch.mps, "recommended_max_memory"):
            try:
                return torch.mps.recommended_max_memory() / (1024**3)
            except Exception:
                pass
        system_gb = self._get_system_memory_gb()
        if system_gb is None:
            return None
        return system_gb * 0.75

    VAE_DECODE_MAX_CHUNK_SIZE = 512

    def _get_auto_decode_chunk_size(self) -> int:
        """Choose a conservative VAE decode chunk size based on available memory."""
        override = os.environ.get("ACESTEP_VAE_DECODE_CHUNK_SIZE")
        if override:
            try:
                value = int(override)
                if value > 0:
                    return value
            except ValueError:
                pass

        max_chunk = self.VAE_DECODE_MAX_CHUNK_SIZE

        if self.device == "mps":
            mem_gb = self._get_effective_mps_memory_gb()
            if mem_gb is not None:
                if mem_gb >= 48:
                    return min(1536, max_chunk)
                if mem_gb >= 24:
                    return min(1024, max_chunk)
            return min(512, max_chunk)

        if _is_cuda_device(self.device):
            try:
                free_gb = get_effective_free_vram_gb(_cuda_device_index(self.device))
            except Exception:
                free_gb = 0
            logger.debug(f"[_get_auto_decode_chunk_size] Effective free VRAM: {free_gb:.2f} GB")
            if free_gb >= 24.0:
                return min(512, max_chunk)
            if free_gb >= 16.0:
                return min(384, max_chunk)
            if free_gb >= 12.0:
                return min(256, max_chunk)
            return min(128, max_chunk)
        return min(256, max_chunk)

    def _should_offload_wav_to_cpu(self) -> bool:
        """Decide whether to offload decoded wavs to CPU for memory safety."""
        override = os.environ.get("ACESTEP_MPS_DECODE_OFFLOAD")
        if override:
            return override.lower() in ("1", "true", "yes")
        if self.device == "mps":
            mem_gb = self._get_effective_mps_memory_gb()
            if mem_gb is not None and mem_gb >= 32:
                return False
            return True
        if _is_cuda_device(self.device):
            try:
                free_gb = get_effective_free_vram_gb(_cuda_device_index(self.device))
                logger.debug(f"[_should_offload_wav_to_cpu] Effective free VRAM: {free_gb:.2f} GB")
                if free_gb >= 24.0:
                    return False
            except Exception:
                pass
        return True

    def _vram_guard_reduce_batch(
        self,
        batch_size: int,
        audio_duration: Optional[float] = None,
        use_lm: bool = False,
    ) -> int:
        """Auto-reduce batch_size when free VRAM is too tight."""
        if batch_size <= 1:
            return batch_size

        device = self.device
        if device == "cpu" or device == "mps":
            return batch_size

        if self.offload_to_cpu:
            gpu_config = get_global_gpu_config()
            if gpu_config is not None:
                tier_max = gpu_config.max_batch_size_with_lm
                if batch_size <= tier_max:
                    logger.debug(
                        f"[VRAM guard] offload_to_cpu=True, batch_size={batch_size} <= "
                        f"tier limit {tier_max} - skipping dynamic VRAM check"
                    )
                    return batch_size

        try:
            free_gb = get_effective_free_vram_gb(_cuda_device_index(device))
        except Exception:
            return batch_size

        duration_sec = float(audio_duration) if audio_duration and float(audio_duration) > 0 else 60.0
        per_sample_gb = 0.5 + max(0.0, 0.15 * (duration_sec - 60.0) / 60.0)
        if hasattr(self, "model") and self.model is not None:
            model_name = getattr(self, "config_path", "") or ""
            if "base" in model_name.lower():
                per_sample_gb *= 2.0

        safety_margin_gb = 1.5
        available_for_batch = free_gb - safety_margin_gb
        if available_for_batch <= 0:
            logger.warning(
                f"[VRAM guard] Only {free_gb:.1f} GB free - reducing batch_size to 1"
            )
            return 1

        max_safe_batch = max(1, int(available_for_batch / per_sample_gb))
        if max_safe_batch < batch_size:
            logger.warning(
                f"[VRAM guard] Free VRAM {free_gb:.1f} GB can safely fit ~{max_safe_batch} samples "
                f"(requested {batch_size}). Reducing batch_size to {max_safe_batch}."
            )
            return max_safe_batch
        return batch_size

    def _get_vae_dtype(self, device: Optional[str] = None) -> torch.dtype:
        """Get VAE dtype based on target device and GPU tier."""
        target_device = device or self.device
        if _is_cuda_device(target_device):
            if is_rocm_available():
                # On ROCm, defer to self.dtype which is already set to a safe
                # value (float32 by default, or ACESTEP_ROCM_DTYPE override).
                return getattr(self, "dtype", torch.float32)
            if cuda_supports_bfloat16(_cuda_device_index(target_device)):
                return torch.bfloat16
            return torch.float16
        if target_device == "xpu":
            return torch.bfloat16
        if target_device == "mps":
            return torch.float16
        if target_device == "cpu":
            return torch.float32
        return self.dtype
