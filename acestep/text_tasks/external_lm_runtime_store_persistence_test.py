"""Tests for external LM runtime settings persistence."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acestep.text_tasks.external_lm_runtime_store import (
    external_lm_settings_path,
    load_all_external_lm_runtime_settings,
    load_external_lm_runtime_settings,
    save_external_lm_runtime_settings,
)


class ExternalLmRuntimeStorePersistenceTests(unittest.TestCase):
    """Verify runtime settings save/load behavior."""

    def test_save_and_load_round_trip_per_provider(self) -> None:
        """Saved runtime settings should retain separate provider records."""

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"XDG_DATA_HOME": tmpdir}, clear=False):
                save_external_lm_runtime_settings(
                    provider="zai",
                    protocol="openai_chat",
                    model="glm-4.7",
                    base_url="https://api.z.ai/api/paas/v4/chat/completions",
                )
                path = save_external_lm_runtime_settings(
                    provider="openai",
                    protocol="openai_chat",
                    model="gpt-4o-mini",
                    base_url="https://api.openai.com/v1/chat/completions",
                )

                self.assertEqual(path, external_lm_settings_path())
                self.assertTrue(path.exists())
                self.assertEqual(
                    load_external_lm_runtime_settings("zai"),
                    {
                        "provider": "zai",
                        "protocol": "openai_chat",
                        "model": "glm-4.7",
                        "base_url": "https://api.z.ai/api/paas/v4/chat/completions",
                    },
                )
                self.assertEqual(
                    load_external_lm_runtime_settings(),
                    {
                        "provider": "openai",
                        "protocol": "openai_chat",
                        "model": "gpt-4o-mini",
                        "base_url": "https://api.openai.com/v1/chat/completions",
                    },
                )

    def test_load_all_external_lm_runtime_settings_ignores_non_provider_shape(self) -> None:
        """Unexpected settings shapes should safely fall back to an empty payload."""

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"XDG_DATA_HOME": tmpdir}, clear=False):
                config_dir = Path(tmpdir) / "acestep" / "config"
                config_dir.mkdir(parents=True, exist_ok=True)
                (config_dir / "external_lm_runtime.json").write_text(
                    json.dumps({"provider": "zai", "model": "glm-4.5-flash"}),
                    encoding="utf-8",
                )

                loaded = load_all_external_lm_runtime_settings()

        self.assertEqual(loaded, {"active_provider": "", "providers": {}})

    def test_load_external_lm_runtime_settings_supplies_safe_defaults_for_partial_record(
        self,
    ) -> None:
        """Partial provider records should fall back to provider defaults after upgrades."""

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"XDG_DATA_HOME": tmpdir}, clear=False):
                config_dir = Path(tmpdir) / "acestep" / "config"
                config_dir.mkdir(parents=True, exist_ok=True)
                (config_dir / "external_lm_runtime.json").write_text(
                    json.dumps(
                        {
                            "active_provider": "claude",
                            "providers": {
                                "claude": {
                                    "model": "",
                                    "protocol": "",
                                    "base_url": "",
                                }
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                loaded = load_external_lm_runtime_settings("claude")

        self.assertEqual(loaded["provider"], "claude")
        self.assertEqual(loaded["protocol"], "anthropic_messages")
        self.assertEqual(loaded["model"], "claude-3-7-sonnet-latest")
        self.assertEqual(loaded["base_url"], "https://api.anthropic.com/v1/messages")

    def test_load_all_external_lm_runtime_settings_skips_unknown_provider_entries(self) -> None:
        """Unknown provider keys should be ignored instead of poisoning saved settings."""

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"XDG_DATA_HOME": tmpdir}, clear=False):
                config_dir = Path(tmpdir) / "acestep" / "config"
                config_dir.mkdir(parents=True, exist_ok=True)
                (config_dir / "external_lm_runtime.json").write_text(
                    json.dumps(
                        {
                            "active_provider": "zai",
                            "providers": {
                                "zai": {
                                    "protocol": "openai_chat",
                                    "model": "glm-4.5-flash",
                                    "base_url": "https://api.z.ai/api/paas/v4/chat/completions",
                                },
                                "future_provider": {
                                    "protocol": "future_chat",
                                    "model": "future-1",
                                    "base_url": "https://example.invalid/future",
                                },
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                loaded = load_all_external_lm_runtime_settings()

        self.assertEqual(loaded["active_provider"], "zai")
        self.assertIn("zai", loaded["providers"])
        self.assertNotIn("future_provider", loaded["providers"])


if __name__ == "__main__":
    unittest.main()
