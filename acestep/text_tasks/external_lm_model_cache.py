"""Cached model-list helpers for external LM provider discovery."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from loguru import logger


def external_lm_model_cache_path() -> Path:
    """Return the user-local JSON cache path for discovered provider models."""

    xdg_data_home = os.getenv("XDG_DATA_HOME", "").strip()
    base = (
        Path(xdg_data_home).expanduser()
        if xdg_data_home
        else Path.home() / ".local" / "share"
    )
    return base / "acestep" / "config" / "external_lm_model_cache.json"


def load_cached_external_models(
    *,
    provider: str,
    protocol: str,
    base_url: str,
) -> list[str] | None:
    """Return cached model identifiers when the entry is present and still fresh."""

    payload = _load_cache_payload()
    entry = payload.get(_cache_key(provider=provider, protocol=protocol, base_url=base_url))
    if not isinstance(entry, dict):
        return None
    ttl_sec = _safe_int_env("ACESTEP_EXTERNAL_MODEL_CACHE_TTL_SEC", default=43200)
    updated_at = float(entry.get("updated_at", 0))
    if ttl_sec >= 0 and (time.time() - updated_at) > ttl_sec:
        return None
    models = entry.get("models")
    if not isinstance(models, list):
        return None
    normalized = [str(model).strip() for model in models if str(model).strip()]
    return normalized or None


def save_cached_external_models(
    *,
    provider: str,
    protocol: str,
    base_url: str,
    models: list[str],
) -> Path:
    """Persist discovered model identifiers for a provider configuration."""

    payload = _load_cache_payload()
    payload[_cache_key(provider=provider, protocol=protocol, base_url=base_url)] = {
        "models": [str(model).strip() for model in models if str(model).strip()],
        "updated_at": time.time(),
    }
    path = external_lm_model_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return path


def invalidate_cached_external_models(
    *,
    provider: str | None = None,
    protocol: str | None = None,
    base_url: str | None = None,
) -> None:
    """Remove matching cached model entries for a provider configuration."""

    path = external_lm_model_cache_path()
    payload = _load_cache_payload()
    filtered = {
        key: value
        for key, value in payload.items()
        if not _matches_invalidation(
            key,
            provider=provider,
            protocol=protocol,
            base_url=base_url,
        )
    }
    if not filtered:
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.error("Failed removing external LM model cache file {}: {}", path, exc)
            return
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(filtered, ensure_ascii=True, indent=2), encoding="utf-8")
        path.chmod(0o600)
    except OSError as exc:
        logger.error("Failed writing external LM model cache file {}: {}", path, exc)
        return


def _load_cache_payload() -> dict[str, dict[str, object]]:
    """Load the full cache payload from disk when available."""

    path = external_lm_model_cache_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _cache_key(*, provider: str, protocol: str, base_url: str) -> str:
    """Build a stable cache key for a provider discovery configuration."""

    return json.dumps(
        [
            (provider or "").strip().lower(),
            (protocol or "").strip().lower(),
            (base_url or "").strip(),
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _safe_int_env(name: str, *, default: int) -> int:
    """Return an integer env var value or the provided default when malformed."""

    raw_value = os.getenv(name, "")
    try:
        return int(raw_value) if raw_value != "" else default
    except (TypeError, ValueError):
        return default


def _matches_invalidation(
    key: str,
    *,
    provider: str | None,
    protocol: str | None,
    base_url: str | None,
) -> bool:
    """Return whether a cached key matches an invalidation filter."""

    try:
        cached_provider, cached_protocol, cached_base_url = json.loads(key)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if provider and cached_provider != provider.strip().lower():
        return False
    if protocol and cached_protocol != protocol.strip().lower():
        return False
    if base_url and cached_base_url != (base_url or "").strip():
        return False
    return True
