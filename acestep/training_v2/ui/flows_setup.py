"""
First-run setup wizard and settings editor for Side-Step.

Runs automatically on the first launch.  Collects the checkpoint
directory path and vanilla-mode intent.
Re-accessible from the main menu under "Settings".

Note: This is the upstream-integrated version of Side-Step.
For the standalone version with additional features, visit:
https://github.com/koda-dernet/Side-Step
"""

from __future__ import annotations

import logging
from pathlib import Path

from acestep.training_v2.ui import console, is_rich_active
from acestep.training_v2.ui.prompt_helpers import (
    ask_bool,
    ask_path,
    native_path,
    section,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print(msg: str) -> None:
    """Print via Rich console if available, else plain print."""
    if is_rich_active() and console is not None:
        console.print(msg)
    else:
        # Strip Rich markup for plain output
        import re
        print(re.sub(r"\[/?[^\]]*\]", "", msg))


def _smart_checkpoint_default() -> str:
    """Pick a sensible default checkpoint path based on context."""
    for rel in ("./checkpoints", "../checkpoints"):
        if Path(rel).is_dir():
            return native_path(rel)
    return native_path("./checkpoints")


# ---------------------------------------------------------------------------
# First-run wizard
# ---------------------------------------------------------------------------

def run_first_setup() -> dict:
    """Walk the user through first-time setup.

    Returns the settings dict ready for ``save_settings()``.
    """
    from acestep.training_v2.settings import _default_settings

    data = _default_settings()

    # -- Welcome + disclaimer -----------------------------------------------
    section("Welcome to Side-Step")
    _print("  [bold]Before we begin, a few important notes:[/]\n")
    _print("  [yellow]1.[/] You are responsible for downloading the model weights")
    _print("     you want to train on (e.g. via [bold]acestep-download[/] or manually).")
    _print("  [yellow]2.[/] If you are training on a fine-tune, you [bold]MUST[/] also have")
    _print("     the original base model that fine-tune was built from.")
    _print("  [yellow]3.[/] [bold]Never rename checkpoint folders.[/] The model loader uses")
    _print("     folder names and config.json files to identify models.\n")

    _print("  [dim]This is the upstream-integrated version of Side-Step.[/]")
    _print("  [dim]For the standalone version with more features:[/]")
    _print("  [dim]https://github.com/koda-dernet/Side-Step[/]\n")

    # -- Vanilla intent -----------------------------------------------------
    section("Vanilla Training Mode")
    _print("  Side-Step's [bold green]corrected (fixed)[/] training is the recommended mode.")
    _print("  [bold yellow]Vanilla[/] mode reproduces the original ACE-Step training")
    _print("  behavior (discrete timesteps, no CFG dropout).\n")

    data["vanilla_enabled"] = ask_bool(
        "Do you plan to use Vanilla training mode?",
        default=False,
    )

    # -- Checkpoint directory -----------------------------------------------
    section("Model Checkpoints")
    _print("  Where are your model checkpoint folders?")
    _print("  [dim](Each model variant lives in its own subfolder, e.g.\n   checkpoints/acestep-v15-turbo/, checkpoints/acestep-v15-base/, etc.)[/]\n")

    default_ckpt = _smart_checkpoint_default()
    while True:
        ckpt_dir = ask_path("Checkpoint directory", default=default_ckpt)
        ckpt_path = Path(ckpt_dir)
        if not ckpt_path.is_dir():
            _print(f"  [red]Directory not found: {ckpt_dir}[/]")
            if not ask_bool("Try a different path?", default=True):
                break
            continue

        # Scan for model subdirectories
        from acestep.training_v2.model_discovery import scan_models
        models = scan_models(ckpt_dir)
        if models:
            _print(f"\n  [green]Found {len(models)} model(s):[/]")
            for m in models:
                tag = "[green](official)[/]" if m.is_official else "[yellow](custom)[/]"
                _print(f"    - {m.name}  {tag}")
            _print("")
            break
        else:
            _print("  [yellow]No model directories found in that location.[/]")
            _print("  [dim](Looking for subfolders with a config.json file.)[/]")
            if not ask_bool("Try a different path?", default=True):
                break

    data["checkpoint_dir"] = ckpt_dir
    data["first_run_complete"] = True

    # -- Summary ------------------------------------------------------------
    section("Setup Complete")
    _print(f"  Checkpoint dir : [bold]{data['checkpoint_dir']}[/]")
    if data["vanilla_enabled"]:
        _print("  Vanilla mode   : [bold green]enabled[/]")
    else:
        _print("  Vanilla mode   : [bold yellow]disabled[/] (corrected mode recommended)")
    _print("")
    _print("  [dim]You can change these any time from the main menu → Settings.[/]\n")

    return data


# ---------------------------------------------------------------------------
# Settings editor (re-run setup from the menu)
# ---------------------------------------------------------------------------

def run_settings_editor() -> dict | None:
    """Re-run the setup flow from defaults.

    Returns the updated settings dict, or ``None`` if the user cancels.
    """
    from acestep.training_v2.settings import load_settings

    _print("\n  [bold]Re-running Side-Step setup...[/]\n")
    try:
        return run_first_setup()
    except (KeyboardInterrupt, EOFError):
        _print("  [dim]Cancelled.[/]")
        return None
