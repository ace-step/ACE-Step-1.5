"""External LM setup actions for the Gradio generation settings panel."""

from __future__ import annotations

import os

import gradio as gr

from acestep.text_tasks.external_lm_credentials import resolve_external_secret_store_path
from acestep.text_tasks.external_lm_model_cache import (
    load_cached_external_models,
    save_cached_external_models,
)
from acestep.text_tasks.external_lm_model_discovery import (
    ExternalModelDiscoveryError,
)
from acestep.text_tasks.external_lm_providers import (
    CUSTOM_BASE_URL_PRESET,
    get_external_base_url_preset_choices,
    get_external_base_url_preset_value,
    get_external_provider_profile,
)
from acestep.text_tasks.external_lm_runtime_store import (
    load_external_lm_runtime_settings,
    save_external_lm_runtime_settings,
)
from acestep.text_tasks.passphrase_store import resolve_runtime_passphrase
from acestep.text_tasks.secure_secret_store import EncryptedSecretStore, SecretStoreError
from acestep.ui.gradio.i18n import t

from .external_lm_setup_actions import (
    fetch_models_action,
    runtime_doctor_action,
    save_settings_action,
    test_endpoint_action,
)
from .external_lm_setup_support import discover_provider_models


def hydrate_external_lm_setup_fields(provider: str):
    """Hydrate provider-scoped model/base-url fields and preset choices."""

    try:
        profile = get_external_provider_profile(provider)
    except ValueError:
        return gr.update(), gr.update(), gr.update(), gr.update(value="")

    stored = load_external_lm_runtime_settings(profile.provider_id) or {}
    model = str(stored.get("model", "")).strip() or profile.default_model
    base_url = str(stored.get("base_url", "")).strip() or profile.default_base_url
    cached_models = load_cached_external_models(
        provider=profile.provider_id,
        protocol=profile.protocol,
        base_url=base_url,
    ) or []
    model_choices = [str(item).strip() for item in cached_models if str(item).strip()]
    if model not in model_choices:
        model_choices.insert(0, model)
    return (
        gr.update(choices=model_choices, value=model),
        gr.update(value=base_url),
        gr.update(
            choices=get_external_base_url_preset_choices(profile.provider_id),
            value=get_external_base_url_preset_value(profile.provider_id, base_url),
        ),
        gr.update(value=""),
    )


def apply_external_lm_base_url_preset(provider: str, preset: str, current_base_url: str):
    """Resolve the selected base-URL preset into the editable textbox value."""

    try:
        profile = get_external_provider_profile(provider)
    except ValueError:
        return gr.update()

    preset_value = (preset or "").strip()
    if not preset_value or preset_value == CUSTOM_BASE_URL_PRESET:
        return gr.update(value=(current_base_url or "").strip())

    valid_choices = {value for _, value in get_external_base_url_preset_choices(profile.provider_id)}
    if preset_value not in valid_choices:
        return gr.update(value=(current_base_url or "").strip())
    return gr.update(value=preset_value)


def sync_external_lm_base_url_preset(provider: str, base_url: str):
    """Update the preset dropdown when the base URL is edited manually."""

    try:
        profile = get_external_provider_profile(provider)
    except ValueError:
        return gr.update()

    normalized_base_url = (base_url or "").strip() or profile.default_base_url
    return gr.update(
        choices=get_external_base_url_preset_choices(profile.provider_id),
        value=get_external_base_url_preset_value(profile.provider_id, normalized_base_url),
    )


def fetch_external_lm_models(provider: str, model: str, base_url: str, api_key: str):
    """Discover remote model IDs and update the model dropdown choices."""

    return fetch_models_action(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        gr=gr,
        get_profile=get_external_provider_profile,
        discover_models=discover_provider_models,
        save_cache=save_cached_external_models,
        status_formatter=_format_status_lines,
    )


def save_external_lm_settings(provider: str, model: str, base_url: str, api_key: str) -> str:
    """Persist external LM runtime settings and optionally store the API key securely."""

    return save_settings_action(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        get_profile=get_external_provider_profile,
        save_runtime_settings=save_external_lm_runtime_settings,
        secret_store_cls=EncryptedSecretStore,
        resolve_secret_store_path=_resolve_secret_store_path,
        resolve_passphrase=resolve_runtime_passphrase,
        status_formatter=_format_status_lines,
    )


def test_external_lm_endpoint(provider: str, model: str, base_url: str, api_key: str) -> str:
    """Probe the provider endpoint via model discovery and report connectivity."""

    return test_endpoint_action(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        get_profile=get_external_provider_profile,
        discover_models=discover_provider_models,
        status_formatter=_format_status_lines,
    )


def run_external_lm_runtime_doctor(provider: str, model: str, base_url: str, api_key: str) -> str:
    """Summarize the effective runtime state for the external LM configuration."""

    return runtime_doctor_action(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        get_profile=get_external_provider_profile,
        load_cached_models=load_cached_external_models,
        load_runtime_settings=load_external_lm_runtime_settings,
        resolve_secret_store_path=_resolve_secret_store_path,
        status_formatter=_format_status_lines,
    )


def _resolve_secret_store_path(profile):
    """Return the configured or default encrypted-secret path for a provider."""

    return resolve_external_secret_store_path(profile)


def _format_status_lines(lines: list[str]) -> str:
    """Join non-empty status lines into the markdown status payload."""

    return "\n\n".join(line for line in lines if line)
