"""
Model discovery and selection for Side-Step.

Scans a checkpoint directory for model subdirectories (identified by the
presence of a ``config.json``), classifies them as official or custom
(fine-tune), and provides an interactive fuzzy-search picker.
"""

from __future__ import annotations

import difflib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Official ACE-Step model directory name patterns.
_OFFICIAL_PREFIXES = ("acestep-v15-", "acestep-v1-")

# Known base-model fingerprints: (is_turbo, timestep_mu approx range).
_BASE_DEFAULTS: Dict[str, Dict] = {
    "turbo": {"is_turbo": True, "timestep_mu": -0.4, "timestep_sigma": 1.0, "shift": 3.0, "num_inference_steps": 8},
    "base":  {"is_turbo": False, "timestep_mu": -0.4, "timestep_sigma": 1.0, "shift": 1.0, "num_inference_steps": 50},
    "sft":   {"is_turbo": False, "timestep_mu": -0.4, "timestep_sigma": 1.0, "shift": 1.0, "num_inference_steps": 50},
}


@dataclass
class ModelInfo:
    """Metadata about a discovered model directory."""

    name: str
    path: Path
    is_official: bool
    config: Dict = field(default_factory=dict)
    base_model: str = "unknown"


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_models(checkpoint_dir: str | Path) -> List[ModelInfo]:
    """Scan *checkpoint_dir* for model subdirectories.

    A valid model directory contains a ``config.json`` with either an
    ``auto_map`` key (HuggingFace custom model) or a ``model_type`` key.
    Non-model directories (``vae/``, ``Qwen3-*``, ``*.lm-*``) are
    excluded automatically.

    Returns a sorted list of :class:`ModelInfo` (officials first, then
    alphabetical).
    """
    ckpt = Path(checkpoint_dir)
    if not ckpt.is_dir():
        return []

    skip_names = {"vae", ".git", "__pycache__"}
    skip_prefixes = ("Qwen", "acestep-5Hz")

    results: List[ModelInfo] = []
    for child in sorted(ckpt.iterdir()):
        if not child.is_dir():
            continue
        if child.name in skip_names:
            continue
        if any(child.name.startswith(p) for p in skip_prefixes):
            continue

        cfg_path = child / "config.json"
        if not cfg_path.is_file():
            continue

        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # Must look like a model config (not just any JSON)
        if "auto_map" not in cfg and "model_type" not in cfg:
            continue

        is_official = any(child.name.startswith(p) for p in _OFFICIAL_PREFIXES)
        base = detect_base_model(cfg, child.name)

        results.append(ModelInfo(
            name=child.name,
            path=child,
            is_official=is_official,
            config=cfg,
            base_model=base,
        ))

    # Sort: officials first, then alphabetical
    results.sort(key=lambda m: (not m.is_official, m.name))
    return results


# ---------------------------------------------------------------------------
# Base-model detection
# ---------------------------------------------------------------------------

def detect_base_model(config: Dict, dir_name: str = "") -> str:
    """Infer which base variant a model descends from.

    Uses ``is_turbo`` flag and directory name heuristics.  Returns one
    of ``"turbo"``, ``"base"``, ``"sft"``, or ``"unknown"``.
    """
    # Explicit is_turbo flag
    if config.get("is_turbo", False):
        return "turbo"

    # Match by directory name for official models
    name_lower = dir_name.lower()
    for variant in ("turbo", "base", "sft"):
        if variant in name_lower:
            return variant

    return "unknown"


def get_base_defaults(base_model: str) -> Dict:
    """Return default timestep params for a known base variant."""
    return dict(_BASE_DEFAULTS.get(base_model, _BASE_DEFAULTS["base"]))


# ---------------------------------------------------------------------------
# Fuzzy search
# ---------------------------------------------------------------------------

