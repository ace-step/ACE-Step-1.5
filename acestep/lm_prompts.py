"""Prompt formatting for the 5Hz language model.

Extracted from ``LLMHandler`` so prompt logic can be tested and reused
without instantiating the full inference pipeline.

Every public function accepts a *tokenizer* that must implement
``apply_chat_template(messages, tokenize, add_generation_prompt)``.
"""

from __future__ import annotations

from typing import Any, Protocol

from acestep.constants import (
    DEFAULT_LM_INSTRUCTION,
    DEFAULT_LM_INSPIRED_INSTRUCTION,
    DEFAULT_LM_REWRITE_INSTRUCTION,
    DEFAULT_LM_UNDERSTAND_INSTRUCTION,
)


# ---------------------------------------------------------------------------
# Typing helpers
# ---------------------------------------------------------------------------

class ChatTokenizer(Protocol):
    """Minimal interface required by the prompt builders."""

    def apply_chat_template(
        self,
        messages: list[dict[str, Any]],
        *,
        tokenize: bool = False,
        add_generation_prompt: bool = True,
    ) -> str: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def has_meaningful_negative_prompt(negative_prompt: str) -> bool:
    """Return *True* if *negative_prompt* is not the default/empty sentinel."""
    return bool(
        negative_prompt
        and negative_prompt.strip()
        and negative_prompt.strip() != "NO USER INPUT"
    )


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_formatted_prompt(
    tokenizer: ChatTokenizer,
    caption: str,
    lyrics: str = "",
    is_negative_prompt: bool = False,
    generation_phase: str = "cot",
    negative_prompt: str = "NO USER INPUT",
) -> str:
    """Build the chat-formatted prompt for 5Hz LM from caption/lyrics.

    Parameters
    ----------
    tokenizer:
        A HuggingFace tokenizer (or compatible) with ``apply_chat_template``.
    caption, lyrics, is_negative_prompt, generation_phase, negative_prompt:
        See ``LLMHandler.build_formatted_prompt`` for semantics.
    """
    if is_negative_prompt:
        has_neg = has_meaningful_negative_prompt(negative_prompt)
        if generation_phase == "cot":
            if has_neg:
                prompt = f"# Caption\n{negative_prompt}\n\n# Lyric\n{lyrics}\n"
            else:
                prompt = f"# Lyric\n{lyrics}\n"
        else:
            prompt = caption
    else:
        prompt = f"# Caption\n{caption}\n\n# Lyric\n{lyrics}\n"

    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": f"# Instruction\n{DEFAULT_LM_INSTRUCTION}\n\n"},
            {"role": "user", "content": prompt},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )


def build_formatted_prompt_with_cot(
    tokenizer: ChatTokenizer,
    caption: str,
    lyrics: str,
    cot_text: str,
    is_negative_prompt: bool = False,
    negative_prompt: str = "NO USER INPUT",
) -> str:
    """Build the codes-generation prompt with pre-generated CoT."""
    if is_negative_prompt:
        has_neg = has_meaningful_negative_prompt(negative_prompt)
        cot_for_prompt = "<think>\n</think>"
        caption_for_prompt = negative_prompt if has_neg else caption
    else:
        cot_for_prompt = cot_text
        caption_for_prompt = caption

    user_prompt = f"# Caption\n{caption_for_prompt}\n\n# Lyric\n{lyrics}\n"

    formatted = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": f"# Instruction\n{DEFAULT_LM_INSTRUCTION}\n\n"},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": cot_for_prompt},
        ],
        tokenize=False,
        add_generation_prompt=False,
    )

    if not formatted.endswith("\n"):
        formatted += "\n"

    return formatted


def build_formatted_prompt_for_understanding(
    tokenizer: ChatTokenizer,
    audio_codes: str,
    is_negative_prompt: bool = False,
    negative_prompt: str = "NO USER INPUT",
) -> str:
    """Build the prompt for audio understanding (codes -> metadata + lyrics)."""
    if is_negative_prompt:
        user_content = negative_prompt if negative_prompt and negative_prompt.strip() else ""
    else:
        user_content = audio_codes

    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": f"# Instruction\n{DEFAULT_LM_UNDERSTAND_INSTRUCTION}\n\n"},
            {"role": "user", "content": user_content},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )


def build_formatted_prompt_for_inspiration(
    tokenizer: ChatTokenizer,
    query: str,
    instrumental: bool = False,
    is_negative_prompt: bool = False,
    negative_prompt: str = "NO USER INPUT",
) -> str:
    """Build the prompt for inspiration/simple mode."""
    instrumental_str = "true" if instrumental else "false"

    if is_negative_prompt:
        user_content = negative_prompt if negative_prompt and negative_prompt.strip() else ""
    else:
        user_content = f"{query}\n\ninstrumental: {instrumental_str}"

    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": f"# Instruction\n{DEFAULT_LM_INSPIRED_INSTRUCTION}\n\n"},
            {"role": "user", "content": user_content},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )


def build_formatted_prompt_for_format(
    tokenizer: ChatTokenizer,
    caption: str,
    lyrics: str,
    is_negative_prompt: bool = False,
    negative_prompt: str = "NO USER INPUT",
) -> str:
    """Build the prompt for format/rewrite mode."""
    if is_negative_prompt:
        user_content = negative_prompt if negative_prompt and negative_prompt.strip() else ""
    else:
        user_content = f"# Caption\n{caption}\n\n# Lyric\n{lyrics}"

    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": f"# Instruction\n{DEFAULT_LM_REWRITE_INSTRUCTION}\n\n"},
            {"role": "user", "content": user_content},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )
