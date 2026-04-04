"""Tests for external LM HTTP transport validation."""

from __future__ import annotations

import unittest

from acestep.text_tasks.external_ai_types import ExternalAIClientError
from acestep.text_tasks.external_lm_http_client import post_external_request


class ExternalLmHttpClientTests(unittest.TestCase):
    """Verify the HTTP client rejects unsafe or malformed endpoints."""

    def test_post_external_request_rejects_non_http_scheme(self) -> None:
        """Only http/https provider endpoints should be accepted."""

        with self.assertRaisesRegex(ExternalAIClientError, "Only http and https are allowed"):
            post_external_request(
                base_url="file:///etc/passwd",
                headers={},
                payload={},
                timeout_sec=5,
                provider="openai",
                model="gpt-4.1-mini",
                urlopen_impl=lambda *_args, **_kwargs: None,
            )

    def test_post_external_request_rejects_missing_netloc(self) -> None:
        """Malformed endpoints with no network location should fail fast."""

        with self.assertRaisesRegex(ExternalAIClientError, "missing network location"):
            post_external_request(
                base_url="https:///v1/chat/completions",
                headers={},
                payload={},
                timeout_sec=5,
                provider="openai",
                model="gpt-4.1-mini",
                urlopen_impl=lambda *_args, **_kwargs: None,
            )


if __name__ == "__main__":
    unittest.main()
