"""Tests for external AI protocol helpers."""

from __future__ import annotations

import unittest

from acestep.text_tasks.external_ai_protocols import (
    extract_intent_signal_text,
    normalize_protocol,
    normalize_request_protocol,
    require_message_pair,
)
from acestep.text_tasks.external_ai_types import ExternalAIClientError


class ExternalAIProtocolsTests(unittest.TestCase):
    """Verify protocol normalization and intent-signal helpers stay strict."""

    def test_extract_intent_signal_text_prefers_labelled_fields(self) -> None:
        """Labelled prompt fields should be prioritized for intent heuristics."""

        signal = extract_intent_signal_text(
            "Caption: Dreamy city-pop\nInstrumental: true\nVocal_Language: ja"
        )

        self.assertEqual(signal, "dreamy city-pop\ntrue\nja")

    def test_normalize_request_protocol_rejects_unknown_values(self) -> None:
        """Unsupported protocol values should fail fast."""

        with self.assertRaises(ExternalAIClientError):
            normalize_request_protocol("mystery")

    def test_normalize_protocol_rejects_unknown_response_values(self) -> None:
        """Shared protocol normalization should keep response validation strict."""

        with self.assertRaisesRegex(ExternalAIClientError, "Unsupported external response protocol"):
            normalize_protocol("mystery", purpose="response")

    def test_require_message_pair_requires_system_and_user_messages(self) -> None:
        """Protocol builders should reject incomplete message lists cleanly."""

        with self.assertRaises(ExternalAIClientError):
            require_message_pair([{"role": "system", "content": "s"}])

    def test_require_message_pair_rejects_swapped_roles(self) -> None:
        """Protocol builders should reject malformed role ordering."""

        with self.assertRaises(ExternalAIClientError):
            require_message_pair(
                [
                    {"role": "user", "content": "u"},
                    {"role": "assistant", "content": "a"},
                ]
            )

    def test_require_message_pair_requires_content_fields(self) -> None:
        """Protocol builders should reject role pairs that omit content."""

        with self.assertRaises(ExternalAIClientError):
            require_message_pair([{"role": "system"}, {"role": "user", "content": "u"}])

    def test_require_message_pair_rejects_non_mapping_messages(self) -> None:
        """Protocol builders should fail fast on malformed message container entries."""

        with self.assertRaises(ExternalAIClientError):
            require_message_pair(["system", {"role": "user", "content": "u"}])

    def test_require_message_pair_rejects_empty_content(self) -> None:
        """Protocol builders should reject empty string content fields."""

        with self.assertRaises(ExternalAIClientError):
            require_message_pair(
                [
                    {"role": "system", "content": ""},
                    {"role": "user", "content": "u"},
                ]
            )


if __name__ == "__main__":
    unittest.main()
