"""HTTP helpers for external LM requests."""

from __future__ import annotations

import json
from typing import Any
from urllib import error as urllib_error
from urllib.parse import urlparse
from urllib import request as urllib_request

from .external_ai_request_helpers import build_http_error_guidance
from .external_ai_types import ExternalAIClientError

_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def post_external_request(
    *,
    base_url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_sec: int,
    provider: str,
    model: str,
    urlopen_impl=None,
) -> str:
    """POST JSON to an external provider and return the raw response body."""

    _validate_external_base_url(base_url=base_url, provider=provider)
    if urlopen_impl is None:
        urlopen_impl = urllib_request.urlopen
    req = urllib_request.Request(
        url=base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen_impl(req, timeout=timeout_sec) as response:
            return response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
        guidance = build_http_error_guidance(
            detail=detail,
            model=model,
            base_url=base_url,
        )
        raise ExternalAIClientError(
            f"HTTP {exc.code} from external provider '{provider}'.{guidance}"
        ) from exc
    except urllib_error.URLError as exc:
        raise ExternalAIClientError(
            f"Network error while contacting external provider '{provider}': {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise ExternalAIClientError(
            f"Timed out while contacting external provider '{provider}'."
        ) from exc


def _validate_external_base_url(*, base_url: str, provider: str) -> None:
    """Reject non-network or malformed provider endpoints before dispatch."""

    parsed = urlparse(base_url)
    scheme = (parsed.scheme or "").strip().lower()
    if scheme not in _ALLOWED_URL_SCHEMES:
        raise ExternalAIClientError(
            f"Invalid URL scheme '{parsed.scheme}' for external provider '{provider}'. "
            "Only http and https are allowed."
        )
    if not parsed.netloc:
        raise ExternalAIClientError(
            f"Invalid base URL for external provider '{provider}': missing network location."
        )
