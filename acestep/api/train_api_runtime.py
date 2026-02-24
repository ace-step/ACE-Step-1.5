"""Runtime helpers for training API temporary component management."""

from __future__ import annotations

from typing import Any, Optional

from loguru import logger

from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler


def unwrap_module(module: Any) -> Any:
    """Best-effort unwrap for common wrapper attributes used by training runtimes."""

    current = module
    for _ in range(4):
        if hasattr(current, "_forward_module"):
            current = getattr(current, "_forward_module")
            continue
        if hasattr(current, "module"):
            current = getattr(current, "module")
            continue
        break
    return current


class RuntimeComponentManager:
    """Temporarily offload runtime components and restore them after a task."""

    def __init__(self, handler: AceStepHandler, llm: Optional[LLMHandler], app_state: Any) -> None:
        """Capture runtime handles used by offload/restore operations."""

        self.handler = handler
        self.llm = llm
        self.app_state = app_state

        self.decoder_moved = False
        self.llm_unloaded = False

        self._decoder_prev_device: Optional[str] = None
        self._decoder_prev_dtype: Any = None
        self._vae_prev_device: Optional[str] = None
        self._text_encoder_prev_device: Optional[str] = None
        self._model_encoder_prev_device: Optional[str] = None

    @staticmethod
    def _device_of(module: Any) -> Optional[str]:
        """Return module device string when available."""

        if module is None:
            return None
        try:
            first = next(module.parameters())
            return str(first.device)
        except Exception:
            return None

    @staticmethod
    def _move_module(module: Any, device: str, dtype: Any = None) -> None:
        """Move a module to a target device/dtype when possible."""

        if module is None:
            return
        try:
            if dtype is None:
                module.to(device)
            else:
                module.to(device).to(dtype)
        except Exception:
            module.to(device)

    def move_decoder_to(self, device: str) -> None:
        """Move decoder to target device for training."""

        decoder = getattr(getattr(self.handler, "model", None), "decoder", None)
        if decoder is None:
            return
        current = self._device_of(decoder)
        if current is not None:
            self._decoder_prev_device = current
            self._decoder_prev_dtype = getattr(self.handler, "dtype", None)
        self._move_module(decoder, device, self._decoder_prev_dtype)

    def offload_decoder_to_cpu(self) -> None:
        """Move decoder to CPU to free VRAM for non-decoder workloads."""

        decoder = getattr(getattr(self.handler, "model", None), "decoder", None)
        if decoder is None:
            return
        current = self._device_of(decoder)
        if current and not current.startswith("cpu"):
            self._decoder_prev_device = current
            self._decoder_prev_dtype = getattr(self.handler, "dtype", None)
            self._move_module(decoder, "cpu")
            self.decoder_moved = True

    def offload_vae_to_cpu(self) -> None:
        """Move VAE to CPU."""

        vae = getattr(self.handler, "vae", None)
        self._vae_prev_device = self._device_of(vae)
        if self._vae_prev_device and not self._vae_prev_device.startswith("cpu"):
            self._move_module(vae, "cpu")

    def offload_text_encoder_to_cpu(self) -> None:
        """Move text encoder to CPU."""

        text_encoder = getattr(self.handler, "text_encoder", None)
        self._text_encoder_prev_device = self._device_of(text_encoder)
        if self._text_encoder_prev_device and not self._text_encoder_prev_device.startswith("cpu"):
            self._move_module(text_encoder, "cpu")

    def offload_model_encoder_to_cpu(self) -> None:
        """Move DiT encoder branch to CPU when present."""

        model = getattr(self.handler, "model", None)
        encoder = getattr(model, "encoder", None)
        self._model_encoder_prev_device = self._device_of(encoder)
        if self._model_encoder_prev_device and not self._model_encoder_prev_device.startswith("cpu"):
            self._move_module(encoder, "cpu")

    def unload_llm(self) -> None:
        """Unload LLM to release VRAM and mark state flags."""

        if self.llm is None or not getattr(self.llm, "llm_initialized", False):
            return
        try:
            self.llm.unload()
            self.llm_unloaded = True
            self.app_state._llm_initialized = False
            self.app_state._llm_init_error = None
        except Exception:
            logger.exception("Failed to unload LLM for temporary offload")

    def restore(self) -> None:
        """Restore previously offloaded components back to their original state."""

        try:
            decoder = getattr(getattr(self.handler, "model", None), "decoder", None)
            if decoder is not None and self._decoder_prev_device:
                self._move_module(decoder, self._decoder_prev_device, self._decoder_prev_dtype)
                try:
                    decoder.eval()
                except Exception:
                    pass
        except Exception:
            logger.exception("Failed to restore decoder")

        for module, prev in (
            (getattr(self.handler, "vae", None), self._vae_prev_device),
            (getattr(self.handler, "text_encoder", None), self._text_encoder_prev_device),
            (getattr(getattr(self.handler, "model", None), "encoder", None), self._model_encoder_prev_device),
        ):
            if module is None or not prev:
                continue
            try:
                self._move_module(module, prev)
            except Exception:
                logger.exception("Failed to restore module from temporary offload")

        if self.llm_unloaded and self.llm is not None:
            params = getattr(self.llm, "last_init_params", None)
            if isinstance(params, dict) and params:
                try:
                    status, ok = self.llm.initialize(**params)
                    self.app_state._llm_initialized = bool(ok)
                    self.app_state._llm_init_error = None if ok else status
                except Exception as exc:
                    self.app_state._llm_initialized = False
                    self.app_state._llm_init_error = str(exc)

        self.decoder_moved = False
        self.llm_unloaded = False
