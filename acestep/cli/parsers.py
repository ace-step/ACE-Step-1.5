"""Parsing utilities for CLI input processing, extracted from cli.py."""

import ast
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple


def _parse_description_hints(description: str) -> tuple[Optional[str], bool]:
    import re

    if not description:
        return None, False

    description_lower = description.lower().strip()

    language_mapping = {
        'english': 'en', 'en': 'en',
        'chinese': 'zh', '中文': 'zh', 'zh': 'zh', 'mandarin': 'zh',
        'japanese': 'ja', '日本語': 'ja', 'ja': 'ja',
        'korean': 'ko', '한국어': 'ko', 'ko': 'ko',
        'spanish': 'es', 'español': 'es', 'es': 'es',
        'french': 'fr', 'français': 'fr', 'fr': 'fr',
        'german': 'de', 'deutsch': 'de', 'de': 'de',
        'italian': 'it', 'italiano': 'it', 'it': 'it',
        'portuguese': 'pt', 'português': 'pt', 'pt': 'pt',
        'russian': 'ru', 'русский': 'ru', 'ru': 'ru',
        'bengali': 'bn', 'bn': 'bn',
        'hindi': 'hi', 'hi': 'hi',
        'arabic': 'ar', 'ar': 'ar',
        'thai': 'th', 'th': 'th',
        'vietnamese': 'vi', 'vi': 'vi',
        'indonesian': 'id', 'id': 'id',
        'turkish': 'tr', 'tr': 'tr',
        'dutch': 'nl', 'nl': 'nl',
        'polish': 'pl', 'pl': 'pl',
    }

    detected_language = None
    for lang_name, lang_code in language_mapping.items():
        if len(lang_name) <= 2:
            pattern = r'(?:^|\s|[.,;:!?])' + re.escape(lang_name) + r'(?:$|\s|[.,;:!?])'
        else:
            pattern = r'\b' + re.escape(lang_name) + r'\b'
        if re.search(pattern, description_lower):
            detected_language = lang_code
            break

    is_instrumental = False
    if 'instrumental' in description_lower:
        is_instrumental = True
    elif 'pure music' in description_lower or 'pure instrument' in description_lower:
        is_instrumental = True
    elif description_lower.endswith(' solo') or description_lower == 'solo':
        is_instrumental = True

    return detected_language, is_instrumental


def _extract_caption_lyrics_from_formatted_prompt(formatted_prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort extraction of caption/lyrics from a formatted prompt string."""
    matches = list(re.finditer(r"# Caption\n(.*?)\n+# Lyric\n(.*)", formatted_prompt, re.DOTALL))
    if not matches:
        return None, None

    caption = matches[-1].group(1).strip()
    lyrics = matches[-1].group(2)

    # Trim lyrics if chat-template markers appear after the user message.
    cut_markers = ["<|eot_id|>", "<|start_header_id|>", "<|assistant|>", "<|user|>", "<|system|>", "<|im_end|>", "<|im_start|>"]
    cut_at = len(lyrics)
    for marker in cut_markers:
        pos = lyrics.find(marker)
        if pos != -1:
            cut_at = min(cut_at, pos)
    lyrics = lyrics[:cut_at].rstrip()

    return caption or None, lyrics or None


def _extract_instruction_from_formatted_prompt(formatted_prompt: str) -> Optional[str]:
    """Best-effort extraction of instruction text from a formatted prompt string."""
    match = re.search(r"# Instruction\n(.*?)\n\n", formatted_prompt, re.DOTALL)
    if not match:
        return None
    instruction = match.group(1).strip()
    return instruction or None


def _extract_cot_metadata_from_formatted_prompt(formatted_prompt: str) -> dict:
    """Best-effort extraction of COT metadata from a formatted prompt string,
    supporting multi-line values.
    """
    matches = list(re.finditer(r"<think>\n(.*?)\n</think>", formatted_prompt, re.DOTALL))
    if not matches:
        return {}
    block = matches[-1].group(1)
    metadata = {}
    current_key = None
    current_value_lines = []

    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue

        key_match = re.match(r"^(\w+):\s*(.*)", line)
        if key_match:
            if current_key:
                metadata[current_key] = " ".join(current_value_lines).strip()

            current_key = key_match.group(1).strip().lower()
            current_value_lines = [key_match.group(2).strip()]
        else:
            if current_key:
                current_value_lines.append(line)

    if current_key and current_value_lines:
        metadata[current_key] = " ".join(current_value_lines).strip()

    return metadata


def _parse_number(value: str) -> Optional[float]:
    try:
        match = re.search(r"[-+]?\d*\.?\d+", value)
        if not match:
            return None
        return float(match.group(0))
    except Exception:
        return None


def _parse_timesteps_input(value) -> Optional[List[float]]:
    if value is None:
        return None
    if isinstance(value, list):
        if all(isinstance(t, (int, float)) for t in value):
            return [float(t) for t in value]
        return None
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("[") or raw.startswith("("):
        try:
            parsed = ast.literal_eval(raw)
        except Exception:
            return None
        if isinstance(parsed, list) and all(isinstance(t, (int, float)) for t in parsed):
            return [float(t) for t in parsed]
        return None
    try:
        return [float(t.strip()) for t in raw.split(",") if t.strip()]
    except Exception:
        return None


def _expand_audio_path(path_str: Optional[str]) -> Optional[str]:
    if not path_str or not isinstance(path_str, str):
        return path_str
    try:
        return Path(path_str).expanduser().resolve(strict=False).as_posix()
    except Exception:
        return Path(path_str).expanduser().absolute().as_posix()


def _parse_bool(value: str) -> bool:
    return str(value).lower() in {"true", "1", "yes", "y"}
