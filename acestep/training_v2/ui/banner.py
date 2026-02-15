"""
Startup banner for Side-Step CLI.

Shows a branded header with a random motto (Minecraft-style splash),
subcommand, framework versions, and GPU info.
"""

from __future__ import annotations

import random
import shutil
import sys
import textwrap
from typing import Optional

from acestep.training_v2.ui import console, is_rich_active

# ---- ASCII logos (wide BlurVision + narrow fallback) -------------------------

# Multi-line BlurVision gradient-block art (Unicode shade characters)
_LOGO_WIDE_LINES = [
    " \u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591",
    "\u2591\u2592\u2593\u2588\u2593\u2592\u2591      \u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591      \u2591\u2592\u2593\u2588\u2593\u2592\u2591         \u2591\u2592\u2593\u2588\u2593\u2592\u2591   \u2591\u2592\u2593\u2588\u2593\u2592\u2591      \u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2593\u2592\u2591",
    "\u2591\u2592\u2593\u2588\u2593\u2592\u2591      \u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591      \u2591\u2592\u2593\u2588\u2593\u2592\u2591         \u2591\u2592\u2593\u2588\u2593\u2592\u2591   \u2591\u2592\u2593\u2588\u2593\u2592\u2591      \u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2593\u2592\u2591",
    " \u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591  \u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591   \u2591\u2592\u2593\u2588\u2593\u2592\u2591   \u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591 \u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591",
    "       \u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591             \u2591\u2592\u2593\u2588\u2593\u2592\u2591  \u2591\u2592\u2593\u2588\u2593\u2592\u2591   \u2591\u2592\u2593\u2588\u2593\u2592\u2591      \u2591\u2592\u2593\u2588\u2593\u2592\u2591",
    "       \u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591             \u2591\u2592\u2593\u2588\u2593\u2592\u2591  \u2591\u2592\u2593\u2588\u2593\u2592\u2591   \u2591\u2592\u2593\u2588\u2593\u2592\u2591      \u2591\u2592\u2593\u2588\u2593\u2592\u2591",
    "\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591   \u2591\u2592\u2593\u2588\u2593\u2592\u2591   \u2591\u2592\u2593\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2593\u2592\u2591\u2592\u2593\u2588\u2593\u2592\u2591",
]

_LOGO_NARROW = textwrap.dedent(r"""
  ███████ ██ ██████  ███████
  ██      ██ ██   ██ ██
  ███████ ██ ██   ██ █████
       ██ ██ ██   ██ ██
  ███████ ██ ██████  ███████

  ███████ ████████ ███████ ██████
  ██         ██    ██      ██   ██
  ███████    ██    █████   ██████
       ██    ██    ██      ██
  ███████    ██    ███████ ██
""").strip()

_LOGO_MIN_WIDTH = 98  # Minimum terminal width for the wide BlurVision logo


def _pick_logo() -> str:
    """Return the best logo for the current terminal width."""
    try:
        width = shutil.get_terminal_size((120, 24)).columns
    except Exception:
        width = 120
    if width >= _LOGO_MIN_WIDTH:
        return "\n".join(_LOGO_WIDE_LINES)
    return _LOGO_NARROW

# ---- Splash mottos (randomly picked each launch) ----------------------------

_MOTTOS = [
    "Because Gradio is the spawn of Satan.",
    "Sidestepping the spaghetti code.",
    "Bypassing the BS, one epoch at a time.",
    "Research grade? No. dernet grade.",
    "Nimrod-tested. Blackwell-approved.",
    "The 5-Euro Heist.",
    "Je suis calibré.",
    "Born in the VRAM trenches.",
    "323k tokens later, we have a snare.",
    "Designed by a Producer. Debugged by a Nimrod.",
    "Because Gradio is the spawn of Satan.",
    "Talk to an LLM for 10h? Hell yeah.",
    "Side-Step: The 17-Hour Speedrun.",
    "Red errors are just decoration.",
    "Importing sanity... ModuleNotFoundError.",
    "One variable, two names, zero documentation.",
    "Because Gradio is the spawn of Satan.",
    "Refactoring the Prometheus experience.",
    "Surgical training for blunt-force code.",
    "2,500 lines of 'Why?'",
    "The browser tab is not the boss of me.",
    "1.5 Terabytes of RAM and still no documentation.",
    "The only way to debug a 2000-line error is to write a 2000-line error.",
]


