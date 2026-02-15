"""
Preset save/load/manage logic for Side-Step wizard.

Presets are named JSON files containing training hyperparameters (but not
paths, device settings, or model-derived timestep params).  They live in:

    Built-in:  ``<package>/training_v2/presets/``   (shipped, read-only)
    Local:     ``./presets/``                       (project-local, primary)
    Global:    ``~/.config/sidestep/presets/``      (user-global, fallback)

New user presets are saved to the **local** directory (``./presets/`` in
the current working directory).  This keeps presets visible, portable,
and persistent across Docker container restarts.

The preset schema uses wizard field names for readability.  Unknown keys
are silently ignored on load; missing keys fall back to defaults.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


# ---- Directories ------------------------------------------------------------

def _find_project_root() -> Optional[Path]:
    """Locate the Side-Step project root directory.

    Searches CWD, the script's own directory (``sys.argv[0]``), and
    ancestors of CWD for a directory containing both ``pyproject.toml``
    and the ``acestep/`` package.  This makes preset discovery work
    regardless of the working directory -- important on Windows where
    batch files and shortcuts may not set CWD to the project root.

    Returns ``None`` if the project root cannot be determined.
    """
    import sys as _sys

    def _is_root(p: Path) -> bool:
        return (p / "train.py").is_file() or (
            (p / "pyproject.toml").is_file() and (p / "acestep").is_dir()
        )

    # 1. CWD (most common -- users are told to cd into the project)
    cwd = Path.cwd()
    if _is_root(cwd):
        return cwd

    # 2. Script directory (handles shortcuts, batch files, uv run, etc.)
    if _sys.argv:
        try:
            script_dir = Path(_sys.argv[0]).resolve().parent
            if _is_root(script_dir):
                return script_dir
        except (OSError, ValueError):
            pass

    # 3. Walk up from CWD (user ran from a subdirectory)
    for parent in cwd.parents:
        if _is_root(parent):
            return parent

    return None


def _local_presets_dir() -> Path:
    """Project-local user presets directory.

    Anchored to the Side-Step project root rather than raw ``Path.cwd()``
    so that presets are always found regardless of the working directory.
    Falls back to ``CWD/presets/`` if the project root cannot be located.
    """
    root = _find_project_root()
    if root is not None:
        return root / "presets"
    return Path.cwd() / "presets"


def _global_presets_dir() -> Path:
    """Platform-aware global user presets directory (fallback).

    Used as a secondary scan location so that presets saved before the
    local-directory change are still found.
    """
    import os
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    return base / "sidestep" / "presets"


def _builtin_presets_dir() -> Path:
    """Shipped built-in presets directory."""
    return Path(__file__).resolve().parent.parent / "presets"


# ---- Fields that belong in a preset ----------------------------------------

PRESET_FIELDS = frozenset([
    # Adapter selection
    "adapter_type",
    # LoRA settings
    "rank", "alpha", "dropout", "target_modules_str", "attention_type", "bias",
    # LoKR settings
    "lokr_linear_dim", "lokr_linear_alpha", "lokr_factor",
    "lokr_decompose_both", "lokr_use_tucker", "lokr_use_scalar",
    "lokr_weight_decompose",
    # Training settings
    "learning_rate", "batch_size", "gradient_accumulation", "epochs",
    "warmup_steps", "weight_decay", "max_grad_norm", "seed",
    "shift", "num_inference_steps",
    "optimizer_type", "scheduler_type", "cfg_ratio",
    "save_every", "log_every", "log_heavy_every",
    "gradient_checkpointing", "offload_encoder",
    "sample_every_n_epochs",
])

# ---- Max file size for import validation ------------------------------------
_MAX_PRESET_BYTES = 1_000_000  # 1 MB

# Characters forbidden in preset names (filesystem-safe on all platforms)
_UNSAFE_CHARS = set('/\\:*?"<>|')

# Windows reserved filenames -- cannot be used even with an extension.
# See https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def _sanitize_name(name: str) -> str:
    """Sanitize a preset name to be a safe filename stem.

    Strips whitespace, replaces spaces with underscores, removes unsafe
    characters, rejects path traversal attempts, and blocks Windows
    reserved filenames (CON, NUL, COM1, etc.).
    """
    name = name.strip()
    if not name:
        raise ValueError("Preset name cannot be empty")
    # Block path traversal
    if ".." in name or name.startswith("/") or name.startswith("\\"):
        raise ValueError(f"Invalid preset name: {name!r}")
    # Remove unsafe characters and replace spaces
    cleaned = "".join(c if c not in _UNSAFE_CHARS else "" for c in name)
    cleaned = cleaned.replace(" ", "_")
    if not cleaned:
        raise ValueError(f"Preset name contains only special characters: {name!r}")
    # Block Windows reserved filenames (case-insensitive)
    if cleaned.upper() in _WINDOWS_RESERVED:
        raise ValueError(
            f"Preset name {cleaned!r} is a reserved filename on Windows"
        )
    return cleaned


# ---- Core operations --------------------------------------------------------

def list_presets() -> List[Dict[str, Any]]:
    """Return all available presets (built-in, then local, then global).

    Each entry is ``{"name", "description", "path", "builtin"}``.
    User presets (local or global) with the same name as a built-in
    override the built-in.  Local presets override global ones.
    Logs scan directories at DEBUG level for troubleshooting.
    """
    presets: List[Dict[str, Any]] = []
    seen_names: set[str] = set()

    local_dir = _local_presets_dir()
    global_dir = _global_presets_dir()
    builtin_dir = _builtin_presets_dir()
    logger.debug(
        "Scanning presets: local=%s  global=%s  builtin=%s",
        local_dir, global_dir, builtin_dir,
    )

    # Scan in priority order: local > global > built-in.
    # First-seen name wins, so local overrides global which overrides built-in.
    scan_order = [
        (local_dir, False),
        (global_dir, False),
        (builtin_dir, True),
    ]

    for directory, builtin in scan_order:
        if not directory.is_dir():
            logger.debug("  %s: not found, skipping", directory)
            continue
        found = list(sorted(directory.glob("*.json")))
        logger.debug("  %s: found %d preset(s)", directory, len(found))
        for fp in found:
            name = fp.stem
            if name in seen_names:
                continue  # higher-priority version already listed
            seen_names.add(name)
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                desc = data.get("description", "")
            except (json.JSONDecodeError, OSError):
                desc = "(unreadable)"
            presets.append({
                "name": name,
                "description": desc,
                "path": str(fp),
                "builtin": builtin,
            })

    return presets


def load_preset(name: str) -> Optional[Dict[str, Any]]:
    """Load a preset by name and return the answers dict.

    Search order: local -> global -> built-in.
    Returns None if not found or if the name is invalid.
    """
    try:
        sanitized = _sanitize_name(name)
    except ValueError:
        logger.warning("Invalid preset name: %r", name)
        return None

    for directory in [_local_presets_dir(), _global_presets_dir(), _builtin_presets_dir()]:
        fp = directory / f"{sanitized}.json"
        if fp.is_file():
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load preset %s: %s", fp, exc)
                return None
            # Filter to known preset fields only
            return {k: v for k, v in data.items() if k in PRESET_FIELDS}

    return None


def save_preset(name: str, description: str, answers: Dict[str, Any]) -> Path:
    """Save a preset to the project-local presets directory.

    Presets are saved to ``./presets/`` (relative to the current working
    directory) so they're visible in the project, portable, and persist
    across Docker container restarts.

    Args:
        name: Preset name (used as filename stem, sanitized).
        description: Human-readable description.
        answers: Full wizard answers dict (filtered to PRESET_FIELDS).

    Returns:
        Path to the saved preset file.

    Raises:
        ValueError: If the name is empty or unsafe.
    """
    safe_name = _sanitize_name(name)
    out_dir = _local_presets_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    data = {"name": safe_name, "description": description}
    data.update({k: v for k, v in answers.items() if k in PRESET_FIELDS})

    fp = out_dir / f"{safe_name}.json"
    fp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return fp


def delete_preset(name: str) -> bool:
    """Delete a user preset.  Cannot delete built-ins.

    Checks local directory first, then global.
    Returns True if deleted, False if not found or built-in.
    """
    try:
        safe_name = _sanitize_name(name)
    except ValueError:
        return False
    for directory in [_local_presets_dir(), _global_presets_dir()]:
        fp = directory / f"{safe_name}.json"
        if fp.is_file():
            fp.unlink()
            return True
    return False


def import_preset(source_path: str) -> Optional[str]:
    """Import a preset from an external JSON file.

    Validates the file before copying.  Returns the preset name on
    success, or None on failure.
    """
    src = Path(source_path)
    if not src.is_file():
        logger.warning("Import source not found: %s", src)
        return None
    if src.stat().st_size > _MAX_PRESET_BYTES:
        logger.warning("Preset file too large (>1MB): %s", src)
        return None

    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("Preset must be a JSON object: %s", src)
            return None
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Invalid preset file %s: %s", src, exc)
        return None

    raw_name = data.get("name", src.stem)
    try:
        name = _sanitize_name(raw_name)
    except ValueError:
        logger.warning("Invalid preset name in %s: %r", src, raw_name)
        return None
    out_dir = _local_presets_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{name}.json"
    shutil.copy2(src, dest)
    return name


def export_preset(name: str, dest_path: str) -> bool:
    """Export a preset to an arbitrary path.

    Returns True on success.
    """
    try:
        safe_name = _sanitize_name(name)
    except ValueError:
        return False
    for directory in [_local_presets_dir(), _global_presets_dir(), _builtin_presets_dir()]:
        fp = directory / f"{safe_name}.json"
        if fp.is_file():
            shutil.copy2(fp, dest_path)
            return True
    return False
