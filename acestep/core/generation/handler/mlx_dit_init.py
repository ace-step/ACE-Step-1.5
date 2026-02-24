"""MLX DiT initialization helpers for Apple Silicon acceleration."""

from loguru import logger


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
            self.mlx_decoder = mlx_decoder
            self.use_mlx_dit = True
            self.mlx_dit_compiled = compile_model
            logger.info(
                "[MLX-DiT] Native MLX DiT decoder initialized successfully "
                f"(mx.compile={compile_model})."
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[MLX-DiT] Failed to initialize MLX decoder (non-fatal): {exc}")
            self.mlx_decoder = None
            self.use_mlx_dit = False
            self.mlx_dit_compiled = False
            return False
