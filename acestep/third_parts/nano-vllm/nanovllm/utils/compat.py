"""Compatibility utilities for optional dependencies.

Provides graceful fallbacks when torch.compile's backend (Triton) is
unavailable — e.g. on Windows or on GPU architectures where Triton
has not yet added support (Blackwell / SM 120 as of early 2026).
"""

from typing import Any, Callable, Optional, TypeVar

from loguru import logger

F = TypeVar("F", bound=Callable[..., Any])

# Module-level Triton availability check — runs once at import time
# rather than repeating the import probe at every decoration site.
_HAS_TRITON = False
try:
    import triton  # noqa: F401
    _HAS_TRITON = True
except ImportError:
    pass


def maybe_compile(fn: Optional[F] = None, **compile_kwargs: Any) -> Any:
    """Apply ``torch.compile`` only when its backend (Triton) is available.

    Drop-in replacement for the ``@torch.compile`` decorator.  When Triton
    is importable the function is compiled as usual; otherwise the original
    function is returned unmodified so inference still works (just without
    the kernel-fusion speed-up).

    Args:
        fn: The function to compile. When used as ``@maybe_compile`` (without
            parentheses) the decorated function is passed directly.  When used
            as ``@maybe_compile(...)`` this is ``None`` and a decorator is
            returned instead.
        **compile_kwargs: Keyword arguments forwarded to ``torch.compile``
            (e.g. ``dynamic=True``, ``fullgraph=True``).

    Returns:
        The compiled function when Triton is available, or the original
        unmodified function as a fallback.

    Usage::

        @maybe_compile
        def forward(self, x):
            ...

        # or with keyword arguments:
        @maybe_compile(dynamic=True)
        def forward(self, x):
            ...
    """
    def decorator(func: F) -> F:
        """Inner decorator that performs the actual compile-or-skip logic."""
        if _HAS_TRITON:
            import torch
            return torch.compile(func, **compile_kwargs)
        logger.info(
            "Triton not available — skipping torch.compile for {} "
            "(inference will use native PyTorch kernels)",
            func.__qualname__,
        )
        return func

    # Support both @maybe_compile and @maybe_compile(...) syntax
    if fn is not None:
        return decorator(fn)
    return decorator
