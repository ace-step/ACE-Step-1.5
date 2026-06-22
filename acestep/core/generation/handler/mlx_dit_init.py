"""MLX DiT initialization helpers for Apple Silicon acceleration."""

import os

from loguru import logger


def _mlx_dit_bf16_requested() -> bool:
    """Return True when ``ACESTEP_MLX_DIT_BF16`` opts into bf16 DiT compute."""
    return os.environ.get("ACESTEP_MLX_DIT_BF16", "0").lower() in ("1", "true", "yes")


class MlxDitInitMixin:
    """Initialize native MLX DiT decoder state used by generation runtime."""

    def _init_mlx_dit(self, compile_model: bool = False) -> bool:
        """Initialize the MLX DiT decoder when platform support is available.

        Args:
            compile_model: Whether MLX diffusion should use ``mx.compile``.

        Returns:
            bool: ``True`` when MLX DiT is initialized successfully, else ``False``.
        """
        try:
            from acestep.models.mlx import mlx_available

            if not mlx_available():
                logger.info("[MLX-DiT] MLX not available on this platform; skipping.")
                return False

            from acestep.models.mlx.dit_model import MLXDiTDecoder
            from acestep.models.mlx.dit_convert import convert_and_load

            mlx_decoder = MLXDiTDecoder.from_config(self.config)
            convert_and_load(self.model, mlx_decoder)
            bf16_applied = self._maybe_apply_mlx_dit_bf16(mlx_decoder)
            mlx_decoder.materialize_static_buffers()
            self.mlx_decoder = mlx_decoder
            self.use_mlx_dit = True
            self.mlx_dit_compiled = compile_model
            self.mlx_dit_bf16 = bf16_applied
            logger.info(
                "[MLX-DiT] Native MLX DiT decoder initialized successfully "
                f"(mx.compile={compile_model}, dtype={'bfloat16' if bf16_applied else 'float32'})."
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[MLX-DiT] Failed to initialize MLX decoder (non-fatal): {exc}")
            self.mlx_decoder = None
            self.use_mlx_dit = False
            self.mlx_dit_compiled = False
            self.mlx_dit_bf16 = False
            return False

    @staticmethod
    def _maybe_apply_mlx_dit_bf16(mlx_decoder) -> bool:
        """Optionally cast the MLX DiT to bfloat16 for faster Apple-Silicon compute.

        Controlled by the ``ACESTEP_MLX_DIT_BF16`` environment variable (off by
        default). When disabled this returns immediately without importing
        ``mlx`` so the float32 path — and unit tests that stub the MLX modules —
        is completely unaffected.

        bf16 keeps the float32 exponent range (no overflow risk, unlike fp16),
        matches the precision the DiT is trained/served at on CUDA, and roughly
        halves both matmul time and weight bandwidth on the M-series GPU.

        Returns:
            bool: ``True`` when the decoder was converted to bf16, else ``False``.
        """
        if not _mlx_dit_bf16_requested():
            return False
        try:
            import mlx.core as mx
            from mlx.utils import tree_map

            def _to_bf16(value):
                """Cast floating MLX arrays to bfloat16, leaving others intact."""
                if isinstance(value, mx.array) and mx.issubdtype(value.dtype, mx.floating):
                    return value.astype(mx.bfloat16)
                return value

            mlx_decoder.update(tree_map(_to_bf16, mlx_decoder.parameters()))
            mlx_decoder.compute_dtype = mx.bfloat16
            mx.eval(mlx_decoder.parameters())
            logger.info("[MLX-DiT] Parameters converted to bfloat16 (ACESTEP_MLX_DIT_BF16=1).")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[MLX-DiT] bfloat16 conversion failed ({exc}); staying on float32."
            )
            return False
