"""Tests for external LM provider profile helpers."""

from __future__ import annotations

import unittest

from acestep.text_tasks.external_lm_providers import (
    CUSTOM_BASE_URL_PRESET,
    get_external_base_url_preset_choices,
    get_external_base_url_preset_value,
    get_external_provider_profile,
)


class ExternalLmProvidersTests(unittest.TestCase):
    """Verify provider lookup and base-URL preset helpers stay explicit."""

    def test_get_external_provider_profile_rejects_unknown_provider(self) -> None:
        """Unknown providers should fail fast instead of silently defaulting."""

        with self.assertRaises(ValueError):
            get_external_provider_profile("mystery")

    def test_base_url_preset_helpers_use_shared_custom_token(self) -> None:
        """Custom base-URL selection should use the centralized custom token."""

        choices = get_external_base_url_preset_choices("ollama")
        value = get_external_base_url_preset_value("ollama", "http://example.invalid")

        self.assertIn(("Custom", CUSTOM_BASE_URL_PRESET), choices)
        self.assertEqual(value, CUSTOM_BASE_URL_PRESET)


if __name__ == "__main__":
    unittest.main()
