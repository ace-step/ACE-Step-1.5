"""Mixin for GPU memory management: model loading/offloading and HuggingFace model access."""

import time
from contextlib import contextmanager

import torch
from loguru import logger
from transformers import AutoModelForCausalLM


class MemoryMixin:
    """Mixin providing GPU memory management utilities for LLM inference.

    Expects the consuming class to provide the following attributes:
        - offload_to_cpu (bool)
        - llm_backend (str)
        - llm: the loaded language model
        - device: target accelerator device
        - dtype: model dtype
        - _hf_model_for_scoring: cached HuggingFace model (or None)
    """

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
