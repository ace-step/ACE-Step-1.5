"""Provider-aware model discovery helpers for external LM setup."""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any
from urllib import error, parse, request


class ExternalModelDiscoveryError(RuntimeError):
    """Raised when model discovery fails for all candidate endpoints."""


def discover_external_models(
    *,
    provider: str,
    protocol: str,
    base_url: str,
    api_key: str,
    timeout_sec: int = 20,
) -> list[str]:
    """Discover model identifiers from a provider's model-list endpoint."""

    parsed_base_url = parse.urlparse(base_url.strip())
    if parsed_base_url.scheme and parsed_base_url.scheme not in {"http", "https"}:
        raise ExternalModelDiscoveryError(
            f"Unsupported URL scheme for model discovery: {parsed_base_url.scheme}"
        )

    candidate_urls = _build_model_list_urls(
        provider=provider,
        protocol=protocol,
        base_url=base_url,
    )
    if not candidate_urls:
        raise ExternalModelDiscoveryError(
            "No model-discovery endpoint could be derived from base URL."
        )

    headers = _build_auth_headers(protocol=protocol, api_key=api_key)
    failures: list[str] = []

    for url in candidate_urls:
        parsed_url = parse.urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            failures.append(f"{url} -> unsupported URL scheme")
            continue
        req = request.Request(url=url, headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=timeout_sec) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            failures.append(f"{url} -> HTTP {exc.code} {detail[:120]}")
            continue
        except (error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            failures.append(f"{url} -> {exc}")
            continue

        models = _extract_model_ids(payload)
        if models:
            return models
        failures.append(f"{url} -> no models found in response")

    raise ExternalModelDiscoveryError("; ".join(failures[:3]))


def _build_model_list_urls(*, provider: str, protocol: str, base_url: str) -> list[str]:
    """Build ordered candidate model-list URLs from a provider endpoint."""

    root = base_url.strip().rstrip("/")
    if not root:
        return []

    candidates: list[str] = []
    if root.endswith("/models") or root.endswith("/api/tags"):
        candidates.append(root)
    if "/chat/completions" in root:
        candidates.append(root.replace("/chat/completions", "/models"))
    if root.endswith("/messages"):
        candidates.append(root[: -len("/messages")] + "/models")
    if root.endswith("/completions"):
        candidates.append(root[: -len("/completions")] + "/models")
    if root.endswith("/v1"):
        candidates.append(f"{root}/models")
    if root.endswith("/v4"):
        candidates.append(f"{root}/models")

    protocol_token = (protocol or "").strip().lower()
    provider_token = (provider or "").strip().lower()
    if protocol_token == "anthropic_messages" and "/models" not in root and "/v1/" in root:
        prefix = root.split("/v1/", 1)[0]
        candidates.append(f"{prefix}/v1/models")

    if provider_token == "ollama":
        if "/v1/" in root:
            prefix = root.split("/v1/", 1)[0]
            candidates.append(f"{prefix}/api/tags")
            candidates.append(f"{prefix}/v1/models")
        else:
            candidates.append(f"{root}/api/tags")
            candidates.append(f"{root}/v1/models")

    unique = OrderedDict((url, None) for url in candidates if url)
    return list(unique.keys())


def _build_auth_headers(*, protocol: str, api_key: str) -> dict[str, str]:
    """Build auth headers for model-discovery requests."""

    headers = {"Content-Type": "application/json"}
    if (protocol or "").strip().lower() == "anthropic_messages":
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        return headers

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _extract_model_ids(payload: Any) -> list[str]:
    """Extract model IDs from common provider response payloads."""

    if not isinstance(payload, dict):
        return []

    ids: OrderedDict[str, None] = OrderedDict()
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            _add_model_id(ids, item)

    models = payload.get("models")
    if isinstance(models, list):
        for item in models:
            _add_model_id(ids, item)

    if not ids and isinstance(payload.get("id"), str):
        _add_model_id(ids, payload.get("id"))

    return list(ids.keys())


def _add_model_id(collector: OrderedDict[str, None], item: Any) -> None:
    """Normalize and add a model ID from a response item."""

    if isinstance(item, str):
        value = item.strip()
        if value:
            collector[value] = None
        return

    if not isinstance(item, dict):
        return

    for key in ("id", "name", "model"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            collector[value.strip()] = None
            return
