"""
Interactive wizard for ACE-Step Training V2.

Launched when ``python train.py`` is run with no subcommand.  Provides a
session loop so the user can preprocess, train, manage presets, and access
experimental features without restarting.

Submenus are in ``wizard_menus.py``; flow builders are in ``flows*.py``.
"""

from __future__ import annotations

import argparse
from typing import Generator, Optional

from acestep.training_v2.ui import console, is_rich_active
from acestep.training_v2.ui.prompt_helpers import GoBack, menu
from acestep.training_v2.ui.flows import wizard_train, wizard_preprocess
from acestep.training_v2.ui.wizard_menus import experimental_menu, manage_presets_menu, _print_msg


# ---- First-run check -------------------------------------------------------

def _ensure_first_run_done() -> None:
    """Run the first-time setup wizard if settings don't exist yet."""
    from acestep.training_v2.settings import is_first_run, save_settings
    from acestep.training_v2.ui.flows_setup import run_first_setup

    if not is_first_run():
        return

    try:
        data = run_first_setup()
        save_settings(data)
    except (KeyboardInterrupt, EOFError):
        if is_rich_active() and console is not None:
            console.print("\n  [dim]Setup skipped. You can run it later from Settings.[/]")
        else:
            print("\n  Setup skipped. You can run it later from Settings.")


# ---- Session loop -----------------------------------------------------------

def run_wizard_session() -> Generator[argparse.Namespace, None, None]:
    """Launch the interactive wizard as a session loop.

    Yields one ``argparse.Namespace`` per action the user selects.
    The caller (``train.py:main()``) dispatches each, cleans up GPU,
    and the loop shows the menu again.

    After preprocessing, offers to chain directly into training.
    """
    from acestep.training_v2.ui.banner import show_banner
    from acestep.training_v2.ui.prompt_helpers import ask_bool

    show_banner(subcommand="interactive")

    # First-run setup (skippable)
    _ensure_first_run_done()

    while True:
        try:
            ns = _main_menu()
        except (KeyboardInterrupt, EOFError):
            _print_abort()
            return

        if ns is None:
            return  # user chose Exit

        is_preprocess = getattr(ns, "preprocess", False)
        tensor_output = getattr(ns, "tensor_output", None)

        yield ns

        # Flow chaining: after preprocess, offer to train on the output
        if is_preprocess and tensor_output:
            try:
                _print_msg("")
                if ask_bool("Train on these tensors now?", default=True):
                    try:
                        adapter = menu(
                            "Which adapter type?",
                            [("lora", "LoRA (PEFT)"), ("lokr", "LoKR (LyCORIS)")],
                            default=1,
                        )
                        chain_ns = wizard_train(
                            mode="fixed",
                            adapter_type=adapter,
                            preset={"dataset_dir": tensor_output},
                        )
                        yield chain_ns
                    except GoBack:
                        pass
            except (KeyboardInterrupt, EOFError):
                pass


# ---- Main menu --------------------------------------------------------------

def _main_menu() -> Optional[argparse.Namespace]:
    """Show the main menu and return a Namespace, or None to exit.

    Uses a loop instead of recursion to avoid hitting the stack limit
    when the user navigates back and forth many times.
    """
    while True:
        action = menu(
            "What would you like to do?",
            [
                ("train_lora", "Train a LoRA (PEFT)"),
                ("train_lokr", "Train a LoKR (LyCORIS)"),
                ("preprocess", "Preprocess audio into tensors"),
                ("presets", "Manage presets"),
                ("settings", "Settings (paths, vanilla mode)"),
                ("experimental", "Experimental (beta)"),
                ("exit", "Exit"),
            ],
            default=1,
        )

        if action == "exit":
            return None

        if action == "presets":
            manage_presets_menu()
            continue  # loop back to main menu

        if action == "settings":
            _run_settings_editor()
            continue  # loop back to main menu

        try:
            if action == "experimental":
                result = experimental_menu()
                if result is None:
                    continue  # user chose "Back" -> main menu
                return result

            if action == "preprocess":
                return wizard_preprocess()

            if action in ("train_lora", "train_lokr"):
                adapter = "lokr" if action == "train_lokr" else "lora"
                mode = _training_mode_submenu()
                if mode is None:
                    continue  # user chose "Back" -> main menu
                return wizard_train(mode=mode, adapter_type=adapter)
        except GoBack:
            continue  # loop back to main menu


def _training_mode_submenu() -> Optional[str]:
    """Ask which training mode to use. Returns 'fixed' or 'vanilla', or None for back."""
    try:
        choice = menu(
            "Which training mode?",
            [
                ("fixed", "Corrected (recommended -- continuous timesteps + CFG dropout)"),
                ("vanilla", "Vanilla (original behavior -- discrete timesteps, no CFG)"),
            ],
            default=1,
            allow_back=True,
        )
        return choice
    except GoBack:
        return None


# ---- Backward-compat shim --------------------------------------------------

def run_wizard() -> Optional[argparse.Namespace]:
    """Single-shot wizard (backward compatibility).

    Returns the first Namespace from the session loop, or None.
    """
    for ns in run_wizard_session():
        return ns
    return None


# ---- Helpers ----------------------------------------------------------------

def _run_settings_editor() -> None:
    """Open the settings editor and save any changes."""
    from acestep.training_v2.settings import save_settings
    from acestep.training_v2.ui.flows_setup import run_settings_editor

    data = run_settings_editor()
    if data is not None:
        save_settings(data)


def _print_abort() -> None:
    if is_rich_active() and console is not None:
        console.print("\n  [dim]Aborted.[/]")
    else:
        print("\n  Aborted.")
