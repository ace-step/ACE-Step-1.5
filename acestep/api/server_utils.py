"""Shared helper utilities used by API server request and runtime flows."""

from __future__ import annotations

import os
import re
from typing import Optional


STATUS_MAP = {"queued": 0, "running": 0, "succeeded": 1, "failed": 2}


def parse_description_hints(description: str) -> tuple[Optional[str], bool]:
    """Parse language and instrumental hints from free-form description text.

    Args:
        description: User free-form sample description.

    Returns:
        Tuple of ``(language_code, is_instrumental)``.
    """

    if not description:
        return None, False

    description_lower = description.lower().strip()

    language_mapping = {
        "english": "en",
        "en": "en",
        "chinese": "zh",
        "中文": "zh",
        "zh": "zh",
        "mandarin": "zh",
        "japanese": "ja",
        "日本語": "ja",
        "ja": "ja",
        "korean": "ko",
        "한국어": "ko",
        "ko": "ko",
        "spanish": "es",
        "español": "es",
        "es": "es",
        "french": "fr",
        "français": "fr",
        "fr": "fr",
        "german": "de",
        "deutsch": "de",
        "de": "de",
        "italian": "it",
        "italiano": "it",
        "it": "it",
        "portuguese": "pt",
        "português": "pt",
        "pt": "pt",
        "russian": "ru",
        "русский": "ru",
        "ru": "ru",
        "bengali": "bn",
        "bn": "bn",
        "hindi": "hi",
        "hi": "hi",
        "arabic": "ar",
        "ar": "ar",
        "thai": "th",
        "th": "th",
        "vietnamese": "vi",
        "vi": "vi",
        "indonesian": "id",
        "id": "id",
        "turkish": "tr",
        "tr": "tr",
        "dutch": "nl",
        "nl": "nl",
        "polish": "pl",
        "pl": "pl",
    }

    detected_language = None
    for lang_name, lang_code in language_mapping.items():
        if len(lang_name) <= 2:
            pattern = r"(?:^|\s|[.,;:!?])" + re.escape(lang_name) + r"(?:$|\s|[.,;:!?])"
        else:
            pattern = r"\b" + re.escape(lang_name) + r"\b"
        if re.search(pattern, description_lower):
            detected_language = lang_code
            break

    is_instrumental = False
    if "instrumental" in description_lower:
        is_instrumental = True
    elif "pure music" in description_lower or "pure instrument" in description_lower:
        is_instrumental = True
    elif description_lower.endswith(" solo") or description_lower == "solo":
        is_instrumental = True

    return detected_language, is_instrumental


def env_bool(name: str, default: bool) -> bool:
    """Read boolean environment variable with legacy truthy semantics."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_model_name(config_path: str) -> str:
    """Extract model name from config path."""

    if not config_path:
        return ""
    normalized = config_path.rstrip("/\\")
    return os.path.basename(normalized)


def map_status(status: str) -> int:
    """Map textual job status to integer API status code."""

    return STATUS_MAP.get(status, 2)


def parse_timesteps(value: Optional[str]) -> Optional[list[float]]:
    """Parse comma-separated timesteps into float list."""

    if not value or not value.strip():
        return None
    try:
        return [float(item.strip()) for item in value.split(",") if item.strip()]
    except (ValueError, Exception):
        return None


def is_instrumental(lyrics: str) -> bool:
    """Return whether lyrics indicate instrumental output."""

    if not lyrics:
        return True
    lyrics_clean = lyrics.strip().lower()
    if not lyrics_clean:
        return True
    return lyrics_clean in ("[inst]", "[instrumental]")