def _pick_motto() -> str:
    return random.choice(_MOTTOS)


def _get_versions() -> dict:
    """Collect framework version strings (best-effort)."""
    info: dict = {}
    try:
        import torch
        info["PyTorch"] = torch.__version__
        if torch.cuda.is_available():
            info["CUDA"] = torch.version.cuda or "n/a"
    except ImportError:
        info["PyTorch"] = "not installed"
    try:
        info["Python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    except Exception:
        pass
    return info


def _get_gpu_line(device: str = "", precision: str = "") -> str:
    """One-liner for GPU name + VRAM."""
    try:
        from acestep.training_v2.gpu_utils import detect_gpu
        gpu = detect_gpu(requested_device=device or "auto", requested_precision=precision or "auto")
        vram_part = ""
        if gpu.vram_total_mb is not None:
            vram_gb = gpu.vram_total_mb / 1024
            vram_part = f"  ({vram_gb:.1f} GiB)"
        return f"{gpu.name}{vram_part}"
    except Exception:
        return "unknown"


# ---- Public API -------------------------------------------------------------

def show_banner(
    subcommand: str,
    device: str = "",
    precision: str = "",
    extra_lines: Optional[list] = None,
) -> None:
    """Print the startup banner with a random motto."""
    versions = _get_versions()
    gpu_line = _get_gpu_line(device, precision)
    motto = _pick_motto()

    ver_parts = []
    if "Python" in versions:
        ver_parts.append(f"Python {versions['Python']}")
    if "PyTorch" in versions:
        ver_parts.append(f"PyTorch {versions['PyTorch']}")
    if "CUDA" in versions:
        ver_parts.append(f"CUDA {versions['CUDA']}")
    if precision:
        ver_parts.append(precision)
    ver_str = " | ".join(ver_parts)

    from acestep.training_v2 import __version__ as SIDESTEP_VERSION

    _SUBCOMMAND_DESC = {
        "vanilla": "vanilla (original behaviour, bugged timesteps)",
        "fixed": "fixed (corrected timesteps + CFG dropout)",
        "estimate": "estimate (gradient sensitivity analysis)",
    }
    sub_desc = _SUBCOMMAND_DESC.get(subcommand, subcommand)

    if is_rich_active() and console is not None:
        from rich.panel import Panel
        from rich.text import Text

        logo = _pick_logo()
        body = Text()
        body.append(logo + "\n", style="bold cyan")
        body.append(f'  "{motto}"\n\n', style="italic yellow")
        body.append(f"  Side-Step v{SIDESTEP_VERSION} -- Adapter Fine-Tuning CLI (LoRA + LoKR)\n", style="dim")
        body.append("  Standalone: github.com/koda-dernet/Side-Step\n\n", style="dim italic")
        body.append("  Mode   : ", style="dim")
        body.append(f"{sub_desc}\n", style="bold")
        body.append("  Stack  : ", style="dim")
        body.append(f"{ver_str}\n", style="")
        body.append("  GPU    : ", style="dim")
        body.append(f"{gpu_line}\n", style="")

        if extra_lines:
            for line in extra_lines:
                body.append(f"  {line}\n", style="dim")

        console.print(Panel(body, border_style="cyan", padding=(0, 1)))
    else:
        # Plain text fallback
        print(_pick_logo(), file=sys.stderr)
        print(f'  "{motto}"', file=sys.stderr)
        print(f"  Side-Step v{SIDESTEP_VERSION} -- Adapter Fine-Tuning CLI (LoRA + LoKR)", file=sys.stderr)
        print("  Standalone: github.com/koda-dernet/Side-Step", file=sys.stderr)
        print(f"  Mode   : {sub_desc}", file=sys.stderr)
        print(f"  Stack  : {ver_str}", file=sys.stderr)
        print(f"  GPU    : {gpu_line}", file=sys.stderr)
        if extra_lines:
            for line in extra_lines:
                print(f"  {line}", file=sys.stderr)
        print(file=sys.stderr)
