"""Tests for external LM runtime settings environment hydration."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acestep.text_tasks.external_lm_runtime_store import (
    hydrate_external_lm_env_from_store,
)


class ExternalLmRuntimeStoreHydrationTests(unittest.TestCase):
    """Verify persisted runtime settings hydrate missing env vars."""

    def test_hydrate_populates_missing_env_vars_from_active_provider(self) -> None:
        """Hydration should fill missing env vars from the active saved provider."""

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
                                "ollama": {
                                    "protocol": "openai_chat",
                                    "model": "qwen3:4b",
                                    "base_url": "http://127.0.0.1:11434/v1/chat/completions",
                                },
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                with patch.dict(os.environ, {}, clear=True):
                    os.environ["XDG_DATA_HOME"] = tmpdir
                    changed = hydrate_external_lm_env_from_store()
                    self.assertTrue(changed)
                    self.assertEqual(os.environ["ACESTEP_EXTERNAL_LM_PROVIDER"], "zai")
                    self.assertEqual(os.environ["ACESTEP_GLM_MODEL"], "glm-4.5-flash")

    def test_hydrate_uses_env_selected_provider_when_present(self) -> None:
        """Hydration should backfill from the provider already selected in env."""

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
                                "openai": {
                                    "protocol": "openai_chat",
                                    "model": "gpt-4o-mini",
                                    "base_url": "https://api.openai.com/v1/chat/completions",
                                },
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                with patch.dict(
                    os.environ,
                    {"XDG_DATA_HOME": tmpdir, "ACESTEP_EXTERNAL_LM_PROVIDER": "openai"},
                    clear=True,
                ):
                    changed = hydrate_external_lm_env_from_store()
                    self.assertTrue(changed)
                    self.assertEqual(os.environ["ACESTEP_EXTERNAL_LM_PROVIDER"], "openai")
                    self.assertEqual(os.environ["ACESTEP_EXTERNAL_LM_MODEL"], "gpt-4o-mini")
                    self.assertEqual(
                        os.environ["ACESTEP_EXTERNAL_BASE_URL"],
                        "https://api.openai.com/v1/chat/completions",
                    )

if __name__ == "__main__":
    unittest.main()
