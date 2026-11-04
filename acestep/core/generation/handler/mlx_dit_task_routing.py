"""Decide whether a generation task may run on the native MLX DiT backend.

Source-separation-style tasks (``extract``, ``lego``, ``complete``) produce
wrong output on the MLX DiT path for ``acestep-v15-base`` (extract returns an
attenuated copy of the source mix instead of the requested stem), while the
PyTorch DiT path is correct. Until MLX parity is confirmed for these tasks they
are routed to the PyTorch DiT.
"""

from loguru import logger

MLX_DIT_UNSUPPORTED_TASKS = frozenset({"extract", "lego", "complete"})


def should_use_mlx_dit(mlx_ready: bool, task_type: str) -> bool:
    """Return whether diffusion should run on the MLX DiT for ``task_type``.

    Args:
        mlx_ready: True when MLX DiT is enabled and a decoder is loaded.
        task_type: Resolved generation task type (e.g. ``"extract"``).

    Returns:
        True to use MLX, False to use the PyTorch DiT. Logs a warning when an
        available MLX backend is bypassed for an unsupported task.
    """
    if not mlx_ready:
        return False
    if task_type in MLX_DIT_UNSUPPORTED_TASKS:
        logger.warning(
            "[service_generate] task_type={!r} is not supported on the MLX DiT "
            "backend; using the PyTorch DiT instead.",
            task_type,
        )
        return False
    return True
