"""Request-building helpers for external AI formatting calls."""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib import parse

from .external_ai_protocols import (
    extract_intent_signal_text,
    normalize_request_protocol,
    require_message_pair,
)
from .external_ai_types import ExternalAIClientError


def build_task_focus_guidance(*, task_focus: str) -> str:
    """Return task-specific guidance for planning prompts."""

    normalized_focus = (task_focus or "all").strip().lower()
    if normalized_focus == "format":
        return (
            "For format focus: preserve user intent, then expand it into a fuller standard song caption. "
            "Write a linear narrative description of the arrangement that covers who is singing, the "
            "singer's delivery or mood, the core instrumentation, how the song progresses from intro to "
            "verse to chorus or drop to outro, and how the mix or energy evolves. "
            "Keep the caption under 200 words. "
            "Set instrumental to true or false only, never to an instrument list or free-form text. "
            "Do not output reasoning, analysis, or commentary outside the JSON object. "
            "Do not change the core genre or mood unless required for coherence."
        )
    return (
        "For all-task focus: produce complete caption, lyrics, and metadata that can directly "
        "drive music generation."
    )


def build_intent_specific_guidance(intent: str) -> str:
    """Return extra format guidance inferred from the user's stated intent."""

    normalized_signal = extract_intent_signal_text(intent)
    if not normalized_signal:
        return ""

    if re.search(r"(?im)^\s*instrumental\s*:\s*(?:true|1|yes)\s*$", intent or ""):
        return (
            "Honor the no-vocals or instrumental request exactly. "
            "Do not introduce lead vocals, backing vocals, choir parts, choir harmonies, choral textures, "
            "vocal harmonies, or vocal language. "
            "Set instrumental to true."
        )

    if any(
        marker in normalized_signal
        for marker in ("no vocals", "no lead vocals", "instrumental only")
    ) or normalized_signal in {"instrumental", "fully instrumental", "purely instrumental"}:
        return (
            "Honor the no-vocals or instrumental request exactly. "
            "Do not introduce lead vocals, backing vocals, choir parts, choir harmonies, choral textures, "
            "vocal harmonies, or vocal language. "
            "Set instrumental to true."
        )
    return ""


def build_planning_messages(intent: str, task_focus: str = "all") -> list[dict[str, str]]:
    """Build protocol-agnostic planning messages."""

    system = (
        "You generate structured music planning JSON for ACE-Step. "
        "Return only valid JSON with keys: caption, lyrics, bpm, duration, "
        "key_scale, time_signature, vocal_language, instrumental. "
        "Caption must be a linear narrative production brief describing arrangement, vocals, instrumentation, "
        "song progression, and energy or mix evolution. "
        "Keep the caption under 200 words. "
        "The instrumental field must be a JSON boolean. "
        "Start the response with '{' and end it with '}'. "
        "Do not wrap the JSON in code fences. "
        "Do not include chain-of-thought, reasoning, analysis, or any text outside the JSON object."
    )
    user = (
        f"Task focus: {task_focus}\n"
        f"User intent:\n{intent}\n\n"
        f"{build_task_focus_guidance(task_focus=task_focus)}\n"
        f"{build_intent_specific_guidance(intent)}\n"
        "Output JSON only. No markdown, no commentary."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_request_for_protocol(
    *,
    protocol: str,
    provider: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    base_url: str,
    max_tokens: int | None = None,
    disable_thinking: bool = False,
    require_json_output: bool = False,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build protocol-specific payload and headers."""

    normalized_protocol = normalize_request_protocol(protocol)
    if normalized_protocol == "anthropic_messages":
        if not api_key:
            raise ExternalAIClientError("Missing API key for anthropic_messages protocol.")
        system_message, user_message = require_message_pair(messages)
        payload = {
            "model": model,
            "max_tokens": max_tokens or int(os.getenv("ACESTEP_ANTHROPIC_MAX_TOKENS", "1024")),
            "temperature": 0.4,
            "system": system_message["content"],
            "messages": [{"role": "user", "content": user_message["content"]}],
        }
        if require_json_output:
            payload["stop_sequences"] = ["```"]
        headers = {
            "x-api-key": api_key,
            "anthropic-version": os.getenv("ACESTEP_ANTHROPIC_VERSION", "2023-06-01"),
            "Content-Type": "application/json",
        }
        return payload, headers

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens or int(os.getenv("ACESTEP_OPENAI_MAX_TOKENS", "3072")),
        "temperature": 0.4,
    }
    if require_json_output and provider in {"openai", "zai"}:
        payload["response_format"] = {"type": "json_object"}
        payload["stop"] = ["```"]
    if disable_thinking and provider == "zai":
        payload["thinking"] = {"type": "disabled"}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return payload, headers


def resolve_max_tokens_for_task_focus(task_focus: str) -> int:
    """Return a task-focused completion budget for external planning calls."""

    normalized_focus = (task_focus or "all").strip().lower()
    if normalized_focus == "format":
        return int(os.getenv("ACESTEP_EXTERNAL_FORMAT_MAX_TOKENS", "768"))
    return int(os.getenv("ACESTEP_OPENAI_MAX_TOKENS", "3072"))


def build_http_error_guidance(*, detail: str, model: str, base_url: str) -> str:
    """Return targeted guidance for common HTTP/API error payloads."""

    if not detail:
        return ""
    try:
        payload = json.loads(detail)
        raw_error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(raw_error, dict):
            code = str(raw_error.get("code", "")).strip()
            error_type = str(raw_error.get("type", "")).strip().lower()
            message = str(raw_error.get("message", "")).strip().lower()
        else:
            code = ""
            error_type = ""
            message = str(raw_error or detail).strip().lower()
    except json.JSONDecodeError:
        code = ""
        error_type = ""
        message = detail.strip().lower()

    parsed_base_url = parse.urlparse(base_url or "")
    normalized_host = (parsed_base_url.hostname or "").strip().lower()
    is_openai_endpoint = normalized_host == "api.openai.com"
    quota_like_error = (
        code == "insufficient_quota"
        or error_type == "insufficient_quota"
        or "insufficient_quota" in message
        or ("quota" in message and "insufficient" in message)
    )
    if code == "1211":
        return " | Model not found. Try a valid provider model and verify your account has access."
    if is_openai_endpoint and quota_like_error:
        return (
            " | OpenAI API quota is unavailable for this request. ChatGPT or Codex subscription "
            "usage is separate from API billing for app-driven API-key calls."
        )
    return ""
