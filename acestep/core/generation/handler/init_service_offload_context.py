"""Context manager for temporary model loading/offloading."""

import time
from contextlib import contextmanager

from loguru import logger


class InitServiceOffloadContextMixin:
    """Context-managed model load/offload behavior for CPU offload mode."""

    @contextmanager
    def _load_model_context(self, model_name: str):
        """Load a model to device for the context and offload back to CPU on exit."""
        if not self.offload_to_cpu:
            yield
            return

        if model_name == "model" and not self.offload_dit_to_cpu:
            model = getattr(self, model_name, None)
            if model is not None:
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
            logger.info(f"[_load_model_context] Offloading {model_name} to CPU")
            start_time = time.time()
            if model_name == "vae":
                self._recursive_to_device(model, "cpu", self._get_vae_dtype("cpu"))
            else:
                self._recursive_to_device(model, "cpu")

            self._empty_cache()
            offload_time = time.time() - start_time
            self.current_offload_cost += offload_time
            logger.info(f"[_load_model_context] Offloaded {model_name} to CPU in {offload_time:.4f}s")
