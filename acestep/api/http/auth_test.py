"""Unit tests for API-key authentication helpers."""

from __future__ import annotations

import asyncio
import unittest

from fastapi import HTTPException

from acestep.api.http.auth import set_api_key, verify_api_key, verify_token_from_request


class AuthHelpersTests(unittest.TestCase):
    """Behavior tests for API-key state and token/header validation helpers."""

    def setUp(self) -> None:
        """Reset auth state before each test."""

        set_api_key(None)

    def tearDown(self) -> None:
        """Reset auth state after each test."""

        set_api_key(None)

    def test_verify_token_returns_none_when_auth_is_disabled(self) -> None:
        """Token verification should allow requests when no API key is configured."""

        token = verify_token_from_request(body={}, authorization=None)
        self.assertIsNone(token)
        asyncio.run(verify_api_key(authorization=None))

    def test_verify_token_accepts_ai_token_in_body(self) -> None:
        """Body ai_token should be accepted when it matches configured API key."""

        set_api_key("secret")
        token = verify_token_from_request(body={"ai_token": "secret"}, authorization=None)
        self.assertEqual("secret", token)

    def test_verify_token_rejects_invalid_ai_token(self) -> None:
        """Body ai_token mismatch should return the legacy 401 detail message."""

        set_api_key("secret")
        with self.assertRaises(HTTPException) as ctx:
            verify_token_from_request(body={"ai_token": "wrong"}, authorization=None)
        self.assertEqual(401, ctx.exception.status_code)
        self.assertEqual("Invalid ai_token", ctx.exception.detail)

    def test_verify_token_accepts_bearer_header(self) -> None:
        """Authorization header should support Bearer-prefix token values."""

        set_api_key("secret")
        token = verify_token_from_request(body={}, authorization="Bearer secret")
        self.assertEqual("secret", token)

    def test_verify_token_requires_token_when_auth_enabled(self) -> None:
        """Missing body token and header should preserve existing 401 error message."""

        set_api_key("secret")
        with self.assertRaises(HTTPException) as ctx:
            verify_token_from_request(body={}, authorization=None)
        self.assertEqual(401, ctx.exception.status_code)
        self.assertEqual("Missing ai_token or Authorization header", ctx.exception.detail)

    def test_verify_api_key_rejects_invalid_or_missing_header(self) -> None:
        """Header-only verifier should preserve missing/invalid API key errors."""

        set_api_key("secret")

        with self.assertRaises(HTTPException) as missing_ctx:
            asyncio.run(verify_api_key(authorization=None))
        self.assertEqual(401, missing_ctx.exception.status_code)
        self.assertEqual("Missing Authorization header", missing_ctx.exception.detail)

        with self.assertRaises(HTTPException) as invalid_ctx:
            asyncio.run(verify_api_key(authorization="Bearer wrong"))
        self.assertEqual(401, invalid_ctx.exception.status_code)
        self.assertEqual("Invalid API key", invalid_ctx.exception.detail)

        asyncio.run(verify_api_key(authorization="Bearer secret"))


if __name__ == "__main__":
    unittest.main()
