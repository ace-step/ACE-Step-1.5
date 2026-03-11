"""Unit tests for LLM startup initialization helper."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.api.startup_llm_init import initialize_llm_at_startup


class StartupLlmInitTests(unittest.TestCase):
    """Behavior tests for LLM startup initialization decisions."""

    def test_initialize_llm_at_startup_skips_when_disabled(self) -> None:
        """Helper should skip LLM init and disable lazy loading when explicitly disabled."""

        app = SimpleNamespace(
            state=SimpleNamespace(
                _llm_initialized=True,
                _llm_init_error=None,
                _llm_lazy_load_disabled=False,
            )
        )
        llm_handler = MagicMock()
        gpu_config = SimpleNamespace(init_lm_default=True, gpu_memory_gb=8.0, tier="mid")

        with patch.dict(os.environ, {"ACESTEP_INIT_LLM": "false"}, clear=True):
            initialize_llm_at_startup(
                app=app,
                llm_handler=llm_handler,
                gpu_config=gpu_config,
                device="cuda",
                offload_to_cpu=False,
                checkpoint_dir="k:/repo/checkpoints",
                get_model_name=MagicMock(return_value="acestep-5Hz-lm-0.6B"),
                ensure_model_downloaded=MagicMock(),
                env_bool=lambda _name, default: default,
            )

        llm_handler.initialize.assert_not_called()
        self.assertFalse(app.state._llm_initialized)
        self.assertTrue(app.state._llm_lazy_load_disabled)

    @patch("acestep.api.startup_llm_init.is_lm_model_supported")
    @patch("acestep.api.startup_llm_init.get_recommended_lm_model")
    def test_initialize_llm_at_startup_loads_recommended_model(
        self,
        mock_get_recommended_lm_model: MagicMock,
        mock_is_lm_model_supported: MagicMock,
    ) -> None:
        """Helper should initialize LLM with recommended model when auto mode is active."""

        app = SimpleNamespace(
            state=SimpleNamespace(
                _llm_initialized=False,
                _llm_init_error=None,
                _llm_lazy_load_disabled=False,
            )
        )
        llm_handler = MagicMock()
        llm_handler.initialize.return_value = ("ok", True)
        gpu_config = SimpleNamespace(init_lm_default=True, gpu_memory_gb=24.0, tier="high")
        mock_get_recommended_lm_model.return_value = "acestep-5Hz-lm-1.1B"
        mock_is_lm_model_supported.return_value = (True, "")
        ensure_model_downloaded = MagicMock()

        with patch.dict(os.environ, {}, clear=True):
            initialize_llm_at_startup(
                app=app,
                llm_handler=llm_handler,
                gpu_config=gpu_config,
                device="cuda",
                offload_to_cpu=False,
                checkpoint_dir="k:/repo/checkpoints",
                get_model_name=MagicMock(return_value="acestep-5Hz-lm-1.1B"),
                ensure_model_downloaded=ensure_model_downloaded,
                env_bool=lambda _name, default: default,
            )

        ensure_model_downloaded.assert_called_once_with(
            "acestep-5Hz-lm-1.1B",
            "k:/repo/checkpoints",
        )
        llm_handler.initialize.assert_called_once()
        self.assertTrue(app.state._llm_initialized)
        self.assertIsNone(app.state._llm_init_error)


if __name__ == "__main__":
    unittest.main()
