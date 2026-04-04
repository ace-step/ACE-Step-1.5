"""Support helpers for external-LM setup actions."""

from __future__ import annotations

from acestep.text_tasks.external_lm_credentials import resolve_external_api_key
from acestep.text_tasks.external_lm_model_discovery import (
    discover_external_models,
)


def discover_provider_models(*, profile, base_url: str, api_key: str) -> tuple[str, list[str]]:
    """Return the normalized base URL plus discovered models for a provider profile."""

    resolved_base_url = (base_url or "").strip() or profile.default_base_url
    resolved_api_key = resolve_external_api_key(
        provider=profile.provider_id,
        api_key=(api_key or "").strip(),
    )
    models = discover_external_models(
        provider=profile.provider_id,
        protocol=profile.protocol,
        base_url=resolved_base_url,
        api_key=resolved_api_key,
    )
    return resolved_base_url, models


def format_status_lines(lines: list[str]) -> str:
    """Join non-empty status lines into the markdown status payload."""

    return "\n\n".join(line for line in lines if line)
