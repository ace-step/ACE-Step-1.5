"""Unit tests for API server CLI bootstrap helper."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from acestep.api.server_cli import run_api_server_main


class ServerCliTests(unittest.TestCase):
    """Behavior tests for argument parsing and uvicorn bootstrap wiring."""

    def test_run_api_server_main_invokes_uvicorn_with_parsed_host_port(self) -> None:
        """CLI helper should pass parsed host/port and fixed worker settings to uvicorn."""

        with patch.dict(os.environ, {}, clear=True):
            with patch("acestep.api.server_cli.uvicorn.run") as mock_run:
                run_api_server_main(lambda _name, default: default, argv=["--host", "0.0.0.0", "--port", "9001"])
        mock_run.assert_called_once_with(
            "acestep.api_server:app",
            host="0.0.0.0",
            port=9001,
            reload=False,
            workers=1,
        )

    def test_run_api_server_main_sets_env_overrides_from_flags(self) -> None:
        """CLI helper should apply legacy env side effects for supported flags."""

        with patch.dict(os.environ, {}, clear=True):
            with patch("acestep.api.server_cli.uvicorn.run"):
                run_api_server_main(
                    lambda _name, default: default,
                    argv=[
                        "--api-key",
                        "secret",
                        "--download-source",
                        "huggingface",
                        "--init-llm",
                        "--lm-model-path",
                        "acestep-5Hz-lm-0.6B",
                        "--no-init",
                    ],
                )

            self.assertEqual("secret", os.environ.get("ACESTEP_API_KEY"))
            self.assertEqual("huggingface", os.environ.get("ACESTEP_DOWNLOAD_SOURCE"))
            self.assertEqual("true", os.environ.get("ACESTEP_INIT_LLM"))
            self.assertEqual("acestep-5Hz-lm-0.6B", os.environ.get("ACESTEP_LM_MODEL_PATH"))
            self.assertEqual("true", os.environ.get("ACESTEP_NO_INIT"))

    def test_run_api_server_main_uses_env_bool_for_flag_defaults(self) -> None:
        """CLI helper should respect env_bool-provided defaults when flags omitted."""

        observed = []

        def _env_bool(name: str, default: bool) -> bool:
            observed.append((name, default))
            if name == "ACESTEP_INIT_LLM":
                return True
            return False

        with patch.dict(os.environ, {}, clear=True):
            with patch("acestep.api.server_cli.uvicorn.run") as mock_run:
                run_api_server_main(_env_bool, argv=[])
                self.assertEqual("true", os.environ.get("ACESTEP_INIT_LLM"))
                self.assertIsNone(os.environ.get("ACESTEP_NO_INIT"))
                mock_run.assert_called_once()

        self.assertIn(("ACESTEP_INIT_LLM", False), observed)
        self.assertIn(("ACESTEP_NO_INIT", False), observed)


if __name__ == "__main__":
    unittest.main()
