"""
ACE-Step Training V2 -- Rich UI Layer

Provides a shared ``Console`` instance and a ``RICH_AVAILABLE`` flag so that
every UI module can degrade gracefully when Rich is not installed.

Exports
-------
console : Console | None
    Shared Rich console (``None`` when Rich is missing).
RICH_AVAILABLE : bool
    ``True`` when ``rich>=13`` is importable.
plain_mode : bool
    Module-level flag toggled by ``--plain``.  When ``True`` *or* stdout is
    not a TTY, all UI helpers fall back to plain ``print()`` output.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterator, Tuple

# ---- Rich availability check ------------------------------------------------

RICH_AVAILABLE: bool = False
console = None  # type: ignore[assignment]

try:
    from rich.console import Console as _Console

    console = _Console(stderr=True)  # UI goes to stderr so stdout stays clean
    RICH_AVAILABLE = True
except ImportError:
    pass

# ---- Plain-mode flag (set via --plain CLI arg) ------------------------------

plain_mode: bool = False


def set_plain_mode(value: bool) -> None:
    """Toggle plain-text output globally."""
    global plain_mode
    plain_mode = value


def is_rich_active() -> bool:
    """Return True when Rich output should be used."""
    if plain_mode or not RICH_AVAILABLE:
        return False
    if console is not None and not console.is_terminal:
        return False
    return True


def require_rich() -> None:
    """Print an install hint and exit if Rich is missing."""
    if RICH_AVAILABLE:
        return
    print(
        "[FAIL] Rich is required for the pretty CLI.\n"
        "       Install it with:  pip install rich\n"
        "       Or use --plain for basic text output.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---- TrainingUpdate (backward-compatible structured yield) ------------------

@dataclass
class TrainingUpdate:
    """Structured object yielded by the trainer, backward-compatible with
    ``(step, loss, msg)`` tuple unpacking.

    Extra fields give the UI enough context to render a live dashboard
    without parsing message strings.
    """

    step: int
    loss: float
    msg: str
    kind: str = "info"
    """One of: info, step, epoch, checkpoint, complete, warn, fail."""
    epoch: int = 0
    max_epochs: int = 0
    lr: float = 0.0
    epoch_time: float = 0.0
    samples_per_sec: float = 0.0
    steps_per_epoch: int = 0
    """Total optimizer steps per epoch (for step-level progress bar)."""
    checkpoint_path: str = ""
    """Filesystem path emitted with kind='checkpoint'."""

    # -- backward compat: ``for step, loss, msg in trainer.train():`` --------
    def __iter__(self) -> Iterator[Tuple[int, float, str]]:  # type: ignore[override]
        return iter((self.step, self.loss, self.msg))
