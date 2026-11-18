"""Pure planning helpers for the instrumental studio.

These decide output quality, folder names, and how many tracks can be
generated together. They do not load models.
"""

from __future__ import annotations

import re
import unicodedata

QUALITY_PRESETS = {
    "high": {
        "label": "High — 32-bit WAV and 320 kbps MP3",
        "wav_format": "wav32",
        "wav_ext": "wav",
        "mp3_bitrate": "320k",
        "mp3_sample_rate": 48000,
    },
    "standard": {
        "label": "Standard — 16-bit WAV and 256 kbps MP3",
        "wav_format": "wav",
        "wav_ext": "wav",
        "mp3_bitrate": "256k",
        "mp3_sample_rate": 48000,
    },
    "compact": {
        "label": "Compact — 16-bit WAV and 192 kbps MP3",
        "wav_format": "wav",
        "wav_ext": "wav",
        "mp3_bitrate": "192k",
        "mp3_sample_rate": 48000,
    },
}

DEFAULT_QUALITY = "high"
MAX_TRACKS = 10

# Words that do not help someone recognize a batch later.
_FOLDER_SKIP = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "instrumental",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def normalize_quality(name: str | None) -> str:
    """Return a known quality preset name. Unknown values use the high default."""
    key = (name or "").strip().lower()
    if key in QUALITY_PRESETS:
        return key
    return DEFAULT_QUALITY


def folder_name_for_prompt(prompt: str, max_words: int = 6) -> str:
    """Turn a prompt into a short folder name.

    Uses the opening sentence, keeps the distinctive words, and drops
    characters Windows cannot put in a path.
    """
    text = unicodedata.normalize("NFKD", prompt or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    sentence = re.split(r"[.!?]", text, maxsplit=1)[0]
    words = re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", sentence)
    chosen: list[str] = []
    for word in words:
        token = word.lower()
        if token in _FOLDER_SKIP:
            continue
        chosen.append(token)
        if len(chosen) >= max_words:
            break
    slug = "-".join(chosen).strip("-")
    return slug[:48].rstrip("-") or "track"


def instrumental_caption(prompt: str) -> str:
    """Keep the user's prompt and state that the piece has no vocals."""
    text = " ".join((prompt or "").split())
    if not text:
        raise ValueError("Enter a music prompt.")
    return f"Instrumental music with no vocals and no singing. {text}"


def choose_parallel_batch(free_gb: float, requested: int, is_xl: bool) -> int:
    """Pick how many tracks to generate at once from free GPU memory.

    XL weights leave less room for extra tracks, so the cap is lower.
    One track is always safe.
    """
    count = max(1, min(int(requested), MAX_TRACKS))
    per_track = 3.0 if is_xl else 1.5
    cap = 2 if is_xl else 4
    if free_gb <= 0:
        return 1
    fit = int(free_gb // per_track)
    return max(1, min(count, fit, cap))
