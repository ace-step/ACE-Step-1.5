"""
Submenu implementations for the wizard session loop.

Extracted from ``wizard.py`` to keep modules under the LOC cap.
"""

from __future__ import annotations

import argparse
from typing import Optional

from acestep.training_v2.ui import console, is_rich_active
from acestep.training_v2.ui.prompt_helpers import GoBack, menu, section, ask


def experimental_menu() -> Optional[argparse.Namespace]:
    """Show experimental features and return a Namespace, or None to go back.

    Uses a loop instead of recursion.  Returns None when the user
    chooses 'Back', which the caller interprets as "show main menu".
    """
    from acestep.training_v2.ui.flows import wizard_estimate

    if is_rich_active() and console is not None:
        console.print(
            "\n  [dim]These features are functional but under active development.\n"
            "  Results may vary. Feedback welcome.[/]"
        )
    else:
        print(
            "\n  These features are functional but under active development.\n"
            "  Results may vary. Feedback welcome."
        )

    while True:
        action = menu(
            "Experimental Features",
            [
                ("estimate", "Gradient estimation (analyze which layers learn fastest)"),
                ("back", "Back"),
            ],
            default=2,
        )

        if action == "back":
            return None  # caller loops back to main menu

        if action == "estimate":
            try:
                return wizard_estimate()
            except GoBack:
                continue  # stay in experimental menu


def manage_presets_menu() -> None:
    """Submenu for listing, viewing, deleting, importing, and exporting presets."""
    from acestep.training_v2.ui.presets import (
        list_presets, load_preset, delete_preset, import_preset, export_preset,
    )

    while True:
        action = menu(
            "Manage Presets",
            [
                ("list", "List all presets"),
                ("view", "View preset details"),
                ("delete", "Delete a user preset"),
                ("import", "Import preset from file"),
                ("export", "Export preset to file"),
                ("back", "Back"),
            ],
            default=6,
        )

        if action == "back":
            return

        presets = list_presets()

        if action == "list":
            if not presets:
                _print_msg("  No presets found.")
                continue
            section("Available Presets")
            for p in presets:
                tag = " (built-in)" if p["builtin"] else ""
                desc = f" -- {p['description']}" if p["description"] else ""
                _print_msg(f"    {p['name']}{tag}{desc}")
            _print_msg("")

        elif action == "view":
            if not presets:
                _print_msg("  No presets found.")
                continue
            name = ask("Preset name to view", required=True)
            data = load_preset(name)
            if data is None:
                _print_msg(f"  Preset '{name}' not found.")
            else:
                section(f"Preset: {name}")
                for k, v in sorted(data.items()):
                    _print_msg(f"    {k}: {v}")
                _print_msg("")

        elif action == "delete":
            user_presets = [p for p in presets if not p["builtin"]]
            if not user_presets:
                _print_msg("  No user presets to delete.")
                continue
            name = ask("Preset name to delete", required=True)
            if delete_preset(name):
                _print_msg(f"  Deleted preset '{name}'.")
            else:
                _print_msg(f"  Preset '{name}' not found (or is built-in).")

        elif action == "import":
            path = ask("Path to preset JSON file", required=True)
            imported = import_preset(path)
            if imported:
                _print_msg(f"  Imported preset '{imported}'.")
            else:
                _print_msg("  Import failed. Check the file path and format.")

        elif action == "export":
            name = ask("Preset name to export", required=True)
            dest = ask("Destination path", required=True)
            if export_preset(name, dest):
                _print_msg(f"  Exported '{name}' to {dest}.")
            else:
                _print_msg(f"  Preset '{name}' not found.")


def _print_msg(msg: str) -> None:
    """Print a message using Rich if available, plain otherwise."""
    if is_rich_active() and console is not None:
        # Strip Rich markup for plain fallback detection
        console.print(msg)
    else:
        # Remove Rich markup tags for plain output
        import re
        clean = re.sub(r"\[/?[^\]]*\]", "", msg)
        print(clean)
