"""External LM format-mode request helpers."""

from __future__ import annotations

import os
from typing import Any
from urllib import request as urllib_request

from loguru import logger

from .external_ai_request_helpers import (
    build_planning_messages,
    build_request_for_protocol,
    resolve_max_tokens_for_task_focus,
)
from .external_ai_response_parsing import extract_protocol_message_content, parse_plan_from_content
from .external_ai_types import ExternalAIClientError, ExternalAIPlan
from .external_lm_captioning import (
    apply_user_metadata_overrides,
    build_fallback_caption,
    build_format_request_intent,
    caption_needs_retry,
)
from .external_lm_credentials import resolve_external_api_key
from .external_lm_http_client import post_external_request
from .external_lm_providers import get_external_provider_profile


def request_external_format_plan(
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    caption: str,
    lyrics: str,
    user_metadata: dict[str, Any] | None,
    protocol: str | None = None,
    timeout_sec: int = 90,
) -> ExternalAIPlan:
    """Request a format-mode plan from an external text model."""

    profile = get_external_provider_profile(provider)
    protocol_value = (protocol or profile.protocol).strip()
    model_value = (model or "").strip() or profile.default_model
    base_url_value = (base_url or "").strip() or profile.default_base_url
    api_key_value = resolve_external_api_key(provider=profile.provider_id, api_key=api_key)

    if profile.api_key_required and not api_key_value:
        raise ExternalAIClientError(
            f"Missing API key for external provider '{profile.provider_id}'."
        )
    if not base_url_value:
        raise ExternalAIClientError(
            f"Missing base URL for external provider '{profile.provider_id}'."
        )

    effective_caption = (caption or "").strip() or "NO USER INPUT"
    effective_lyrics = (lyrics or "").strip() or "[Instrumental]"
    intent = build_format_request_intent(
        caption=effective_caption,
        lyrics=effective_lyrics,
        user_metadata=user_metadata or {},
    )

    plan = _request_plan_once(
        provider=profile.provider_id,
        protocol=protocol_value,
        model=model_value,
        base_url=base_url_value,
        api_key=api_key_value,
        intent=intent,
        timeout_sec=timeout_sec,
    )
    if caption_needs_retry(
        original_caption=effective_caption,
        generated_caption=plan.caption,
    ):
        logger.info(
            "External LM caption looked under-specified for provider '{}'; retrying once.",
            profile.provider_id,
        )
        retry_intent = (
            intent
            + "\nRetry instruction: rewrite the caption into a fuller arrangement brief. "
            "Do not echo the source caption. Add concrete progression, instrumentation, "
            "and vocal or mix details while preserving the user's intent."
        )
        try:
            retry_plan = _request_plan_once(
                provider=profile.provider_id,
                protocol=protocol_value,
                model=model_value,
                base_url=base_url_value,
                api_key=api_key_value,
                intent=retry_intent,
                timeout_sec=timeout_sec,
            )
        except ExternalAIClientError as exc:
            logger.warning(
                "External LM retry failed for provider '{}'; keeping first plan: {}",
                profile.provider_id,
                exc,
            )
        else:
            plan = _merge_retry_plan(plan=plan, retry_plan=retry_plan)

    plan = apply_user_metadata_overrides(plan=plan, user_metadata=user_metadata or {})
    if caption_needs_retry(
        original_caption=effective_caption,
        generated_caption=plan.caption,
    ):
        plan.caption = build_fallback_caption(
            caption=effective_caption,
            user_metadata=user_metadata or {},
        )
    if not (plan.lyrics or "").strip():
        plan.lyrics = effective_lyrics
    return plan


def _merge_retry_plan(*, plan: ExternalAIPlan, retry_plan: ExternalAIPlan) -> ExternalAIPlan:
    """Overlay non-empty retry fields onto the first successful plan."""

    if (retry_plan.caption or "").strip():
        plan.caption = retry_plan.caption
    if (retry_plan.lyrics or "").strip():
        plan.lyrics = retry_plan.lyrics
    if retry_plan.bpm is not None:
        plan.bpm = retry_plan.bpm
    if retry_plan.duration is not None:
        plan.duration = retry_plan.duration
    if (retry_plan.key_scale or "").strip():
        plan.key_scale = retry_plan.key_scale
    if (retry_plan.time_signature or "").strip():
        plan.time_signature = retry_plan.time_signature
    if (retry_plan.vocal_language or "").strip():
        plan.vocal_language = retry_plan.vocal_language
    return plan


def _request_plan_once(
    *,
    provider: str,
    protocol: str,
    model: str,
    base_url: str,
    api_key: str,
    intent: str,
    timeout_sec: int,
) -> ExternalAIPlan:
    """Send one external format-mode request and parse the response."""

    messages = build_planning_messages(intent, task_focus="format")
    payload, headers = build_request_for_protocol(
        protocol=protocol,
        provider=provider,
        api_key=api_key,
        model=model,
        messages=messages,
        base_url=base_url,
        max_tokens=resolve_max_tokens_for_task_focus("format"),
        temperature=float(os.getenv("ACESTEP_EXTERNAL_FORMAT_TEMPERATURE", "0.2")),
        disable_thinking=True,
        require_json_output=True,
    )
    raw_response = _post_external_request(
        base_url=base_url,
        headers=headers,
        payload=payload,
        timeout_sec=timeout_sec,
        provider=provider,
        model=model,
    )
    content = extract_protocol_message_content(raw_response=raw_response, protocol=protocol)
    return parse_plan_from_content(content, task_focus="format")
def _post_external_request(
    *, base_url: str, headers: dict[str, str], payload: dict[str, Any], timeout_sec: int,
    provider: str, model: str,
) -> str:
    """POST JSON to an external provider using patch-friendly local transport."""

    return post_external_request(
        base_url=base_url,
        headers=headers,
        payload=payload,
        timeout_sec=timeout_sec,
        provider=provider,
        model=model,
        urlopen_impl=urllib_request.urlopen,
    )
