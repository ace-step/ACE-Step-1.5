"""Shared test helpers for API route tests.

Provides common utilities duplicated across 18+ test files:
- ``wrap_response`` -- build an API-compatible response envelope
- ``noop_verify_api_key`` -- no-op auth dependency for unit tests
- ``bearer_verify_api_key`` -- bearer-token auth dependency for HTTP integration tests
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Header, HTTPException


def wrap_response(
    data: Any, code: int = 200, error: Optional[str] = None
) -> Dict[str, Any]:
    """Return an ``api_server``-compatible response envelope dict."""
    return {"data": data, "code": code, "error": error}


async def noop_verify_api_key(_: Optional[str] = None) -> None:
    """No-op auth dependency for unit tests."""
    return None


async def bearer_verify_api_key(
    authorization: Optional[str] = Header(None),
) -> None:
    """Require a fixed bearer token for HTTP integration tests."""
    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")
