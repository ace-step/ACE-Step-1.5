"""Parse structured LM output into metadata and audio codes.

Extracted from ``LLMHandler.parse_lm_output`` so that parsing logic can
be tested and reused independently of the inference pipeline.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Tuple

from loguru import logger

# Known metadata field keys emitted by the constrained decoder.
_KNOWN_FIELDS = frozenset(
    {"bpm", "caption", "duration", "genres", "keyscale", "language", "timesignature"}
)

# Regex for audio code tokens: <|audio_code_12345|>
_CODE_PATTERN = re.compile(r"<\|audio_code_\d+\|>")

# Ordered list of tag pairs that may wrap the reasoning section.
_REASONING_PATTERNS = [
    re.compile(r"<think>(.*?)</think>", re.DOTALL),
    re.compile(r"<reasoning>(.*?)</reasoning>", re.DOTALL),
]


def _default_postprocess_caption(caption: str) -> str:
    """Fallback caption cleaner when no external one is supplied."""
    if not caption:
        return caption
    return " ".join(line.strip() for line in caption.split("\n") if line.strip())


def parse_lm_output(
    output_text: str,
    postprocess_caption: Optional[Callable[[str], str]] = None,
) -> Tuple[Dict[str, Any], str]:
    """Parse LM output to extract metadata and audio codes.

    Expected format::

        <think>
        bpm: 73
        caption: A calm piano melody
        duration: 273
        genres: Chinese folk
        keyscale: G major
        language: en
        timesignature: 4
        </think>

        <|audio_code_56535|><|audio_code_62918|>...

    Parameters
    ----------
    output_text:
        Raw text produced by the language model.
    postprocess_caption:
        Optional callable applied to the ``caption`` value.  When *None*,
        a simple whitespace-normalising cleaner is used.

    Returns
    -------
    (metadata_dict, audio_codes_string)
    """
    if postprocess_caption is None:
        postprocess_caption = _default_postprocess_caption

    debug_output_text = output_text.split("</think>")[0]
    logger.debug(f"Debug output text: {debug_output_text}")

    metadata: Dict[str, Any] = {}
    audio_codes = ""

    # Extract audio codes -- find all <|audio_code_XXX|> patterns.
    code_matches = _CODE_PATTERN.findall(output_text)
    if code_matches:
        audio_codes = "".join(code_matches)

    # Extract metadata from reasoning section.
    reasoning_text = None
    for pattern in _REASONING_PATTERNS:
        match = pattern.search(output_text)
        if match:
            reasoning_text = match.group(1).strip()
            break

    # If no reasoning tags found, parse metadata from text before audio codes.
    if not reasoning_text:
        lines_before_codes = (
            output_text.split("<|audio_code_")[0]
            if "<|audio_code_" in output_text
            else output_text
        )
        reasoning_text = lines_before_codes.strip()

    # Parse metadata fields with YAML multi-line value support.
    if reasoning_text:
        metadata = _parse_metadata_fields(reasoning_text, postprocess_caption)

    return metadata, audio_codes


def _parse_metadata_fields(
    reasoning_text: str,
    postprocess_caption: Callable[[str], str],
) -> Dict[str, Any]:
    """Parse key-value metadata fields from reasoning text."""
    metadata: Dict[str, Any] = {}
    lines = reasoning_text.split("\n")
    current_key: Optional[str] = None
    current_value_lines: list[str] = []

    def save_current_field() -> None:
        nonlocal current_key, current_value_lines
        if current_key and current_value_lines:
            value = "\n".join(current_value_lines)
            _store_field(metadata, current_key, value, postprocess_caption)
        current_key = None
        current_value_lines = []

    for line in lines:
        # Skip tag lines.
        if line.strip().startswith("<"):
            continue

        # New field: no leading whitespace, contains ':'
        if line and not line[0].isspace() and ":" in line:
            save_current_field()
            parts = line.split(":", 1)
            if len(parts) == 2:
                current_key = parts[0].strip().lower()
                first_value = parts[1]
                if first_value.strip():
                    current_value_lines.append(first_value)
        elif line.startswith(" ") or line.startswith("\t"):
            # Continuation line (YAML multi-line value).
            if current_key:
                current_value_lines.append(line)

    save_current_field()
    return metadata


def _store_field(
    metadata: Dict[str, Any],
    key: str,
    value: str,
    postprocess_caption: Callable[[str], str],
) -> None:
    """Store a single parsed metadata field, coercing types as needed."""
    if key not in _KNOWN_FIELDS:
        return

    if key in ("bpm", "duration"):
        try:
            metadata[key] = int(value.strip())
        except (ValueError, TypeError):
            metadata[key] = value.strip()
    elif key == "caption":
        metadata[key] = postprocess_caption(value)
    else:
        metadata[key] = value.strip()
