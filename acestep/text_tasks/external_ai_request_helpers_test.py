"""Tests for external AI request helper edge cases."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from acestep.text_tasks.external_ai_request_helpers import (
    build_http_error_guidance,
    build_intent_specific_guidance,
    build_planning_messages,
    build_request_for_protocol,
    resolve_max_tokens_for_task_focus,
    build_task_focus_guidance,
)
from acestep.text_tasks.external_ai_types import ExternalAIClientError


class ExternalAIRequestHelpersTests(unittest.TestCase):
    """Verify HTTP error guidance handles provider payload variants."""

    def test_format_guidance_requests_linear_arrangement_caption(self) -> None:
        """Format guidance should ask for a linear arrangement-style caption."""

        guidance = build_task_focus_guidance(task_focus="format")
        messages = build_planning_messages("Tropical funk", task_focus="format")

        self.assertIn("linear narrative", guidance)
        self.assertIn("core instrumentation", guidance)
        self.assertIn("song progresses", guidance)
        self.assertIn("arrangement", messages[0]["content"])
        self.assertIn("under 200 words", guidance)
        self.assertIn("JSON boolean", messages[0]["content"])
        self.assertIn("Start the response with '{'", messages[0]["content"])

    def test_intent_specific_guidance_honors_no_vocals_requests(self) -> None:
        """Instrumental and no-vocals prompts should add stricter anti-vocal guidance."""

        guidance = build_intent_specific_guidance("Ambient choir soundscape, no drums, no vocals")

        self.assertIn("Do not introduce lead vocals", guidance)
        self.assertIn("vocal harmonies", guidance)
        self.assertIn("choral textures", guidance)
        self.assertIn("Set instrumental to true", guidance)

    def test_intent_specific_guidance_ignores_instrumental_lyrics_placeholder(self) -> None:
        """A lyrics placeholder should not override a caption that explicitly asks for vocals."""

        guidance = build_intent_specific_guidance(
            "Caption: tropical funk female vocals\nLyrics: [Instrumental]\nbpm: 125"
        )

        self.assertEqual(guidance, "")

    def test_intent_specific_guidance_honors_explicit_instrumental_field(self) -> None:
        """An explicit instrumental field should force no-vocals guidance."""

        guidance = build_intent_specific_guidance(
            "Caption: tropical funk female vocals\nInstrumental: true"
        )

        self.assertIn("Set instrumental to true", guidance)

    def test_intent_specific_guidance_does_not_treat_instrumental_caption_word_as_flag(self) -> None:
        """Freeform captions should not infer instrumental mode from descriptive wording."""

        guidance = build_intent_specific_guidance("Caption: instrumental intro with female vocals")

        self.assertEqual(guidance, "")

    def test_intent_specific_guidance_does_not_treat_wordless_vocalise_as_instrumental(self) -> None:
        """Descriptive wordless vocal prompts should not be reclassified as no-vocals."""

        guidance = build_intent_specific_guidance("Caption: wordless choir and vocalise textures")

        self.assertEqual(guidance, "")

    def test_build_http_error_guidance_accepts_string_error_shape(self) -> None:
        """Provider payloads with a string ``error`` field should not crash parsing."""

        guidance = build_http_error_guidance(
            detail='{"error":"model requires more system memory"}',
            model="qwen3:8b",
            base_url="http://127.0.0.1:11434/api/generate",
        )

        self.assertEqual(guidance, "")

    def test_resolve_max_tokens_for_format_uses_tighter_budget(self) -> None:
        """Format-mode calls should use a smaller completion budget by default."""

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ACESTEP_EXTERNAL_FORMAT_MAX_TOKENS", None)
            self.assertEqual(resolve_max_tokens_for_task_focus("format"), 768)

    def test_build_request_for_protocol_accepts_task_specific_max_tokens(self) -> None:
        """OpenAI-compatible payloads should honor an explicit max-token override."""

        payload, _headers = build_request_for_protocol(
            protocol="openai_chat",
            provider="ollama",
            api_key="",
            model="qwen3:4b",
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            base_url="http://127.0.0.1:11434/v1/chat/completions",
            max_tokens=768,
        )

        self.assertEqual(payload["max_tokens"], 768)

    def test_build_request_for_protocol_requests_json_output_for_openai_format(self) -> None:
        """OpenAI format-mode requests should force JSON output."""

        payload, _headers = build_request_for_protocol(
            protocol="openai_chat",
            provider="openai",
            api_key="test-key",
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            base_url="https://api.openai.com/v1/chat/completions",
            max_tokens=768,
            require_json_output=True,
        )

        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["stop"], ["```"])
        self.assertNotIn("thinking", payload)

    def test_build_request_for_protocol_disables_zai_thinking_and_requests_json(self) -> None:
        """Z.ai format calls should disable thinking and request JSON output."""

        payload, _headers = build_request_for_protocol(
            protocol="openai_chat",
            provider="zai",
            api_key="test-key",
            model="glm-5",
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            base_url="https://api.z.ai/api/coding/paas/v4/chat/completions",
            max_tokens=768,
            disable_thinking=True,
            require_json_output=True,
        )

        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["stop"], ["```"])

    def test_build_request_for_protocol_leaves_claude_without_thinking_flags(self) -> None:
        """Claude format-mode requests should stay on the default non-thinking path."""

        payload, _headers = build_request_for_protocol(
            protocol="anthropic_messages",
            provider="claude",
            api_key="test-key",
            model="claude-sonnet-4-5",
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            base_url="https://api.anthropic.com/v1/messages",
            max_tokens=768,
            disable_thinking=True,
            require_json_output=True,
        )

        self.assertNotIn("thinking", payload)
        self.assertNotIn("response_format", payload)
        self.assertEqual(payload["stop_sequences"], ["```"])

    def test_build_request_for_protocol_requires_two_messages_for_anthropic(self) -> None:
        """Anthropic payload building should reject malformed message lists cleanly."""

        with self.assertRaises(ExternalAIClientError) as exc:
            build_request_for_protocol(
                protocol="anthropic_messages",
                provider="claude",
                api_key="test-key",
                model="claude-sonnet-4-5",
                messages=[{"role": "system", "content": "s"}],
                base_url="https://api.anthropic.com/v1/messages",
            )

        self.assertIn("requires both system and user messages", str(exc.exception))

    def test_build_request_for_protocol_requires_system_then_user_roles_for_anthropic(self) -> None:
        """Anthropic payload building should reject swapped or malformed role pairs."""

        with self.assertRaises(ExternalAIClientError) as exc:
            build_request_for_protocol(
                protocol="anthropic_messages",
                provider="claude",
                api_key="test-key",
                model="claude-sonnet-4-5",
                messages=[{"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}],
                base_url="https://api.anthropic.com/v1/messages",
            )

        self.assertIn("system message followed by a user message", str(exc.exception))

    def test_build_request_for_protocol_rejects_unknown_protocol(self) -> None:
        """Unknown request protocols should fail fast instead of falling through silently."""

        with self.assertRaises(ExternalAIClientError) as exc:
            build_request_for_protocol(
                protocol="mystery_protocol",
                provider="openai",
                api_key="test-key",
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
                base_url="https://api.openai.com/v1/chat/completions",
            )

        self.assertIn("Unsupported external request protocol", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
