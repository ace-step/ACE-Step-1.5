"""Credential helpers for external LM provider integrations."""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from .external_lm_providers import get_external_provider_profile
from .passphrase_store import resolve_runtime_passphrase
from .secure_secret_store import EncryptedSecretStore, SecretStoreError


def resolve_external_api_key(*, provider: str, api_key: str) -> str:
    """Return the explicit API key or the provider-scoped env fallback."""

    profile = get_external_provider_profile(provider)
    explicit_key = (api_key or "").strip()
    if explicit_key:
        return explicit_key
    env_key = os.environ.get(profile.api_key_env, "").strip()
    if env_key:
        return env_key
    return _load_external_api_key_from_secret_store(profile)


def resolve_external_secret_store_path(profile) -> Path:
    """Return the configured or default encrypted-secret path for a provider."""

    configured_path = os.environ.get(profile.secret_path_env, "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return EncryptedSecretStore.resolve_existing_default_path(profile.secret_file_name)


def has_external_secret_store_value(profile) -> bool:
    """Return whether the provider has a saved secret in file or native keyring."""

    secret_path = resolve_external_secret_store_path(profile)
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


def _load_external_api_key_from_secret_store(profile) -> str:
    """Load an API key from the provider-specific secure secret store when present."""

    secret_path = resolve_external_secret_store_path(profile)
    if secret_path is None or not secret_path.exists():
        return ""

    try:
        secret_store = EncryptedSecretStore(secret_path=secret_path)
        return secret_store.load(passphrase=(resolve_runtime_passphrase() or "").strip()).strip()
    except SecretStoreError as exc:
        logger.debug(
            "Could not load secure API key for provider '{}': {}",
            profile.provider_id,
            exc,
        )
        return ""
