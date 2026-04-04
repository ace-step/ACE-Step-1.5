"""Tests for external LM format-mode request helpers."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from acestep.text_tasks.external_ai_types import ExternalAIClientError
from acestep.text_tasks.external_lm_format_client import (
    request_external_format_plan,
    resolve_external_api_key,
)


class _FakeResponse:
    """Minimal context-manager wrapper for urlopen payloads."""

    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class ExternalLmFormatClientTests(unittest.TestCase):
    """Verify external format-mode requests parse and recover safely."""

    def test_resolve_external_api_key_uses_provider_env_fallback(self) -> None:
        """Missing explicit keys should fall back to the provider-specific env var."""

        with patch.dict(os.environ, {"ACESTEP_OPENAI_API_KEY": "env-secret"}, clear=True):
            self.assertEqual(
                resolve_external_api_key(provider="openai", api_key=""),
                "env-secret",
            )

    @patch("acestep.text_tasks.external_lm_credentials.resolve_runtime_passphrase")
    @patch("acestep.text_tasks.external_lm_credentials.EncryptedSecretStore")
    def test_resolve_external_api_key_uses_secure_store_fallback(
        self,
        secret_store_cls,
        resolve_passphrase_mock,
    ) -> None:
        """Missing explicit/env keys should fall back to the provider secure store."""

        secret_store = secret_store_cls.return_value
        secret_store.load.return_value = "stored-secret"
        resolve_passphrase_mock.return_value = "passphrase"

        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "acestep.text_tasks.external_lm_credentials.EncryptedSecretStore.resolve_existing_default_path",
                return_value=type("FakePath", (), {"exists": lambda self: True})(),
            ):
                self.assertEqual(
                    resolve_external_api_key(provider="openai", api_key=""),
                    "stored-secret",
                )
        secret_store.load.assert_called_once_with(passphrase="passphrase")

    @patch("acestep.text_tasks.external_lm_format_client.urllib_request.urlopen")
    def test_request_external_format_plan_parses_openai_response(self, urlopen_mock) -> None:
        """OpenAI-style responses should parse into a normalized plan object."""

        urlopen_mock.return_value = _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "caption": "Expanded synth-pop arrangement with airy vocals",
                                    "lyrics": "[Verse]\nGlow tonight",
                                    "bpm": 118,
                                    "duration": 42,
                                    "key_scale": "C Minor",
                                    "time_signature": "4/4",
                                    "vocal_language": "en",
                                    "instrumental": False,
                                }
                            )
                        }
                    }
                ]
            }
        )

        plan = request_external_format_plan(
            provider="openai",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1/chat/completions",
            api_key="sk-test",
            caption="Dreamy synth-pop",
            lyrics="[Verse]\nGlow tonight",
            user_metadata={"bpm": 118},
        )

        self.assertEqual(plan.caption, "Expanded synth-pop arrangement with airy vocals")
        self.assertEqual(plan.bpm, 118)
        self.assertEqual(plan.time_signature, "4/4")

    @patch("acestep.text_tasks.external_lm_format_client.urllib_request.urlopen")
    def test_request_external_format_plan_falls_back_after_two_echoes(self, urlopen_mock) -> None:
        """Two weak echo responses should trigger the local fallback caption."""

        echoed_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "caption": "Dreamy synth-pop",
                                "lyrics": "[Instrumental]",
                                "bpm": 118,
                                "duration": 60,
                                "key_scale": "C Minor",
                                "time_signature": "4/4",
                                "vocal_language": "en",
                                "instrumental": True,
                            }
                        )
                    }
                }
            ]
        }
        urlopen_mock.side_effect = [
            _FakeResponse(echoed_payload),
            _FakeResponse(echoed_payload),
        ]

        plan = request_external_format_plan(
            provider="openai",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1/chat/completions",
            api_key="sk-test",
            caption="Dreamy synth-pop",
            lyrics="",
            user_metadata={"bpm": 118},
        )

        self.assertNotEqual(plan.caption, "Dreamy synth-pop")
        self.assertIn("Dreamy synth-pop", plan.caption)
        self.assertIn("118 BPM", plan.caption)
        self.assertEqual(plan.lyrics, "[Instrumental]")

    @patch("acestep.text_tasks.external_lm_format_client.urllib_request.urlopen")
    def test_request_external_format_plan_keeps_first_plan_if_retry_fails(self, urlopen_mock) -> None:
        """A retry failure should not discard the first successful plan."""

        first_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "caption": "Dreamy synth-pop",
                                "lyrics": "[Verse]\nGlow tonight",
                                "bpm": 118,
                                "duration": 42,
                                "key_scale": "C Minor",
                                "time_signature": "4/4",
                                "vocal_language": "en",
                                "instrumental": False,
                            }
                        )
                    }
                }
            ]
        }
        urlopen_mock.side_effect = [
            _FakeResponse(first_payload),
            TimeoutError("retry timed out"),
        ]

        plan = request_external_format_plan(
            provider="openai",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1/chat/completions",
            api_key="sk-test",
            caption="Dreamy synth-pop",
            lyrics="[Verse]\nGlow tonight",
            user_metadata={"bpm": 118},
        )

        self.assertNotEqual(plan.caption, "")
        self.assertIn("Dreamy synth-pop", plan.caption)
        self.assertEqual(plan.lyrics, "[Verse]\nGlow tonight")
        self.assertEqual(plan.bpm, 118)

    def test_request_external_format_plan_requires_api_key_when_provider_needs_one(self) -> None:
        """Providers with required credentials should fail fast without a key."""

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ExternalAIClientError, "Missing API key"):
                request_external_format_plan(
                    provider="openai",
                    model="gpt-4o-mini",
                    base_url="https://api.openai.com/v1/chat/completions",
                    api_key="",
                    caption="Dreamy synth-pop",
                    lyrics="",
                    user_metadata={},
                )


if __name__ == "__main__":
    unittest.main()
