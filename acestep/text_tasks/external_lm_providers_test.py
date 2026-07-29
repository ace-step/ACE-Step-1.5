"""Tests for external LM provider profile helpers."""

from __future__ import annotations

import unittest

from acestep.text_tasks.external_lm_providers import (
    CUSTOM_BASE_URL_PRESET,
    build_external_model_choice,
    get_external_base_url_preset_choices,
    get_external_base_url_preset_value,
    get_external_provider_choices,
    get_external_provider_profile,
)


class ExternalLmProvidersTests(unittest.TestCase):
    """Verify provider lookup and base-URL preset helpers stay explicit."""

    def test_get_external_provider_profile_returns_minimax_defaults(self) -> None:
        """MiniMax should expose OpenAI-compatible chat defaults."""

        profile = get_external_provider_profile("minimax")

        self.assertEqual(profile.protocol, "openai_chat")
        self.assertEqual(profile.default_model, "MiniMax-M3")
        self.assertEqual(
            profile.default_base_url,
            "https://api.minimax.io/v1/chat/completions",
        )
        self.assertEqual(profile.api_key_env, "ACESTEP_MINIMAX_API_KEY")

    def test_get_external_provider_profile_returns_minimax_anthropic_defaults(self) -> None:
        """MiniMax also exposes an Anthropic Messages provider option."""

        profile = get_external_provider_profile("minimax_anthropic")

        self.assertEqual(profile.protocol, "anthropic_messages")
        self.assertEqual(profile.default_model, "MiniMax-M3")
        self.assertEqual(
            profile.default_base_url,
            "https://api.minimax.io/anthropic/v1/messages",
        )
        self.assertEqual(profile.api_key_env, "ACESTEP_MINIMAX_API_KEY")

    def test_minimax_base_url_presets_cover_global_and_china(self) -> None:
        """MiniMax presets should offer both the global and Mainland China hosts."""

        openai_presets = dict(get_external_base_url_preset_choices("minimax"))
        anthropic_presets = dict(get_external_base_url_preset_choices("minimax_anthropic"))

        self.assertIn("https://api.minimax.io/v1/chat/completions", openai_presets.values())
        self.assertIn("https://api.minimaxi.com/v1/chat/completions", openai_presets.values())
        self.assertIn(
            "https://api.minimax.io/anthropic/v1/messages", anthropic_presets.values()
        )
        self.assertIn(
            "https://api.minimaxi.com/anthropic/v1/messages", anthropic_presets.values()
        )

    def test_get_external_provider_profile_rejects_unknown_provider(self) -> None:
        """Unknown providers should fail fast instead of silently defaulting."""

        with self.assertRaises(ValueError):
            get_external_provider_profile("mystery")

    def test_get_external_provider_choices_includes_minimax(self) -> None:
        """Provider choices should expose both MiniMax options to the picker."""

        choices = get_external_provider_choices()

        self.assertIn(("MiniMax", "minimax"), choices)
        self.assertIn(("MiniMax (Anthropic API)", "minimax_anthropic"), choices)

    def test_build_external_model_choice_defaults_minimax_model(self) -> None:
        """Missing MiniMax model names should fall back to the provider default."""

        choice = build_external_model_choice("minimax", "")

        self.assertEqual(choice, "external:minimax:MiniMax-M3")

    def test_base_url_preset_helpers_use_shared_custom_token(self) -> None:
        """Custom base-URL selection should use the centralized custom token."""

        choices = get_external_base_url_preset_choices("ollama")
        value = get_external_base_url_preset_value("ollama", "http://example.invalid")

        self.assertIn(("Custom", CUSTOM_BASE_URL_PRESET), choices)
        self.assertEqual(value, CUSTOM_BASE_URL_PRESET)


if __name__ == "__main__":
    unittest.main()
