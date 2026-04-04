"""Action handlers for the external-LM setup accordion."""

from __future__ import annotations

import os

from loguru import logger

from acestep.text_tasks.external_lm_credentials import resolve_external_secret_store_path
from acestep.text_tasks.external_lm_model_cache import load_cached_external_models, save_cached_external_models
from acestep.text_tasks.external_lm_model_discovery import ExternalModelDiscoveryError, discover_external_models
from acestep.text_tasks.external_lm_providers import get_external_provider_profile
from acestep.text_tasks.external_lm_runtime_store import load_external_lm_runtime_settings, save_external_lm_runtime_settings
from acestep.text_tasks.passphrase_store import resolve_runtime_passphrase
from acestep.text_tasks.secure_secret_store import EncryptedSecretStore, SecretStoreError
from acestep.ui.gradio.i18n import t

from .external_lm_setup_support import discover_provider_models, format_status_lines


def fetch_models_action(*, provider: str, model: str, base_url: str, api_key: str, gr,
                        get_profile=get_external_provider_profile,
                        discover_models=discover_provider_models,
                        save_cache=save_cached_external_models,
                        status_formatter=format_status_lines):
    """Discover remote model IDs and return dropdown/status updates."""

    try:
        profile = get_profile(provider)
        resolved_base_url, models = discover_models(
            profile=profile,
            base_url=base_url,
            api_key=api_key,
        )
    except ValueError as exc:
        return gr.update(), status_formatter([f"❌ {exc}"])
    except ExternalModelDiscoveryError as exc:
        return gr.update(), status_formatter([t("messages.external_lm_endpoint_failed", error=str(exc))])
    except (OSError, SecretStoreError, RuntimeError) as exc:
        return gr.update(), status_formatter([t("messages.external_lm_endpoint_failed", error=str(exc))])

    selected_model = (model or "").strip()
    if not selected_model or selected_model not in models:
        selected_model = models[0] if models else profile.default_model
    status_lines = [t("messages.external_lm_models_loaded", provider=profile.label, count=len(models))]
    try:
        save_cache(
            provider=profile.provider_id,
            protocol=profile.protocol,
            base_url=resolved_base_url,
            models=models,
        )
    except OSError as exc:
        logger.warning(
            "Failed to persist external model cache for provider '{}': {}",
            profile.provider_id,
            exc,
        )
        status_lines.append(t("messages.external_lm_cache_not_saved", error=str(exc)))
    return gr.update(choices=models, value=selected_model), status_formatter(status_lines)

def save_settings_action(*, provider: str, model: str, base_url: str, api_key: str,
                         get_profile=get_external_provider_profile,
                         save_runtime_settings=save_external_lm_runtime_settings,
                         secret_store_cls=EncryptedSecretStore,
                         resolve_secret_store_path=resolve_external_secret_store_path,
                         resolve_passphrase=resolve_runtime_passphrase,
                         status_formatter=format_status_lines) -> str:
    """Persist external LM runtime settings and optionally store the API key securely."""

    try:
        profile = get_profile(provider)
    except ValueError as exc:
        return status_formatter([f"❌ {exc}"])

    resolved_model = (model or "").strip() or profile.default_model
    resolved_base_url = (base_url or "").strip() or profile.default_base_url
    save_runtime_settings(
        provider=profile.provider_id,
        protocol=profile.protocol,
        model=resolved_model,
        base_url=resolved_base_url,
    )

    status_lines = [t("messages.external_lm_settings_saved", provider=profile.label)]
    explicit_api_key = (api_key or "").strip()
    if not explicit_api_key:
        status_lines.append(t("messages.external_lm_no_api_key", env_name=profile.api_key_env))
        return status_formatter(status_lines)

    try:
        secret_store = secret_store_cls(secret_path=resolve_secret_store_path(profile))
        secret_store.save(
            secret=explicit_api_key,
            passphrase=(resolve_passphrase() or "").strip(),
        )
    except SecretStoreError as exc:
        status_lines.append(t("messages.external_lm_api_key_not_saved", error=str(exc)))
        return status_formatter(status_lines)

    status_lines.append(t("messages.external_lm_api_key_saved", path=str(secret_store.secret_path)))
    return status_formatter(status_lines)
