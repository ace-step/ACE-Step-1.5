"""Response parsing helpers for external AI text-task integrations."""

from __future__ import annotations

import json

from .external_ai_json_parsing import (
    load_plan_json_object,
    to_bool,
    to_float,
    to_int,
)
from .external_ai_protocols import normalize_protocol
from .external_ai_types import ExternalAIClientError, ExternalAIPlan


def extract_protocol_message_content(*, raw_response: str, protocol: str) -> str:
    """Extract assistant content from protocol-specific API responses."""

    try:
        outer = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ExternalAIClientError("Invalid External AI response shape.") from exc

    normalized_protocol = normalize_protocol(protocol, purpose="response")
    if normalized_protocol == "anthropic_messages":
        return _extract_anthropic_content(outer)
    return _extract_openai_style_content(outer)


def parse_plan_from_content(content: str, task_focus: str = "all") -> ExternalAIPlan:
    """Parse assistant content into a normalized plan object."""

    obj = load_plan_json_object(content, task_focus=task_focus)
    caption = str(obj.get("caption") or "").strip()
    lyrics = str(obj.get("lyrics") or "").strip()
    instrumental = to_bool(obj.get("instrumental"))
    bpm = to_int(obj.get("bpm"))
    duration = to_float(obj.get("duration"))
    key_scale = str(obj.get("key_scale") or obj.get("keyscale") or "").strip()
    time_signature = str(obj.get("time_signature") or obj.get("timesignature") or "").strip()
    vocal_language = str(obj.get("vocal_language") or "").strip()

    if instrumental and not lyrics:
        lyrics = "[Instrumental]"

    return ExternalAIPlan(
        caption=caption,
        lyrics=lyrics,
        bpm=bpm,
        duration=duration,
        key_scale=key_scale,
        time_signature=time_signature,
        vocal_language=vocal_language,
        instrumental=instrumental,
    )


def _extract_anthropic_content(outer: dict[str, object]) -> str:
    """Return text content from Anthropic-style message responses."""

    try:
        blocks = outer["content"]
        if isinstance(blocks, list):
            text_chunks = [
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return "\n".join(chunk for chunk in text_chunks if chunk)
        if isinstance(blocks, str):
            return blocks
    except (KeyError, TypeError) as exc:
        raise ExternalAIClientError("Invalid External AI response shape.") from exc
    raise ExternalAIClientError("Invalid External AI response shape.")


def _extract_openai_style_content(outer: dict[str, object]) -> str:
    """Return text content from OpenAI-compatible chat completion responses."""

    try:
        choices = outer["choices"]
        if not isinstance(choices, list) or not choices:
            raise ExternalAIClientError("External AI response is missing choices.")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ExternalAIClientError("Invalid OpenAI-style External AI response shape.")
        message = choice["message"]
        if not isinstance(message, dict):
            raise ExternalAIClientError("Invalid OpenAI-style External AI response shape.")
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_chunks: list[str] = []
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "text":
                    raise ExternalAIClientError("Invalid OpenAI-style External AI response shape.")
                text = block.get("text", "")
                if not isinstance(text, str):
                    raise ExternalAIClientError("Invalid OpenAI-style External AI response shape.")
                if text:
                    text_chunks.append(text)
            return "\n".join(text_chunks)
        raise ExternalAIClientError("Invalid OpenAI-style External AI response shape.")
    except (KeyError, TypeError) as exc:
        raise ExternalAIClientError("Invalid OpenAI-style External AI response shape.") from exc
