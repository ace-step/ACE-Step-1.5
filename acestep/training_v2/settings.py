"""
Persistent user settings for Side-Step.

Stored as JSON at a platform-aware location:

    Linux/macOS:  ``~/.config/sidestep/settings.json``
    Windows:      ``%APPDATA%\\sidestep\\settings.json``

Settings hold environment paths (checkpoint directory, ACE-Step install
location) and flags (vanilla intent, first-run state).  They are *not*
training hyperparameters -- those live in presets.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Current schema version -- bump when adding/renaming keys.
_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def settings_dir() -> Path:
    """Platform-aware root config directory for Side-Step."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    return base / "sidestep"


def settings_path() -> Path:
    """Full path to the settings JSON file."""
    return settings_dir() / "settings.json"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def _default_settings() -> Dict[str, Any]:
    """Return a blank settings dict with the current schema version."""
    return {
        "version": _SCHEMA_VERSION,
        "checkpoint_dir": None,
        "vanilla_enabled": False,
        "first_run_complete": False,
    }


def load_settings() -> Optional[Dict[str, Any]]:
    """Load settings from disk.

    Returns ``None`` if the file does not exist or cannot be parsed.
    Performs lightweight schema migration when the on-disk version is
    older than ``_SCHEMA_VERSION``.
    """
    p = settings_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read settings: %s", exc)
        return None

    # Schema migration: fill missing keys from defaults
    defaults = _default_settings()
    for key, val in defaults.items():
        data.setdefault(key, val)
    data["version"] = _SCHEMA_VERSION
    return data


def save_settings(data: Dict[str, Any]) -> None:
    """Write settings to disk, creating parent directories as needed."""
    data["version"] = _SCHEMA_VERSION
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.debug("Settings saved to %s", p)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def is_first_run() -> bool:
    """Return ``True`` if settings do not exist or setup was never completed."""
    data = load_settings()
    if data is None:
        return True
    return not data.get("first_run_complete", False)


def get_checkpoint_dir() -> Optional[str]:
    """Return the stored checkpoint directory, or ``None``."""
    data = load_settings()
    if data is None:
        return None
    return data.get("checkpoint_dir")


