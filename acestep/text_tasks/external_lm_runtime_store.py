"""Persistent runtime settings for external LM provider preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .external_lm_providers import get_external_provider_profile


def external_lm_settings_path() -> Path:
    """Return the user-local JSON settings path for external LM preferences."""

    xdg_data_home = os.getenv("XDG_DATA_HOME", "").strip()
    base = (
        Path(xdg_data_home).expanduser()
        if xdg_data_home
        else Path.home() / ".local" / "share"
    )
    return base / "acestep" / "config" / "external_lm_runtime.json"


def save_external_lm_runtime_settings(
    *,
    provider: str,
    protocol: str,
    model: str,
    base_url: str,
) -> Path:
    """Persist non-secret external LM settings for the active provider."""

    provider_id = (provider or "").strip().lower()
    settings = load_all_external_lm_runtime_settings()
    settings["active_provider"] = provider_id
    settings["providers"][provider_id] = {
        "provider": provider_id,
        "protocol": (protocol or "").strip(),
        "model": (model or "").strip(),
        "base_url": (base_url or "").strip(),
    }
    path = external_lm_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(settings, ensure_ascii=True, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return path


def load_external_lm_runtime_settings(provider: str | None = None) -> dict[str, str] | None:
    """Load persisted external LM settings for a provider or the active selection."""

    payload = load_all_external_lm_runtime_settings()
    provider_id = (provider or payload.get("active_provider") or "").strip().lower()
    if not provider_id:
        return None
    provider_settings = payload["providers"].get(provider_id)
    if not isinstance(provider_settings, dict):
        return None
    return {
        "provider": provider_id,
        "protocol": str(provider_settings.get("protocol", "")).strip(),
        "model": str(provider_settings.get("model", "")).strip(),
        "base_url": str(provider_settings.get("base_url", "")).strip(),
    }


def load_all_external_lm_runtime_settings() -> dict[str, object]:
    """Load the full persisted provider-settings payload."""

    path = external_lm_settings_path()
    if not path.exists():
        return {"active_provider": "", "providers": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active_provider": "", "providers": {}}
    return _normalize_runtime_settings_payload(parsed)


def hydrate_external_lm_env_from_store() -> bool:
    """Populate missing runtime env vars from persisted external LM settings.

    This mutates process-wide environment variables and is intended for early,
    one-time startup hydration. It sets missing values for
    ``ACESTEP_EXTERNAL_LM_PROVIDER``, ``ACESTEP_EXTERNAL_LM_PROTOCOL``,
    ``ACESTEP_EXTERNAL_LM_MODEL``, and ``ACESTEP_EXTERNAL_BASE_URL``, plus the
    derived ``ACESTEP_GLM_MODEL`` and ``ACESTEP_GLM_BASE_URL`` aliases when the
    resolved provider is ``zai``. Returns ``True`` when any env var was set.
    """

    requested_provider = os.getenv("ACESTEP_EXTERNAL_LM_PROVIDER", "")
    settings = load_external_lm_runtime_settings(requested_provider or None)
    if not settings:
        return False

    changed = False
    mappings = {
        "provider": "ACESTEP_EXTERNAL_LM_PROVIDER",
        "protocol": "ACESTEP_EXTERNAL_LM_PROTOCOL",
        "model": "ACESTEP_EXTERNAL_LM_MODEL",
        "base_url": "ACESTEP_EXTERNAL_BASE_URL",
    }
    for key, env_name in mappings.items():
        if os.getenv(env_name, "").strip():
            continue
        value = settings.get(key, "")
        if value:
            os.environ[env_name] = value
            changed = True

    provider = os.getenv("ACESTEP_EXTERNAL_LM_PROVIDER", "").strip().lower()
    if provider == "zai":
        model = os.getenv("ACESTEP_EXTERNAL_LM_MODEL", "").strip()
        base_url = os.getenv("ACESTEP_EXTERNAL_BASE_URL", "").strip()
        if model and not os.getenv("ACESTEP_GLM_MODEL", "").strip():
            os.environ["ACESTEP_GLM_MODEL"] = model
            changed = True
        if base_url and not os.getenv("ACESTEP_GLM_BASE_URL", "").strip():
            os.environ["ACESTEP_GLM_BASE_URL"] = base_url
            changed = True

    return changed


def _normalize_runtime_settings_payload(parsed: object) -> dict[str, object]:
    """Normalize persisted runtime settings in the current per-provider format."""

    if not isinstance(parsed, dict):
        return {"active_provider": "", "providers": {}}

    providers = parsed.get("providers")
    if not isinstance(providers, dict):
        return {"active_provider": "", "providers": {}}
    normalized_providers = {
        key.strip().lower(): normalized
        for key, value in providers.items()
        if isinstance(key, str)
        for normalized in [_normalize_provider_settings(key, value)]
        if normalized
    }
    active_provider = str(parsed.get("active_provider", "")).strip().lower()
    if not active_provider and normalized_providers:
        active_provider = next(iter(normalized_providers))
    return {"active_provider": active_provider, "providers": normalized_providers}


def _normalize_provider_settings(provider: str, value: object) -> dict[str, str] | None:
    """Normalize a single provider-settings record and fill safe defaults where needed."""

    if not isinstance(value, dict):
        return None
    provider_id = (provider or "").strip().lower()
    if not provider_id:
        return None
    try:
        profile = get_external_provider_profile(provider_id)
    except ValueError:
        return None
    return {
        "provider": provider_id,
        "protocol": str(value.get("protocol", "")).strip() or profile.protocol,
        "model": str(value.get("model", "")).strip() or profile.default_model,
        "base_url": str(value.get("base_url", "")).strip() or profile.default_base_url,
    }