def test_endpoint_action(*, provider: str, base_url: str, api_key: str,
                         get_profile=get_external_provider_profile,
                         discover_models=discover_provider_models,
                         status_formatter=format_status_lines) -> str:
    """Probe the provider endpoint via model discovery and report connectivity."""

    try:
        profile = get_profile(provider)
        _, models = discover_models(
            profile=profile,
            base_url=base_url,
            api_key=api_key,
        )
    except ValueError as exc:
        return status_formatter([f"❌ {exc}"])
    except ExternalModelDiscoveryError as exc:
        return status_formatter([t("messages.external_lm_endpoint_failed", error=str(exc))])
    except (OSError, SecretStoreError, RuntimeError) as exc:
        return status_formatter([t("messages.external_lm_endpoint_failed", error=str(exc))])

    return status_formatter([t("messages.external_lm_endpoint_ok", provider=profile.label, count=len(models))])


def runtime_doctor_action(*, provider: str, model: str, base_url: str, api_key: str,
                          get_profile=get_external_provider_profile,
                          load_cached_models=load_cached_external_models,
                          load_runtime_settings=load_external_lm_runtime_settings,
                          resolve_secret_store_path=resolve_external_secret_store_path,
                          has_secret_store_value=None,
                          status_formatter=format_status_lines) -> str:
    """Summarize the effective runtime state for the external LM configuration."""

    try:
        profile = get_profile(provider)
    except ValueError as exc:
        return status_formatter([f"❌ {exc}"])

    resolved_model = (model or "").strip() or profile.default_model
    resolved_base_url = (base_url or "").strip() or profile.default_base_url
    cached_models = load_cached_models(provider=profile.provider_id, protocol=profile.protocol, base_url=resolved_base_url) or []
    stored = load_runtime_settings(profile.provider_id) or {}
    explicit_api_key = (api_key or "").strip()
    env_api_key = os.getenv(profile.api_key_env, "").strip()
    secret_path = resolve_secret_store_path(profile)
    secret_store_present = _has_secret_store_value(
        profile=profile,
        secret_path=secret_path,
        has_secret_store_value=has_secret_store_value,
    )

    if explicit_api_key:
        api_key_status = t("messages.external_lm_doctor_api_key_inline")
    elif env_api_key:
        api_key_status = t("messages.external_lm_doctor_api_key_env", env_name=profile.api_key_env)
    elif secret_store_present:
        api_key_status = t("messages.external_lm_doctor_api_key_secret", path=str(secret_path))
    else:
        api_key_status = t("messages.external_lm_doctor_api_key_missing", env_name=profile.api_key_env)

    stored_status = (
        t("messages.external_lm_doctor_runtime_saved")
        if stored
        else t("messages.external_lm_doctor_runtime_missing")
    )
    cached_status = (
        t("messages.external_lm_doctor_cache_present", count=len(cached_models))
        if cached_models
        else t("messages.external_lm_doctor_cache_missing")
    )

    return status_formatter(
        [
            t("messages.external_lm_doctor_header", provider=profile.label),
            t("messages.external_lm_doctor_model", model=resolved_model),
            t("messages.external_lm_doctor_base_url", base_url=resolved_base_url),
            stored_status,
            cached_status,
            api_key_status,
        ]
    )


def _has_secret_store_value(*, profile, secret_path, has_secret_store_value) -> bool:
    """Return whether the configured secret exists in file storage or a native keyring."""

    if has_secret_store_value is not None:
        return bool(has_secret_store_value(profile))
    try:
        secret_store = EncryptedSecretStore(secret_path=secret_path)
    except SecretStoreError:
        return secret_path.exists()

    uses_native_keyring = bool(
        callable(getattr(secret_store, "_uses_native_keyring", None))
        and secret_store._uses_native_keyring()
    )
    if not uses_native_keyring:
        return secret_path.exists()
    try:
        return bool(secret_store.load(passphrase=(resolve_runtime_passphrase() or "").strip()).strip())
    except SecretStoreError:
        return False
