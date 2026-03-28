"""Tests for provider-specific external AI response parsing helpers."""

from __future__ import annotations

import unittest

from acestep.text_tasks.external_ai_response_parsing import (
    extract_protocol_message_content,
    parse_plan_from_content,
)
from acestep.text_tasks.external_ai_types import ExternalAIClientError


class ExternalAIResponseParsingTests(unittest.TestCase):
    """Verify protocol-specific content extraction handles malformed payloads safely."""

    def test_extract_protocol_message_content_rejects_empty_openai_choices(self) -> None:
        """OpenAI-style parsing should fail cleanly when no choices are present."""

        with self.assertRaisesRegex(ExternalAIClientError, "missing choices"):
            extract_protocol_message_content(
                raw_response='{"choices":[]}',
                protocol="openai_chat",
            )

    def test_extract_protocol_message_content_rejects_unknown_protocol(self) -> None:
        """Unknown response protocols should fail fast instead of guessing a shape."""

        with self.assertRaisesRegex(ExternalAIClientError, "Unsupported external response protocol"):
            extract_protocol_message_content(
                raw_response='{"choices":[{"message":{"content":"ok"}}]}',
                protocol="mystery_protocol",
            )

    def test_parse_plan_from_content_accepts_key_aliases(self) -> None:
        """Alias field names should normalize into the canonical plan object."""

        plan = parse_plan_from_content(
            '{"caption":"Glow","lyrics":"line","keyscale":"C Major","timesignature":"4/4","instrumental":false}'
        )

        self.assertEqual(plan.key_scale, "C Major")
        self.assertEqual(plan.time_signature, "4/4")

    def test_parse_plan_from_content_rounds_decimal_bpm_values(self) -> None:
        """Decimal BPM values should round instead of silently truncating."""

        plan = parse_plan_from_content(
            '{"caption":"Glow","lyrics":"line","bpm":"118.7","instrumental":false}'
        )

        self.assertEqual(plan.bpm, 119)

    def test_extract_protocol_message_content_rejects_non_mapping_openai_message(self) -> None:
        """OpenAI-style parsing should reject malformed non-dict message payloads."""

        with self.assertRaisesRegex(ExternalAIClientError, "Invalid OpenAI-style"):
            extract_protocol_message_content(
                raw_response='{"choices":[{"message":"bad"}]}',
                protocol="openai_chat",
            )

    def test_extract_protocol_message_content_rejects_non_text_openai_content(self) -> None:
        """OpenAI-style parsing should reject malformed non-text content payloads."""

        with self.assertRaisesRegex(ExternalAIClientError, "Invalid OpenAI-style"):
            extract_protocol_message_content(
                raw_response='{"choices":[{"message":{"content":{"text":"bad"}}}]}',
                protocol="openai_chat",
            )


if __name__ == "__main__":
    unittest.main()
