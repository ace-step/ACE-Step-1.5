"""Shared helpers for training event handlers.

Contains constants, utility functions, and common UI helpers
used across dataset, preprocessing, and training sub-modules.
"""

import os
import re
import time
from typing import Any, Dict, List, Optional

import gradio as gr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from acestep.ui.gradio.i18n import t
from acestep.training.path_safety import get_safe_root

SAFE_TRAINING_ROOT = get_safe_root()


def create_dataset_builder():
    """Create a new DatasetBuilder instance.

    Lazy import to avoid heavy module load at startup.
    """
    from acestep.training.dataset_builder import DatasetBuilder
    return DatasetBuilder()


def _safe_slider(
    max_value: int,
    value: int = 0,
    visible: Optional[bool] = None,
) -> gr.Slider:
    """Create a slider with a non-zero range to avoid Gradio math errors."""
    max_value = max(1, int(max_value))
    kwargs: Dict[str, Any] = {
        "maximum": max_value,
        "value": min(int(value), max_value),
    }
    if visible is not None:
        kwargs["visible"] = visible
    return gr.Slider(**kwargs)


def _safe_join(base_root: str, user_path: str) -> Optional[str]:
    """Safely join user path to base root, preventing directory traversal.

    Uses ``os.path.normpath`` + ``startswith`` — the pattern CodeQL
    recognises as a path-injection sanitiser.
    """
    if not user_path or not user_path.strip():
        return None
    candidate = user_path.strip()
    if os.path.isabs(candidate):
        return None
    abs_root = os.path.normpath(os.path.abspath(base_root))
    joined = os.path.normpath(os.path.join(abs_root, candidate))
    if not joined.startswith(abs_root + os.sep) and joined != abs_root:
        return None
    return joined


def _format_duration(seconds: float) -> str:
    """Format seconds to human readable string (e.g. ``2m 30s``)."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def _training_loss_figure(
    training_state: Dict,
    step_list: List[int],
    loss_list: List[float],
) -> Optional[Any]:
    """Build a training/validation loss plot (matplotlib Figure) for ``gr.Plot``."""
    steps = training_state.get("plot_steps") or step_list
    loss = training_state.get("plot_loss") or loss_list
    if not steps or not loss:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.set_xlabel("Step")
        ax.set_ylabel("Loss")
        ax.set_title("Training loss")
        fig.tight_layout()
        return fig
    ema = training_state.get("plot_ema")
    val_steps = training_state.get("plot_val_steps") or []
    val_loss = training_state.get("plot_val_loss") or []
    best_step = training_state.get("plot_best_step")

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(steps, loss, color="tab:blue", alpha=0.35, label="Loss (raw)", linewidth=1)
    if ema and len(ema) == len(steps):
        ax.plot(steps, ema, color="tab:blue", alpha=1.0, label="Loss (smoothed)", linewidth=1.5)
    if val_steps and val_loss:
        ax.scatter(val_steps, val_loss, color="tab:orange", s=24, zorder=5, label="Validation")
    if best_step is not None:
        ax.axvline(x=best_step, color="tab:green", linestyle="--", alpha=0.8, label="Best checkpoint")
    ax.set_xlabel("Step")
    ax.set_ylabel("Loss")
    ax.set_title("Training loss")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig
