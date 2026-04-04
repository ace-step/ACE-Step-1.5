"""Unit tests for external LM setup actions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from acestep.text_tasks.external_lm_providers import get_external_provider_profile
from acestep.ui.gradio.events.generation import external_lm_setup
from acestep.ui.gradio.events.generation import external_lm_setup_support


class ExternalLmSetupActionTests(unittest.TestCase):
    """Verify setup helpers restore and persist the expected UI state."""

    @patch("acestep.ui.gradio.events.generation.external_lm_setup.load_cached_external_models")
    @patch("acestep.ui.gradio.events.generation.external_lm_setup.load_external_lm_runtime_settings")
    def test_hydrate_external_lm_setup_fields_returns_saved_values_and_preset(
        self,
        load_runtime_mock,
        load_cached_models_mock,
    ) -> None:
        """Provider hydration should restore saved model/base URL and preset choices."""

        load_runtime_mock.return_value = {
            "provider": "openai",
            "protocol": "openai_chat",
            "model": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1/chat/completions",
        }
        load_cached_models_mock.return_value = ["gpt-4.1-mini", "gpt-4o-mini"]

        model_update, base_url_update, preset_update, status_update = (
            external_lm_setup.hydrate_external_lm_setup_fields("openai")
        )

        self.assertEqual(model_update["value"], "gpt-4.1-mini")
        self.assertIn("gpt-4o-mini", model_update["choices"])
        self.assertEqual(base_url_update["value"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(
            preset_update["value"],
            "https://api.openai.com/v1/chat/completions",
        )
        self.assertEqual(status_update["value"], "")

    @patch("acestep.ui.gradio.events.generation.external_lm_setup.save_cached_external_models")
    @patch("acestep.ui.gradio.events.generation.external_lm_setup.discover_provider_models")
    def test_fetch_external_lm_models_updates_dropdown_and_status(
        self,
        discover_models_mock,
        save_cache_mock,
    ) -> None:
        """Model discovery should update choices and report success."""

        discover_models_mock.return_value = (
            "https://api.openai.com/v1/chat/completions",
            ["gpt-4.1-mini", "gpt-4o-mini"],
        )

        model_update, status = external_lm_setup.fetch_external_lm_models(
            "openai",
            "gpt-4.1-mini",
            "https://api.openai.com/v1/chat/completions",
            "sk-test",
        )

        self.assertEqual(model_update["choices"], ["gpt-4.1-mini", "gpt-4o-mini"])
        self.assertEqual(model_update["value"], "gpt-4.1-mini")
        self.assertIn("discovered 2 models", status)
        save_cache_mock.assert_called_once()

    @patch("acestep.ui.gradio.events.generation.external_lm_setup.save_cached_external_models")
    @patch("acestep.ui.gradio.events.generation.external_lm_setup.discover_provider_models")
    def test_fetch_external_lm_models_keeps_success_when_cache_write_fails(
        self,
        discover_models_mock,
        save_cache_mock,
    ) -> None:
        """A cache-write error should not mask successful remote discovery."""

        discover_models_mock.return_value = (
            "https://api.openai.com/v1/chat/completions",
            ["gpt-4.1-mini", "gpt-4o-mini"],
        )
        save_cache_mock.side_effect = OSError("read-only filesystem")

        model_update, status = external_lm_setup.fetch_external_lm_models(
            "openai",
            "gpt-4.1-mini",
            "https://api.openai.com/v1/chat/completions",
            "sk-test",
        )

        self.assertEqual(model_update["choices"], ["gpt-4.1-mini", "gpt-4o-mini"])
        self.assertEqual(model_update["value"], "gpt-4.1-mini")
        self.assertIn("discovered 2 models", status)
        self.assertIn("cache could not be saved", status)

    @patch("acestep.ui.gradio.events.generation.external_lm_setup_support.discover_external_models")
    @patch("acestep.ui.gradio.events.generation.external_lm_setup_support.resolve_external_api_key")
    def test_discover_provider_models_uses_resolved_api_key_fallback(
        self,
        resolve_api_key_mock,
        discover_models_mock,
    ) -> None:
        """Model discovery should use resolved env/secret credentials when inline key is blank."""

        profile = get_external_provider_profile("openai")
        resolve_api_key_mock.return_value = "stored-secret"
        discover_models_mock.return_value = ["gpt-4.1-mini"]

        base_url, models = external_lm_setup_support.discover_provider_models(
            profile=profile,
            base_url="",
            api_key="",
        )

        self.assertEqual(base_url, profile.default_base_url)
        self.assertEqual(models, ["gpt-4.1-mini"])
        resolve_api_key_mock.assert_called_once_with(provider="openai", api_key="")
        discover_models_mock.assert_called_once_with(
            provider="openai",
            protocol="openai_chat",
            base_url=profile.default_base_url,
            api_key="stored-secret",
        )

    @patch("acestep.ui.gradio.events.generation.external_lm_setup.save_external_lm_runtime_settings")
    def test_save_external_lm_settings_reports_runtime_only_when_api_key_blank(
        self,
        save_runtime_mock,
    ) -> None:
        """Saving with no inline API key should persist non-secret settings and explain fallback."""

        status = external_lm_setup.save_external_lm_settings(
            "openai",
            "gpt-4.1-mini",
            "https://api.openai.com/v1/chat/completions",
            "",
        )

        save_runtime_mock.assert_called_once_with(
            provider="openai",
            protocol="openai_chat",
            model="gpt-4.1-mini",
            base_url="https://api.openai.com/v1/chat/completions",
        )
        self.assertIn("Saved external LM runtime settings", status)
        self.assertIn("ACESTEP_OPENAI_API_KEY", status)

    @patch("acestep.ui.gradio.events.generation.external_lm_setup.resolve_runtime_passphrase")
    @patch("acestep.ui.gradio.events.generation.external_lm_setup.EncryptedSecretStore")
    @patch("acestep.ui.gradio.events.generation.external_lm_setup.save_external_lm_runtime_settings")
    def test_save_external_lm_settings_persists_api_key_when_secret_store_available(
        self,
        save_runtime_mock,
        secret_store_cls,
        resolve_passphrase_mock,
    ) -> None:
        """Saving should persist the API key through the provider secret store when possible."""

        resolve_passphrase_mock.return_value = "passphrase"
        secret_store = MagicMock()
        secret_store.secret_path = Path("/tmp/openai_api_key.enc")
        secret_store_cls.return_value = secret_store

        status = external_lm_setup.save_external_lm_settings(
            "openai",
            "gpt-4.1-mini",
            "https://api.openai.com/v1/chat/completions",
            "sk-test",
        )

        save_runtime_mock.assert_called_once()
        secret_store.save.assert_called_once_with(secret="sk-test", passphrase="passphrase")
        self.assertIn("API key saved to secure storage", status)

    @patch("acestep.ui.gradio.events.generation.external_lm_setup.load_cached_external_models")
    @patch("acestep.ui.gradio.events.generation.external_lm_setup.load_external_lm_runtime_settings")
    def test_runtime_doctor_reports_secret_store_presence(
        self,
        load_runtime_mock,
        load_cached_models_mock,
    ) -> None:
        """Runtime doctor should report cached models, saved runtime, and secret-store availability."""

        load_runtime_mock.return_value = {
            "provider": "openai",
            "protocol": "openai_chat",
            "model": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1/chat/completions",
        }
        load_cached_models_mock.return_value = ["gpt-4.1-mini"]

        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "openai_api_key.enc"
            secret_path.write_text("encrypted", encoding="utf-8")
            with patch(
                "acestep.ui.gradio.events.generation.external_lm_setup._resolve_secret_store_path",
                return_value=secret_path,
            ):
                status = external_lm_setup.run_external_lm_runtime_doctor(
                    "openai",
                    "gpt-4.1-mini",
                    "https://api.openai.com/v1/chat/completions",
                    "",
                )

        self.assertIn("External LM runtime doctor for OpenAI", status)
        self.assertIn("Saved runtime settings found", status)
        self.assertIn("Cached models available (1)", status)
        self.assertIn(str(secret_path), status)

    @patch("acestep.ui.gradio.events.generation.external_lm_setup_actions._has_secret_store_value")
    @patch("acestep.ui.gradio.events.generation.external_lm_setup.load_cached_external_models")
    @patch("acestep.ui.gradio.events.generation.external_lm_setup.load_external_lm_runtime_settings")
    def test_runtime_doctor_reports_keyring_secret_without_file(
        self,
        load_runtime_mock,
        load_cached_models_mock,
        has_secret_store_value_mock,
    ) -> None:
        """Runtime doctor should report keyring-backed secrets even without a file on disk."""

        load_runtime_mock.return_value = {
            "provider": "openai",
            "protocol": "openai_chat",
            "model": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1/chat/completions",
        }
        load_cached_models_mock.return_value = []
        has_secret_store_value_mock.return_value = True
        secret_path = Path("/tmp/openai_keyring_only.enc")

        with patch(
            "acestep.ui.gradio.events.generation.external_lm_setup._resolve_secret_store_path",
            return_value=secret_path,
        ):
            status = external_lm_setup.run_external_lm_runtime_doctor(
                "openai",
                "gpt-4.1-mini",
                "https://api.openai.com/v1/chat/completions",
                "",
            )

        self.assertIn(str(secret_path), status)
        self.assertIn("Saved runtime settings found", status)


if __name__ == "__main__":
    unittest.main()
