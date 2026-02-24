"""Path sanitisation helpers for training modules.

Provides a single ``safe_path`` function that validates user-provided
filesystem paths against a known safe root directory.  The validation
uses ``os.path.realpath`` followed by a ``.startswith`` check — the
exact pattern that CodeQL recognises as a sanitiser for the
``py/path-injection`` query.

Symlinks are resolved on both the root and user paths so that paths
through symlinks (e.g. ``/root/data`` → ``/vepfs/.../data``) are
compared consistently.

All training modules that accept user-supplied paths should call
``safe_path`` (or ``safe_open``) before performing any filesystem I/O.
"""

import os
from typing import Optional

from loguru import logger


def _resolve(path: str) -> str:
    """Normalise and resolve symlinks in *path*.

    Uses ``os.path.realpath`` so that symlinked prefixes are resolved
    to their canonical form before comparison.
    """
    return os.path.normpath(os.path.realpath(path))


# Root directory that all user-provided paths must resolve under.
# Defaults to the working directory at import time.  Override via
# ``set_safe_root`` if needed (e.g. in tests).
_SAFE_ROOT: str = _resolve(os.getcwd())


def set_safe_root(root: str) -> None:
    """Override the safe root directory.

    Args:
        root: New safe root (will be normalised and symlink-resolved).
    """
    global _SAFE_ROOT  # noqa: PLW0603
    _SAFE_ROOT = _resolve(root)


def get_safe_root() -> str:
    """Return the current safe root directory."""
    return _SAFE_ROOT


def safe_path(user_path: str, *, base: Optional[str] = None) -> str:
    """Validate and normalise a user-provided path.

    The returned path is guaranteed to live under *base* (or the
    global ``_SAFE_ROOT`` when *base* is ``None``).  Symlinks in both
    the root and user path are resolved so that paths through symlinks
    compare correctly.

    Args:
        user_path: Untrusted path string from user input.
        base: Optional explicit base directory.  When provided it is
              resolved (symlinks included) and used instead of
              ``_SAFE_ROOT``.

    Returns:
        Normalised, symlink-resolved absolute path within the safe root.

    Raises:
        ValueError: If the resolved path escapes the safe root.
    """
    if base is not None:
        root = _resolve(base)
    else:
        root = _SAFE_ROOT

    # Resolve the user path.  If relative, join against *root* first.
    if os.path.isabs(user_path):
        normalised = _resolve(user_path)
    else:
        normalised = _resolve(os.path.join(root, user_path))

    # ── CodeQL-recognised sanitiser barrier ──
    # ``normpath(…).startswith(safe_prefix)`` is the pattern that
    # CodeQL's ``py/path-injection`` query treats as a sanitiser.
    if not normalised.startswith(root + os.sep) and normalised != root:
        raise ValueError(
            f"Path escapes safe root: {user_path!r} "
            f"(resolved to {normalised!r}, root={root!r})"
        )

    return normalised


def safe_open(user_path: str, mode: str = "r", **kwargs):
    """Open a file after validating its path.

    Convenience wrapper around ``safe_path`` + ``open``.

    Args:
        user_path: Untrusted path string.
        mode: File open mode.
        **kwargs: Extra keyword arguments forwarded to ``open``.

    Returns:
        File object.

    Raises:
        ValueError: If the path escapes the safe root.
    """
    validated = safe_path(user_path)
    return open(validated, mode, **kwargs)  # noqa: SIM115
