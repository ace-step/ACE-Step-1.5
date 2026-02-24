# Native MLX implementations of AceStep models for Apple Silicon.
# Provides pure MLX inference with graceful fallback to PyTorch.

import logging
import platform

logger = logging.getLogger(__name__)


def is_mlx_available() -> bool:
    """Check if MLX is available on this platform (macOS + Apple Silicon)."""
    if platform.system() != "Darwin":
        return False
    try:
        import mlx.core as mx
        import mlx.nn
        # Verify we can actually create arrays (Metal backend works)
        _ = mx.array([1.0])
        mx.eval(_)
        return True
    except Exception:
        return False


_MLX_AVAILABLE = None


def mlx_available() -> bool:
    """Cached check for MLX availability."""
    global _MLX_AVAILABLE
    if _MLX_AVAILABLE is None:
        _MLX_AVAILABLE = is_mlx_available()
    return _MLX_AVAILABLE
