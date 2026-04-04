"""Focused tests for the external LM setup accordion contract."""

from __future__ import annotations

import unittest

import gradio as gr

from acestep.ui.gradio.interfaces.generation_advanced_primary_controls import (
    build_external_lm_controls,
)


class ExternalLmConfigBuilderTests(unittest.TestCase):
    """Verify the external LM accordion exposes the expected setup controls."""

    def test_build_external_lm_controls_returns_full_setup_surface(self) -> None:
        """The builder should expose fetch/save/test/doctor controls plus status."""

        with gr.Blocks():
            components = build_external_lm_controls(
                service_pre_initialized=True,
                params={"backend": "external"},
            )

        expected_keys = {
            "external_llm_accordion",
            "external_llm_provider",
            "external_llm_base_url_preset",
            "external_llm_model",
            "external_llm_fetch_models_btn",
            "external_llm_base_url",
            "external_llm_api_key",
            "external_llm_status",
            "external_llm_save_btn",
            "external_llm_test_btn",
            "external_llm_doctor_btn",
        }
        self.assertTrue(expected_keys.issubset(components.keys()))
        self.assertTrue(components["external_llm_model"].allow_custom_value)
        self.assertEqual(components["external_llm_api_key"].type, "password")
        self.assertIn("external-lm-api-key", components["external_llm_api_key"].elem_classes)


if __name__ == "__main__":
    unittest.main()
