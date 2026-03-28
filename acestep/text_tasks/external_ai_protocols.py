"""Protocol and intent-signal helpers for external AI request building."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .external_ai_types import ExternalAIClientError

SUPPORTED_PROTOCOLS = frozenset({"anthropic_messages", "openai_chat"})


def extract_intent_signal_text(intent: str) -> str:
    """Return the caption and explicit metadata lines used for intent heuristics."""

    lines = [(line or "").strip() for line in (intent or "").splitlines()]
    signal_lines = [
        line.partition(":")[2].strip()
        for line in lines
        if line.lower().startswith(("caption:", "instrumental:", "vocal_language:"))
    ]
    if signal_lines:
        return "\n".join(signal_lines).lower().strip()
    return (intent or "").strip().lower()


def normalize_protocol(protocol: str, *, purpose: str = "request") -> str:
    """Validate and normalize a supported external AI protocol identifier."""

    normalized_protocol = (protocol or "openai_chat").strip().lower()
    if normalized_protocol not in SUPPORTED_PROTOCOLS:
        raise ExternalAIClientError(
            f"Unsupported external {purpose} protocol: {normalized_protocol or '<empty>'}."
        )
    return normalized_protocol


def normalize_request_protocol(protocol: str) -> str:
    """Validate and normalize a supported request protocol identifier."""

    return normalize_protocol(protocol, purpose="request")


def require_message_pair(messages: Sequence[Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Return the expected system and user messages for provider request building."""

    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)) or len(messages) < 2:
        raise ExternalAIClientError(
            "External planning request requires both system and user messages."
        )
    system_message, user_message = messages[0], messages[1]
    if not isinstance(system_message, dict) or not isinstance(user_message, dict):
        raise ExternalAIClientError(
            "External planning request requires both system and user messages."
        )
    if system_message.get("role") != "system" or user_message.get("role") != "user":
        raise ExternalAIClientError(
            "External planning request requires a system message followed by a user message."
        )
    system_content = system_message.get("content")
    user_content = user_message.get("content")
    if (
        not isinstance(system_content, str)
        or system_content == ""
        or not isinstance(user_content, str)
        or user_content == ""
    ):
        raise ExternalAIClientError(
            "External planning request requires content fields on system and user messages."
        )
    return system_message, user_message
