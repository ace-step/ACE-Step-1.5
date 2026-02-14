"""
Reusable Rich/fallback prompt helpers for the interactive wizard.

Provides menu selection, typed value prompts, path prompts, boolean prompts,
section headers, go-back navigation, and step indicators -- with automatic
Rich fallback to plain ``input()``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from acestep.training_v2.ui import console, is_rich_active

# Windows uses spawn-based multiprocessing which breaks DataLoader workers
IS_WINDOWS = sys.platform == "win32"
DEFAULT_NUM_WORKERS = 0 if IS_WINDOWS else 4

# Back-navigation keyword recognised by all prompts
_BACK_KEYWORDS = {"b", "back"}


def _esc(text: object) -> str:
    """Escape Rich markup characters in user-provided text for safe display.

    Replaces ``[`` with ``\\[`` so that paths and other user input containing
    square brackets (e.g. ``/media/user/[volume]/path``) are not interpreted
    as Rich markup tags.
    """
    return str(text).replace("[", "\\[")


def native_path(path: str) -> str:
    """Convert a path string to use the native OS separator for display.

    On Windows, replaces forward slashes with backslashes so that path
    defaults shown in wizard prompts look natural to the user
    (e.g. ``.\checkpoints`` instead of ``./checkpoints``).

    On Linux/macOS, returns the path unchanged.
    """
    if IS_WINDOWS:
        return path.replace("/", "\\")
    return path


# ---- Go-back exception -----------------------------------------------------

class GoBack(Exception):
    """Raised when the user types 'b' or 'back' at any prompt."""


def _is_back(raw: str) -> bool:
    """Return True if the raw input string is a back-navigation request."""
    return raw.strip().lower() in _BACK_KEYWORDS


# ---- Step indicator ---------------------------------------------------------

def step_indicator(current: int, total: int, label: str) -> None:
    """Print a step progress indicator, e.g. ``[Step 3/8] LoRA Settings``."""
    tag = f"Step {current}/{total}"
    if is_rich_active() and console is not None:
        # Use \[ to escape the bracket so Rich doesn't parse it as markup
        console.print(f"\n  [bold green]\\[{tag}][/] [bold]{label}[/]")
    else:
        print(f"\n  [{tag}] {label}")


# ---- Helpers ----------------------------------------------------------------

def menu(
    title: str,
    options: list[tuple[str, str]],
    default: int = 1,
    allow_back: bool = False,
) -> str:
    """Display a numbered menu and return the chosen key.

    Args:
        title: Prompt text.
        options: List of ``(key, label)`` tuples.
        default: 1-based default index.
        allow_back: If True, typing 'b'/'back' raises ``GoBack``.

    Returns:
        The ``key`` of the chosen option.

    Raises:
        GoBack: When ``allow_back`` is True and user types 'b'/'back'.
    """
    back_hint = "  [dim]Type 'b' to go back[/]" if allow_back else ""
    back_hint_plain = "  Type 'b' to go back" if allow_back else ""

    if is_rich_active() and console is not None:
        console.print()
        console.print(f"  [bold]{title}[/]\n")
        for i, (key, label) in enumerate(options, 1):
            marker = "[bold cyan]>[/]" if i == default else " "
            tag = "  [dim](default)[/]" if i == default else ""
            console.print(f"    {marker} [bold]{i}[/]. {label}{tag}")
        if back_hint:
            console.print(back_hint)
        console.print()

        from rich.prompt import IntPrompt
        while True:
            raw = console.input("  Choice: ") if allow_back else None
            if allow_back and raw is not None:
                if _is_back(raw):
                    raise GoBack()
                try:
                    choice = int(raw) if raw.strip() else default
                except ValueError:
                    console.print(f"  [red]Please enter a number between 1 and {len(options)}[/]")
                    continue
            else:
                choice = IntPrompt.ask(
                    "  Choice",
                    default=default,
                    console=console,
                )
            if 1 <= choice <= len(options):
                return options[choice - 1][0]
            console.print(f"  [red]Please enter a number between 1 and {len(options)}[/]")
    else:
        print(f"\n  {title}\n")
        for i, (key, label) in enumerate(options, 1):
            tag = " (default)" if i == default else ""
            print(f"    {i}. {label}{tag}")
        if back_hint_plain:
            print(back_hint_plain)
        print()
        while True:
            try:
                raw = input(f"  Choice [{default}]: ").strip()
                if allow_back and _is_back(raw):
                    raise GoBack()
                choice = int(raw) if raw else default
                if 1 <= choice <= len(options):
                    return options[choice - 1][0]
                print(f"  Please enter a number between 1 and {len(options)}")
            except ValueError:
                print(f"  Please enter a number between 1 and {len(options)}")


def ask(
    label: str,
    default: Any = None,
    required: bool = False,
    type_fn: type = str,
    choices: Optional[list] = None,
    allow_back: bool = False,
) -> Any:
    """Ask for a single value with an optional default.

    Args:
        label: Prompt text.
        default: Default value (None = required).
        required: If True, empty input is rejected.
        type_fn: Cast function (str, int, float).
        choices: Optional list of valid string values.
        allow_back: If True, typing 'b'/'back' raises ``GoBack``.

    Returns:
        The user's input, cast to ``type_fn``.

    Raises:
        GoBack: When ``allow_back`` is True and user types 'b'/'back'.
    """
    if choices:
        choice_str = f" ({'/'.join(str(c) for c in choices)})"
    else:
        choice_str = ""

    if is_rich_active() and console is not None:
        from rich.prompt import Prompt, IntPrompt, FloatPrompt

        prompt_cls = Prompt
        if type_fn is int:
            prompt_cls = IntPrompt
        elif type_fn is float:
            prompt_cls = FloatPrompt

        while True:
            if allow_back:
                # Use raw console.input so we can intercept 'b'/'back'
                # Escape default value so paths with brackets aren't
                # misinterpreted as Rich markup tags.
                default_str = f" \\[{_esc(default)}]" if default is not None else ""
                raw = console.input(f"  {label}{choice_str}{default_str}: ").strip()
                if _is_back(raw):
                    raise GoBack()
                if not raw and default is not None:
                    return default
                if not raw and required:
                    console.print("  [red]This field is required[/]")
                    continue
                try:
                    val = type_fn(raw)
                except (ValueError, TypeError):
                    console.print(f"  [red]Invalid input, expected {type_fn.__name__}[/]")
                    continue
                if choices and str(val) not in [str(c) for c in choices]:
                    console.print(f"  [red]Must be one of: {', '.join(str(c) for c in choices)}[/]")
                    continue
                return val
            else:
                result = prompt_cls.ask(
                    f"  {label}{choice_str}",
                    default=default if default is not None else ...,
                    console=console,
                )
                if result is ...:
                    if required:
                        console.print("  [red]This field is required[/]")
                        continue
                    return None
                if required and not str(result).strip():
                    console.print("  [red]This field is required[/]")
                    continue
                if choices and str(result) not in [str(c) for c in choices]:
                    console.print(f"  [red]Must be one of: {', '.join(str(c) for c in choices)}[/]")
                    continue
                return type_fn(result) if not isinstance(result, type_fn) else result
    else:
        default_str = f" [{default}]" if default is not None else ""
        while True:
            raw = input(f"  {label}{choice_str}{default_str}: ").strip()
            if allow_back and _is_back(raw):
                raise GoBack()
            if not raw and default is not None:
                return default
            if not raw and required:
                print("  This field is required")
                continue
            try:
                val = type_fn(raw)
                if choices and str(val) not in [str(c) for c in choices]:
                    print(f"  Must be one of: {', '.join(str(c) for c in choices)}")
                    continue
                return val
            except (ValueError, TypeError):
                print(f"  Invalid input, expected {type_fn.__name__}")


def ask_path(
    label: str,
    default: Optional[str] = None,
    must_exist: bool = False,
    allow_back: bool = False,
) -> str:
    """Ask for a filesystem path, optionally validating existence.

    Raises:
        GoBack: When ``allow_back`` is True and user types 'b'/'back'.
    """
    while True:
        val = ask(label, default=default, required=True, allow_back=allow_back)
        if must_exist and not Path(val).exists():
            if is_rich_active() and console is not None:
                console.print(f"  [red]Path not found: {_esc(val)}[/]")
            else:
                print(f"  Path not found: {val}")
            continue
        return val


def ask_bool(label: str, default: bool = True, allow_back: bool = False) -> bool:
    """Ask for a yes/no boolean value.

    Raises:
        GoBack: When ``allow_back`` is True and user types 'b'/'back'.
    """
    choices = ["yes", "no"]
    default_str = "yes" if default else "no"
    result = ask(label, default=default_str, choices=choices, allow_back=allow_back)
    return result.lower() in ("yes", "y", "true", "1")


def section(title: str) -> None:
    """Print a section header."""
    if is_rich_active() and console is not None:
        console.print(f"\n  [bold cyan]--- {title} ---[/]\n")
    else:
        print(f"\n  --- {title} ---\n")
