"""Routing tests for external LM format flow."""

from __future__ import annotations

import unittest
from types import MethodType

from acestep.llm_inference import LLMHandler


class ExternalFormatRoutingTests(unittest.TestCase):
    """Verify external backend routes through the external caption-enhancement path."""

    def test_format_sample_from_input_uses_external_path_without_local_init(self) -> None:
        """External format should not require local 5Hz initialization."""

        handler = LLMHandler.__new__(LLMHandler)
        handler.llm_backend = "external"
        handler.llm_initialized = False

        def fake_external(self, caption, lyrics, user_metadata=None):
            return ({"caption": f"external::{caption}", "lyrics": lyrics}, "external-ok")

        handler._format_sample_from_external_llm = MethodType(fake_external, handler)

        metadata, status = LLMHandler.format_sample_from_input(
            handler,
            caption="Dreamy synth-pop",
            lyrics="[Instrumental]",
        )

        self.assertEqual(status, "external-ok")
        self.assertEqual(metadata["caption"], "external::Dreamy synth-pop")

    def test_format_sample_from_input_keeps_local_guard_for_non_external_backend(self) -> None:
        """Non-external backends should still require local 5Hz initialization."""

        handler = LLMHandler.__new__(LLMHandler)
        handler.llm_backend = "vllm"
        handler.llm_initialized = False

        def fail_if_called(*args, **kwargs):
            raise AssertionError("external format path should not run for non-external backends")

        handler._format_sample_from_external_llm = fail_if_called

        metadata, status = LLMHandler.format_sample_from_input(
            handler,
            caption="Dreamy synth-pop",
            lyrics="[Instrumental]",
        )

        self.assertEqual(metadata, {})
        self.assertEqual(status, "❌ 5Hz LM not initialized. Please initialize it first.")


if __name__ == "__main__":
    unittest.main()
