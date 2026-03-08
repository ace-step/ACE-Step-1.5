"""Interactive CLI prompt helpers extracted from cli.py."""

from __future__ import annotations

import os
import re
import sys
from typing import List, Optional, Tuple

from acestep.cli.parsers import _expand_audio_path


def _prompt_non_empty(prompt: str) -> str:
    value = input(prompt).strip()
    while not value:
        value = input(prompt).strip()
    return value


def _prompt_with_default(prompt: str, default: Optional[str] = None, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default not in (None, "") else ""
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default not in (None, ""):
            return str(default)
        if not required:
            return ""
        print("This value is required. Please try again.")


def _prompt_bool(prompt: str, default: bool) -> bool:
    default_str = "y" if default else "n"
    while True:
        value = input(f"{prompt} (y/n) [default: {default_str}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes", "1", "true"}:
            return True
        if value in {"n", "no", "0", "false"}:
            return False
        print("Please enter 'y' or 'n'.")


def _prompt_choice_from_list(
    prompt: str,
    options: List[str],
    default: Optional[str] = None,
    allow_custom: bool = True,
    custom_validator=None,
    custom_error: Optional[str] = None,
) -> Optional[str]:
    if not options:
        return default
    print("\n" + prompt)
    for idx, option in enumerate(options, start=1):
        print(f"{idx}. {option}")
    default_display = default if default not in (None, "") else "auto"
    while True:
        choice = input(f"Choose a model (number or name) [default: {default_display}]: ").strip()
        if not choice:
            return None if default_display == "auto" else default
        if choice.lower() == "auto":
            return None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1]
            print("Invalid selection. Please choose a valid number.")
            continue
        if allow_custom:
            if custom_validator and not custom_validator(choice):
                print(custom_error or "Invalid selection. Please try again.")
                continue
            if choice not in options:
                print("Unknown model. Using as-is.")
            return choice
        print("Please choose a valid option.")


def _prompt_int(prompt: str, default: Optional[int] = None, min_value: Optional[int] = None,
                max_value: Optional[int] = None) -> Optional[int]:
    default_display = "auto" if default is None else default
    while True:
        value = input(f"{prompt} [{default_display}]: ").strip()
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            print("Invalid input. Please enter an integer.")
            continue
        if min_value is not None and parsed < min_value:
            print(f"Please enter a value >= {min_value}.")
            continue
        if max_value is not None and parsed > max_value:
            print(f"Please enter a value <= {max_value}.")
            continue
        return parsed


def _prompt_float(prompt: str, default: Optional[float] = None, min_value: Optional[float] = None,
                  max_value: Optional[float] = None) -> Optional[float]:
    default_display = "auto" if default is None else default
    while True:
        value = input(f"{prompt} [{default_display}]: ").strip()
        if not value:
            return default
        try:
            parsed = float(value)
        except ValueError:
            print("Invalid input. Please enter a number.")
            continue
        if min_value is not None and parsed < min_value:
            print(f"Please enter a value >= {min_value}.")
            continue
        if max_value is not None and parsed > max_value:
            print(f"Please enter a value <= {max_value}.")
            continue
        return parsed


def _prompt_existing_file(prompt: str, default: Optional[str] = None) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        path = input(f"{prompt}{suffix}: ").strip()
        if not path and default:
            path = default
        if os.path.isfile(path):
            return _expand_audio_path(path)
        print("Invalid file path. Please try again.")


def _edit_formatted_prompt_via_file(formatted_prompt: str, instruction_path: str) -> str:
    """Write formatted prompt to file, wait for user edits, then read back."""
    try:
        with open(instruction_path, "w", encoding="utf-8") as f:
            f.write(formatted_prompt)
    except Exception as e:
        print(f"WARNING: Failed to write {instruction_path}: {e}")
        return formatted_prompt

    print("\n--- Final Draft Saved ---")
    print(f"Saved to {instruction_path}")
    print("Edit the file now. Press Enter when ready to continue.")
    input()

    try:
        with open(instruction_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"WARNING: Failed to read {instruction_path}: {e}")
        return formatted_prompt


def _install_prompt_edit_hook(
    llm_handler: "LLMHandler",
    instruction_path: str,
    preloaded_prompt: Optional[str] = None,
) -> None:
    """Intercept formatted prompt generation to allow user editing before audio tokens."""
    # Import extraction helpers lazily to avoid circular imports
    from cli import (
        _extract_caption_lyrics_from_formatted_prompt,
        _extract_cot_metadata_from_formatted_prompt,
        _extract_instruction_from_formatted_prompt,
    )

    original = llm_handler.build_formatted_prompt_with_cot
    cache = {}

    def wrapped(caption, lyrics, cot_text, is_negative_prompt=False, negative_prompt="NO USER INPUT"):
        prompt = original(
            caption,
            lyrics,
            cot_text,
            is_negative_prompt=is_negative_prompt,
            negative_prompt=negative_prompt,
        )
        if is_negative_prompt:
            conditional_prompt = original(
                caption,
                lyrics,
                cot_text,
                is_negative_prompt=False,
                negative_prompt=negative_prompt,
            )
            cached = cache.get(conditional_prompt)
            if cached and (cached.get("edited_caption") or cached.get("edited_lyrics")):
                edited_caption = cached.get("edited_caption") or caption
                edited_lyrics = cached.get("edited_lyrics") or lyrics
                return original(
                    edited_caption,
                    edited_lyrics,
                    cot_text,
                    is_negative_prompt=True,
                    negative_prompt=negative_prompt,
                )
            return prompt
        cached = cache.get(prompt)
        if cached:
            return cached["edited_prompt"]
        if getattr(llm_handler, "_skip_prompt_edit", False):
            cache[prompt] = {
                "edited_prompt": prompt,
                "edited_caption": None,
                "edited_lyrics": None,
            }
            return prompt
        if preloaded_prompt is not None:
            edited = preloaded_prompt
        else:
            edited = _edit_formatted_prompt_via_file(prompt, instruction_path)
        edited_caption, edited_lyrics = _extract_caption_lyrics_from_formatted_prompt(edited)
        if edited != prompt:
            print("INFO: Using edited draft for audio-token prompt.")
            if edited_caption or edited_lyrics:
                llm_handler._edited_caption = edited_caption
                llm_handler._edited_lyrics = edited_lyrics
            edited_instruction = _extract_instruction_from_formatted_prompt(edited)
            if edited_instruction:
                llm_handler._edited_instruction = edited_instruction
            edited_metas = _extract_cot_metadata_from_formatted_prompt(edited)
            if edited_metas:
                llm_handler._edited_metas = edited_metas
        cache[prompt] = {
            "edited_prompt": edited,
            "edited_caption": edited_caption,
            "edited_lyrics": edited_lyrics,
        }
        return edited

    llm_handler.build_formatted_prompt_with_cot = wrapped
