"""LLM generation action facade.

This module preserves the historical import path while delegating
implementation to focused sub-modules.
"""

from .llm_analysis_actions import analyze_src_audio, transcribe_audio_codes
from .llm_format_actions import (
    handle_format_caption,
    handle_format_lyrics,
    handle_format_sample,
)
from .llm_sample_actions import handle_create_sample

__all__ = [
    "analyze_src_audio",
    "handle_create_sample",
    "handle_format_caption",
    "handle_format_lyrics",
    "handle_format_sample",
    "transcribe_audio_codes",
]
