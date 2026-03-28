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
                        self._release_system_memory()
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

        rss_before = self._get_rss_mb()
        logger.info(f"[_load_model_context] Loading {model_name} to {self.device} (RSS: {rss_before:.0f} MB)")
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

        # Free old CPU tensor storage after moving to GPU (not counted in load_time)
        self._release_system_memory()
        rss_after = self._get_rss_mb()
        logger.info(
            f"[_load_model_context] Loaded {model_name} to {self.device} in {load_time:.4f}s "
            f"(RSS: {rss_before:.0f} -> {rss_after:.0f} MB, delta: {rss_after - rss_before:+.0f} MB)"
        )

        try:
            yield
        finally:
            rss_before = self._get_rss_mb()
            logger.info(
                f"[_load_model_context] Offloading {model_name} to CPU (RSS: {rss_before:.0f} MB)"
            )
            start_time = time.time()
            if model_name == "vae":
                self._recursive_to_device(model, "cpu", self._get_vae_dtype("cpu"))
            else:
                self._recursive_to_device(model, "cpu")

            offload_time = time.time() - start_time
            self.current_offload_cost += offload_time

            # Aggressively reclaim memory: GPU cache + Python GC + OS heap trim
            # (not counted in offload_time to keep timing accurate)
            self._release_system_memory()
            rss_after = self._get_rss_mb()
            logger.info(
                f"[_load_model_context] Offloaded {model_name} to CPU in {offload_time:.4f}s "
                f"(RSS: {rss_before:.0f} -> {rss_after:.0f} MB, delta: {rss_after - rss_before:+.0f} MB)"
            )
