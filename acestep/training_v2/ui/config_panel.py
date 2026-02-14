"""
Pre-training configuration display.

Renders a grouped Rich Table of all training parameters, with non-default
values highlighted so the user instantly sees what they changed.

Falls back to aligned plain text when Rich is unavailable.
"""

from __future__ import annotations

import sys
from dataclasses import fields
from typing import Any, Dict, Optional

from acestep.training_v2.configs import LoRAConfigV2, TrainingConfigV2
from acestep.training_v2.ui import console, is_rich_active
from acestep.training_v2.ui.prompt_helpers import _esc

# ---- Default values (for highlighting non-default settings) -----------------

# These mirror the argparse defaults in cli/common.py.
_DEFAULTS: Dict[str, Any] = {
    # Model
    "model_variant": "turbo",
    "checkpoint_dir": "./checkpoints",
    # Device
    "device": "auto",
    "precision": "auto",
    # Training
    "learning_rate": 1e-4,
    "batch_size": 1,
    "gradient_accumulation_steps": 4,
    "max_epochs": 100,
    "warmup_steps": 100,
    "weight_decay": 0.01,
    "max_grad_norm": 1.0,
    "seed": 42,
    # LoRA
    "r": 64,
    "alpha": 128,
    "dropout": 0.1,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "bias": "none",
    # Checkpointing
    "output_dir": "",
    "save_every_n_epochs": 10,
    "resume_from": None,
    # Logging
    "log_dir": None,
    "log_every": 10,
    "log_heavy_every": 50,
    # Corrected training
    "cfg_ratio": 0.15,
    "timestep_mu": -0.4,
    "timestep_sigma": 1.0,
    "data_proportion": 0.5,
}

# Logical grouping for display.
_GROUPS = [
    (
        "Model",
        [
            ("model_variant", "Model variant"),
            ("checkpoint_dir", "Checkpoint dir"),
            ("dataset_dir", "Dataset dir"),
        ],
    ),
    (
        "Device",
        [
            ("device", "Device"),
            ("precision", "Precision"),
        ],
    ),
    (
        "LoRA",
        [
            ("r", "Rank (r)"),
            ("alpha", "Alpha"),
            ("dropout", "Dropout"),
            ("target_modules", "Target modules"),
            ("bias", "Bias"),
        ],
    ),
    (
        "Training",
        [
            ("learning_rate", "Learning rate"),
            ("batch_size", "Batch size"),
            ("gradient_accumulation_steps", "Grad accumulation"),
            ("_effective_batch", "Effective batch"),
            ("max_epochs", "Max epochs"),
            ("warmup_steps", "Warmup steps"),
            ("weight_decay", "Weight decay"),
            ("max_grad_norm", "Max grad norm"),
            ("seed", "Seed"),
        ],
    ),
    (
        "Corrected Training",
        [
            ("cfg_ratio", "CFG dropout ratio"),
            ("timestep_mu", "Timestep mu"),
            ("timestep_sigma", "Timestep sigma"),
            ("data_proportion", "Data proportion"),
        ],
    ),
    (
        "Checkpointing",
        [
            ("output_dir", "Output dir"),
            ("save_every_n_epochs", "Save every N epochs"),
            ("resume_from", "Resume from"),
        ],
    ),
    (
        "Logging",
        [
            ("log_dir", "TensorBoard dir"),
            ("log_every", "Log every N steps"),
            ("log_heavy_every", "Grad norms every N steps"),
        ],
    ),
]


def _resolve_value(
    key: str,
    lora_cfg: LoRAConfigV2,
    train_cfg: TrainingConfigV2,
) -> Any:
    """Look up a config key from either config object."""
    if key == "_effective_batch":
        return train_cfg.batch_size * train_cfg.gradient_accumulation_steps
    # LoRA fields
    for f in fields(lora_cfg):
        if f.name == key:
            return getattr(lora_cfg, key)
    # Training fields
    if hasattr(train_cfg, key):
        return getattr(train_cfg, key)
    return None


