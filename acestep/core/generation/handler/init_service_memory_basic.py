"""Memory and device-check helpers for initialization/offload flows."""

import torch
from loguru import logger


class InitServiceMemoryBasicMixin:
    """Memory cache, sync, and tensor-device utility helpers."""

    def _empty_cache(self):
        """Clear accelerator memory cache (CUDA, XPU, or MPS)."""
        device_type = self._device_type()
        if device_type == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
        elif device_type == "xpu" and hasattr(torch, "xpu") and torch.xpu.is_available():
            torch.xpu.empty_cache()
        elif device_type == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()

    def _synchronize(self):
        """Synchronize accelerator operations (CUDA, XPU, or MPS)."""
        device_type = self._device_type()
        if device_type == "cuda" and torch.cuda.is_available():
            torch.cuda.synchronize()
        elif device_type == "xpu" and hasattr(torch, "xpu") and torch.xpu.is_available():
            torch.xpu.synchronize()
        elif device_type == "mps" and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.synchronize()

    def _memory_allocated(self):
        """Get current accelerator memory usage in bytes, or 0 for unsupported backends."""
        device_type = self._device_type()
        if device_type == "cuda" and torch.cuda.is_available():
            return torch.cuda.memory_allocated()
        return 0

    def _max_memory_allocated(self):
        """Get peak accelerator memory usage in bytes, or 0 for unsupported backends."""
        device_type = self._device_type()
        if device_type == "cuda" and torch.cuda.is_available():
            return torch.cuda.max_memory_allocated()
        return 0

    def _is_on_target_device(self, tensor, target_device):
        """Check if tensor is on the target device (handles cuda vs cuda:0 comparison)."""
        if tensor is None:
            return True
        try:
            if isinstance(target_device, torch.device):
                target_type = target_device.type
            else:
                target_type = torch.device(str(target_device)).type
        except Exception:
            target_type = str(target_device).strip().lower().split(":", 1)[0]
            if not target_type:
                logger.warning(
                    "[_is_on_target_device] Malformed target device value: {!r}",
                    target_device,
                )
                return False
        return tensor.device.type == target_type

    @staticmethod
    def _get_affine_quantized_tensor_class():
        """Return the AffineQuantizedTensor class from torchao, or None if unavailable."""
        try:
            from torchao.dtypes.affine_quantized_tensor import AffineQuantizedTensor
            return AffineQuantizedTensor
        except ImportError:
            pass
        try:
            from torchao.quantization.affine_quantized import AffineQuantizedTensor
            return AffineQuantizedTensor
        except ImportError:
            pass
        return None

    def _is_quantized_tensor(self, t):
        """True if ``t`` is a torchao AffineQuantizedTensor."""
        if t is None:
            return False
        cls = self._get_affine_quantized_tensor_class()
        if cls is None:
            return False
        return isinstance(t, cls)

    def _has_quantized_params(self, module):
        """True if module (or any submodule) has an AffineQuantizedTensor parameter."""
        cls = self._get_affine_quantized_tensor_class()
        if cls is None:
            return False
        for _, param in module.named_parameters():
            if param is not None and isinstance(param, cls):
                return True
        return False

    def _ensure_silence_latent_on_device(self):
        """Ensure ``silence_latent`` is on ``self.device``."""
        if hasattr(self, "silence_latent") and self.silence_latent is not None:
            if not self._is_on_target_device(self.silence_latent, self.device):
                self.silence_latent = self.silence_latent.to(self.device).to(self.dtype)
