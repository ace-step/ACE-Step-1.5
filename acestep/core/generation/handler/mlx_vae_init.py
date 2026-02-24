"""MLX VAE initialization helpers for Apple Silicon acceleration."""

import os
from typing import Any

from loguru import logger


class MlxVaeInitMixin:
    """Initialize native MLX VAE state and compiled decode/encode callables."""

    def _init_mlx_vae(self) -> bool:
        """Initialize native MLX VAE runtime state from ``self.vae``.

        The ``_init_mlx_vae`` path converts the loaded PyTorch VAE in
        ``self.vae`` to an MLX implementation, optionally applies float16
        conversion based on ``ACESTEP_MLX_VAE_FP16``, and prepares decode/encode
        callables.

        Side effects:
            Mutates ``self.mlx_vae`` and ``self.use_mlx_vae`` and updates
            ``self._mlx_compiled_decode``, ``self._mlx_compiled_encode_sample``,
            and ``self._mlx_vae_dtype``.

        Returns:
            bool: ``True`` when MLX VAE is initialized successfully, else ``False``.

        Error behavior:
            Returns ``False`` when MLX is unavailable or when any conversion/
            initialization step raises an exception. Failures are logged as
            non-fatal.
        """
        try:
            from acestep.models.mlx import mlx_available

            if not mlx_available():
                logger.info("[MLX-VAE] MLX not available on this platform; skipping.")
                return False

            import mlx.core as mx
            from mlx.utils import tree_map
            from acestep.models.mlx.vae_model import MLXAutoEncoderOobleck
            from acestep.models.mlx.vae_convert import convert_and_load

            mlx_vae = MLXAutoEncoderOobleck.from_pytorch_config(self.vae)
            convert_and_load(self.vae, mlx_vae)

            use_fp16 = os.environ.get("ACESTEP_MLX_VAE_FP16", "0").lower() in (
                "1",
                "true",
                "yes",
            )
            vae_dtype = mx.float16 if use_fp16 else mx.float32

            if use_fp16:
                try:

                    def _to_fp16(value: Any):
                        """Cast floating MLX arrays to float16 while preserving other values."""
                        if isinstance(value, mx.array) and mx.issubdtype(value.dtype, mx.floating):
                            return value.astype(mx.float16)
                        return value

                    mlx_vae.update(tree_map(_to_fp16, mlx_vae.parameters()))
                    mx.eval(mlx_vae.parameters())
                    logger.info("[MLX-VAE] Model weights converted to float16.")
                except Exception as exc:
                    logger.warning(f"[MLX-VAE] Float16 conversion failed ({exc}); using float32.")
                    vae_dtype = mx.float32

            compiled = True
            try:
                self._mlx_compiled_decode = mx.compile(mlx_vae.decode)
                self._mlx_compiled_encode_sample = mx.compile(mlx_vae.encode_and_sample)
                logger.info("[MLX-VAE] Decode/encode compiled with mx.compile().")
            except Exception as exc:
                compiled = False
                logger.warning(f"[MLX-VAE] mx.compile() failed ({exc}); using uncompiled path.")
                self._mlx_compiled_decode = mlx_vae.decode
                self._mlx_compiled_encode_sample = mlx_vae.encode_and_sample

            self.mlx_vae = mlx_vae
            self.use_mlx_vae = True
            self._mlx_vae_dtype = vae_dtype
            logger.info(
                f"[MLX-VAE] Native MLX VAE initialized (dtype={vae_dtype}, compiled={compiled})."
            )
            return True
        except Exception as exc:
            logger.warning(f"[MLX-VAE] Failed to initialize MLX VAE (non-fatal): {exc}")
            self.mlx_vae = None
            self.use_mlx_vae = False
            self._mlx_compiled_decode = None
            self._mlx_compiled_encode_sample = None
            self._mlx_vae_dtype = None
            return False