def _is_default(key: str, value: Any) -> bool:
    """Return True when *value* matches the known default for *key*."""
    if key not in _DEFAULTS:
        return True  # unknown keys are not highlighted
    default = _DEFAULTS[key]
    if isinstance(default, list) and isinstance(value, list):
        return default == value
    return value == default


def _fmt_value(value: Any) -> str:
    """Format a config value for display."""
    if value is None:
        return "(auto)"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, float):
        # Scientific notation for very small values
        if 0 < abs(value) < 0.001:
            return f"{value:.1e}"
        return f"{value:g}"
    return str(value)


# ---- Public API -------------------------------------------------------------

def show_config(
    lora_cfg: LoRAConfigV2,
    train_cfg: TrainingConfigV2,
    subcommand: str = "fixed",
    skip_corrected: bool = False,
) -> None:
    """Display the full configuration before training starts.

    Args:
        lora_cfg: LoRA configuration.
        train_cfg: Training configuration.
        subcommand: Active subcommand (used to skip irrelevant groups).
        skip_corrected: If True, hide the 'Corrected Training' group
                        (e.g. for the vanilla subcommand).
    """
    if is_rich_active() and console is not None:
        _show_rich(lora_cfg, train_cfg, subcommand, skip_corrected)
    else:
        _show_plain(lora_cfg, train_cfg, subcommand, skip_corrected)


def _show_rich(
    lora_cfg: LoRAConfigV2,
    train_cfg: TrainingConfigV2,
    subcommand: str,
    skip_corrected: bool,
) -> None:
    from rich.panel import Panel
    from rich.table import Table

    assert console is not None

    table = Table(
        show_header=True,
        header_style="bold",
        border_style="dim",
        pad_edge=True,
        expand=False,
    )
    table.add_column("Parameter", style="dim", min_width=22)
    table.add_column("Value", min_width=30)

    for group_name, keys in _GROUPS:
        if skip_corrected and group_name == "Corrected Training":
            continue
        # Section header row
        table.add_row(f"[bold cyan]{group_name}[/]", "", end_section=False)
        for key, label in keys:
            value = _resolve_value(key, lora_cfg, train_cfg)
            formatted = _fmt_value(value)
            is_def = _is_default(key, value)
            if is_def:
                table.add_row(f"  {label}", _esc(formatted))
            else:
                table.add_row(f"  {label}", f"[bold yellow]{_esc(formatted)}[/]")

    console.print(
        Panel(
            table,
            title="[bold]Training Configuration[/]",
            border_style="blue",
            padding=(0, 1),
        )
    )


def _show_plain(
    lora_cfg: LoRAConfigV2,
    train_cfg: TrainingConfigV2,
    subcommand: str,
    skip_corrected: bool,
) -> None:
    print("=" * 60, file=sys.stderr)
    print("  Training Configuration", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    for group_name, keys in _GROUPS:
        if skip_corrected and group_name == "Corrected Training":
            continue
        print(f"\n  [{group_name}]", file=sys.stderr)
        for key, label in keys:
            value = _resolve_value(key, lora_cfg, train_cfg)
            formatted = _fmt_value(value)
            marker = " *" if not _is_default(key, value) else ""
            print(f"    {label:.<24s} {formatted}{marker}", file=sys.stderr)

    print("\n" + "=" * 60, file=sys.stderr)
    print("  (* = non-default value)", file=sys.stderr)
    print("=" * 60 + "\n", file=sys.stderr)


# ---- Confirmation prompt ----------------------------------------------------

def confirm_start(skip: bool = False) -> bool:
    """Ask the user to confirm before training.  Returns True to proceed.

    Args:
        skip: If True (``--yes`` flag), skip the prompt and return True.
    """
    if skip:
        return True

    if is_rich_active() and console is not None:
        from rich.prompt import Confirm
        try:
            return Confirm.ask(
                "[bold]Start training?[/]",
                default=True,
                console=console,
            )
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]Aborted.[/]")
            return False
    else:
        try:
            answer = input("Start training? [Y/n] ").strip().lower()
            return answer in ("", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.", file=sys.stderr)
            return False
