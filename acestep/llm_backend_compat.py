"""Compatibility helpers for optional 5Hz LM backends."""

import importlib
import sys


def _has_working_triton_installation() -> bool:
    """Return whether the Triton modules required by nano-vllm import cleanly."""
    try:
        importlib.import_module("triton")
        importlib.import_module("triton.language")
        return True
    except (ImportError, ModuleNotFoundError):
        return False


def get_vllm_preflight_warning(*, device: str, platform: str | None = None) -> str | None:
    """Return a user-facing warning when vLLM should be skipped before initialization.

    Args:
        device: The resolved device string for LM initialization.
        platform: Optional platform override for tests. Defaults to ``sys.platform``.

    Returns:
        A warning string when vLLM should fall back to PyTorch, otherwise ``None``.
    """
    active_platform = sys.platform if platform is None else platform
    if device != "cuda" or active_platform != "win32":
        return None
    if _has_working_triton_installation():
        return None
    return (
        "vLLM backend is unavailable on Windows because Triton is not installed "
        "or is incompatible. Falling back to the PyTorch backend. "
        "Use --backend pt to suppress this warning."
    )