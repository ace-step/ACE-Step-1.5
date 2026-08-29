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

    def test_get_external_provider_profile_returns_forge_defaults(self) -> None:
        """Forge should use its dedicated OpenAI-compatible defaults."""

        profile = get_external_provider_profile("forge")

        self.assertEqual(profile.protocol, "openai_chat")
        self.assertEqual(profile.default_model, "OpenAI/gpt-4o-mini")
        self.assertEqual(
            profile.default_base_url,
            "https://api.forge.tensorblock.co/v1/chat/completions",
        )
        self.assertEqual(profile.api_key_env, "FORGE_API_KEY")

    def test_get_external_provider_profile_rejects_unknown_provider(self) -> None:
        """Unknown providers should fail fast instead of silently defaulting."""

        with self.assertRaises(ValueError):
            get_external_provider_profile("mystery")

    def test_get_external_provider_choices_includes_forge(self) -> None:
        """Provider choices should expose Forge to the external LM picker."""

        choices = get_external_provider_choices()

        self.assertIn(("Forge", "forge"), choices)

    def test_build_external_model_choice_defaults_forge_model(self) -> None:
        """Missing Forge model names should fall back to the provider default."""

        choice = build_external_model_choice("forge", "")

        self.assertEqual(choice, "external:forge:OpenAI/gpt-4o-mini")

    def test_base_url_preset_helpers_use_shared_custom_token(self) -> None:
        """Custom base-URL selection should use the centralized custom token."""

        choices = get_external_base_url_preset_choices("ollama")
        value = get_external_base_url_preset_value("ollama", "http://example.invalid")

        self.assertIn(("Custom", CUSTOM_BASE_URL_PRESET), choices)
        self.assertEqual(value, CUSTOM_BASE_URL_PRESET)


if __name__ == "__main__":
    unittest.main()