def fuzzy_search(query: str, models: List[ModelInfo]) -> List[ModelInfo]:
    """Filter models by fuzzy name match.

    Tries substring match first, then ``difflib.get_close_matches``.
    Returns matching models in relevance order.
    """
    if not query:
        return list(models)

    q = query.lower()

    # 1. Substring matches (most intuitive)
    substring_hits = [m for m in models if q in m.name.lower()]
    if substring_hits:
        return substring_hits

    # 2. Fuzzy matches via difflib
    names = [m.name for m in models]
    close = difflib.get_close_matches(query, names, n=5, cutoff=0.4)
    name_set = set(close)
    return [m for m in models if m.name in name_set]


# ---------------------------------------------------------------------------
# Interactive picker
# ---------------------------------------------------------------------------

def pick_model(
    checkpoint_dir: str | Path,
) -> Optional[Tuple[str, ModelInfo]]:
    """Interactive model selector with fuzzy search.

    Scans *checkpoint_dir*, lists all discovered models, and lets the
    user pick by number or type a name to search.

    Returns ``(model_name, ModelInfo)`` or ``None`` if no models found.

    Raises:
        GoBack: When user types 'b'/'back'.
    """
    from acestep.training_v2.ui import console, is_rich_active
    from acestep.training_v2.ui.prompt_helpers import GoBack, menu, ask

    models = scan_models(checkpoint_dir)
    if not models:
        return None

    # Build menu options
    options = []
    for m in models:
        tag = "(official)" if m.is_official else f"(custom, base: {m.base_model})"
        options.append((m.name, f"{m.name}  {tag}"))

    # Add search option at the end
    options.append(("__search__", "Search by name..."))

    choice = menu(
        "Select a model to train on",
        options,
        default=1,
        allow_back=True,
    )

    if choice == "__search__":
        return _search_loop(models)

    # Find the matching model
    for m in models:
        if m.name == choice:
            return (m.name, m)

    return None


def _search_loop(models: List[ModelInfo]) -> Optional[Tuple[str, ModelInfo]]:
    """Fuzzy-search sub-flow for model selection."""
    from acestep.training_v2.ui import console, is_rich_active
    from acestep.training_v2.ui.prompt_helpers import GoBack, ask, menu

    while True:
        query = ask("Enter model name (or part of it)", allow_back=True)
        hits = fuzzy_search(query, models)

        if not hits:
            _msg = "  No matches found. Try a different search term."
            if is_rich_active() and console is not None:
                console.print(f"  [yellow]{_msg}[/]")
            else:
                print(_msg)
            continue

        if len(hits) == 1:
            return (hits[0].name, hits[0])

        options = []
        for m in hits:
            tag = "(official)" if m.is_official else f"(custom, base: {m.base_model})"
            options.append((m.name, f"{m.name}  {tag}"))

        choice = menu("Multiple matches -- pick one", options, default=1, allow_back=True)
        for m in hits:
            if m.name == choice:
                return (m.name, m)


def prompt_base_model(model_name: str) -> str:
    """Ask the user which base model a fine-tune descends from.

    Returns ``"turbo"``, ``"base"``, or ``"sft"``.
    """
    from acestep.training_v2.ui import console, is_rich_active
    from acestep.training_v2.ui.prompt_helpers import menu

    from acestep.training_v2.ui.prompt_helpers import _esc

    if is_rich_active() and console is not None:
        console.print(
            f"\n  [yellow]'{_esc(model_name)}' appears to be a custom fine-tune.[/]"
        )
        console.print(
            "  [dim]Knowing the base model helps condition timestep sampling.[/]\n"
        )
    else:
        print(f"\n  '{model_name}' appears to be a custom fine-tune.")
        print("  Knowing the base model helps condition timestep sampling.\n")

    return menu(
        "Which base model was this fine-tune trained from?",
        [
            ("turbo", "Turbo (8-step accelerated)"),
            ("base", "Base (full diffusion)"),
            ("sft", "SFT (supervised fine-tune)"),
        ],
        default=1,
        allow_back=True,
    )
