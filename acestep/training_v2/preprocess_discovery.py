"""
Audio file discovery and metadata loading for preprocessing.

Reads both per-sample metadata and dataset-level metadata (``tag_position``,
``genre_ratio``, default ``custom_tag``) from ACE-Step's JSON format.

Extracted from ``preprocess.py`` to keep that module under the LOC limit.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Supported audio extensions (same as upstream)
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a"}


def discover_audio_files(
    audio_dir: Optional[str],
    dataset_json: Optional[str],
) -> List[Path]:
    """Discover audio files from a dataset JSON or by scanning a directory.

    Resolution order:

    1. If *dataset_json* is provided, extract ``audio_path`` (or fall back
       to ``filename``) from each entry.  Missing files are skipped with a
       warning.
    2. Otherwise, recursively scan *audio_dir* for supported audio
       extensions (``AUDIO_EXTENSIONS``).
    """
    # -- JSON-driven discovery ----------------------------------------------
    if dataset_json and Path(dataset_json).is_file():
        try:
            raw = json.loads(Path(dataset_json).read_text(encoding="utf-8"))
            samples = raw if isinstance(raw, list) else raw.get("samples", [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("[Side-Step] Failed to read dataset JSON: %s", exc)
            samples = []

        audio_files: List[Path] = []
        json_dir = Path(dataset_json).parent  # resolve relative paths vs JSON
        for entry in samples:
            ap = entry.get("audio_path") or entry.get("filename", "")
            if not ap:
                continue
            p = Path(ap)
            if not p.is_absolute():
                p = json_dir / p
            if p.is_file():
                audio_files.append(p)
            else:
                logger.warning("[Side-Step] Audio file from JSON not found: %s", p)

        if audio_files:
            logger.info(
                "[Side-Step] Resolved %d audio files from dataset JSON", len(audio_files),
            )
            return sorted(audio_files)
        else:
            logger.warning(
                "[Side-Step] Dataset JSON contained no resolvable audio paths; "
                "falling back to directory scan"
            )

    # -- Recursive directory scan -------------------------------------------
    if not audio_dir:
        return []

    source_path = Path(audio_dir)
    if not source_path.is_dir():
        logger.warning("[Side-Step] Audio directory does not exist: %s", audio_dir)
        return []

    audio_files = sorted(
        f for f in source_path.rglob("*")
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    )
    if audio_files:
        logger.info(
            "[Side-Step] Found %d audio files (recursive scan of %s)",
            len(audio_files), audio_dir,
        )
    return audio_files


def load_sample_metadata(
    dataset_json: Optional[str],
    audio_files: List[Path],
) -> Dict[str, Dict[str, Any]]:
    """Build a filename -> metadata mapping.

    If *dataset_json* is provided, load it and index by filename.
    Falls back to basename of ``audio_path`` when ``filename`` is missing.
    Otherwise return defaults for every audio file.
    """
    meta: Dict[str, Dict[str, Any]] = {}

    if dataset_json and Path(dataset_json).is_file():
        try:
            raw = json.loads(Path(dataset_json).read_text(encoding="utf-8"))
            samples = raw if isinstance(raw, list) else raw.get("samples", [])
            for s in samples:
                # Primary key: explicit filename field
                fname = s.get("filename", "")
                if fname:
                    meta[fname] = s
                    # Also index by basename if filename contains a path
                    basename = Path(fname).name
                    if basename != fname and basename not in meta:
                        meta[basename] = s
                elif s.get("audio_path"):
                    # Fallback: derive key from audio_path basename
                    basename = Path(s["audio_path"]).name
                    if basename and basename not in meta:
                        meta[basename] = s
            logger.info("[Side-Step] Loaded metadata for %d samples from %s", len(meta), dataset_json)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("[Side-Step] Failed to load dataset JSON: %s", exc)

    # Fill defaults for any audio file without metadata
    for af in audio_files:
        if af.name not in meta:
            meta[af.name] = {
                "filename": af.name,
                "caption": af.stem.replace("_", " ").replace("-", " "),
                "lyrics": "[Instrumental]",
                "genre": "",
                "bpm": None,
                "keyscale": "",
                "timesignature": "",
                "duration": 0,
                "is_instrumental": True,
            }

    return meta


def load_dataset_metadata(dataset_json: Optional[str]) -> Dict[str, Any]:
    """Load the top-level ``metadata`` block from an ACE-Step dataset JSON.

    Returns a dict with the dataset-level settings that affect prompt
    construction:

    - ``tag_position`` (str): ``"prepend"``, ``"append"``, or ``"replace"``.
    - ``genre_ratio`` (int): 0-100, percentage of samples using genre.
    - ``custom_tag`` (str): default trigger word applied to all samples.

    Returns safe defaults when the JSON has no metadata block or is absent.
    """
    defaults: Dict[str, Any] = {
        "tag_position": "prepend",
        "genre_ratio": 0,
        "custom_tag": "",
    }
    if not dataset_json or not Path(dataset_json).is_file():
        return defaults

    try:
        raw = json.loads(Path(dataset_json).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return defaults

    if not isinstance(raw, dict) or "metadata" not in raw:
        return defaults

    meta = raw["metadata"]
    return {
        "tag_position": meta.get("tag_position", "prepend"),
        "genre_ratio": meta.get("genre_ratio", 0),
        "custom_tag": meta.get("custom_tag", ""),
    }


def select_genre_indices(num_samples: int, genre_ratio: int) -> Set[int]:
    """Select sample indices that should use genre instead of caption.

    Mirrors upstream ``select_genre_indices()`` from ACE-Step's
    ``preprocess_utils.py``.  Uses a fixed seed so the selection is
    deterministic and reproducible across runs.

    Args:
        num_samples: Total number of samples.
        genre_ratio: 0-100, percentage of samples that use genre.

    Returns:
        Set of sample indices that should use genre.
    """
    if genre_ratio <= 0 or num_samples <= 0:
        return set()
    num_genre = int(num_samples * genre_ratio / 100)
    rng = random.Random(42)
    indices = list(range(num_samples))
    rng.shuffle(indices)
    return set(indices[:num_genre])
