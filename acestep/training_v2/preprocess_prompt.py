"""
Prompt builder for ACE-Step preprocessing.

Builds the ``SFT_GEN_PROMPT``-formatted text prompt from per-sample
metadata, supporting caption, genre, custom trigger tags, and
optional per-sample ``prompt_override``.

Extracted from ``preprocess.py`` to keep that module under the LOC limit.
"""

from __future__ import annotations

from typing import Any, Dict


def build_simple_prompt(
    meta: Dict[str, Any],
    tag_position: str = "prepend",
    use_genre: bool = False,
) -> str:
    """Build a text prompt from sample metadata.

    Mimics the upstream ``build_text_prompt`` + ``build_metas_str`` +
    ``AudioSample.get_training_prompt`` without requiring the
    ``AudioSample`` dataclass or ``DatasetBuilder``.

    Supports the same JSON fields as upstream:
    - ``caption``, ``genre``: primary text descriptions.
    - ``custom_tag``: trigger word prepended/appended/replaced.
    - ``prompt_override``: per-sample ``"caption"`` or ``"genre"`` override.

    Args:
        meta: Per-sample metadata dict from the dataset JSON.
        tag_position: Where to apply ``custom_tag`` (``"prepend"``,
            ``"append"``, or ``"replace"``).
        use_genre: If ``True`` and no ``prompt_override``, use the
            ``genre`` field instead of ``caption``.
    """
    from acestep.constants import DEFAULT_DIT_INSTRUCTION, SFT_GEN_PROMPT

    caption = meta.get("caption", "")
    genre = meta.get("genre", "")
    override = meta.get("prompt_override")
    tag = meta.get("custom_tag", "")

    # Decide caption vs genre (mirrors AudioSample.get_training_prompt)
    if override == "genre":
        text = genre
    elif override == "caption" or not use_genre:
        text = caption
    else:
        text = genre or caption

    # Apply custom_tag (mirrors AudioSample.get_full_caption / get_full_genre)
    if tag:
        if tag_position == "prepend":
            text = f"{tag}, {text}" if text else tag
        elif tag_position == "append":
            text = f"{text}, {tag}" if text else tag
        elif tag_position == "replace":
            text = tag

    bpm = meta.get("bpm", "N/A") or "N/A"
    ts = meta.get("timesignature", "N/A") or "N/A"
    ks = meta.get("keyscale", "N/A") or "N/A"
    dur = meta.get("duration", 0)

    metas_str = (
        f"- bpm: {bpm}\n"
        f"- timesignature: {ts}\n"
        f"- keyscale: {ks}\n"
        f"- duration: {dur} seconds\n"
    )
    return SFT_GEN_PROMPT.format(DEFAULT_DIT_INSTRUCTION, text, metas_str)
