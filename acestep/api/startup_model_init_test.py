"""Unit tests for startup model initialization orchestration helper."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from acestep.api.startup_model_init import initialize_models_at_startup


def _gpu_config(init_lm_default: bool = True) -> SimpleNamespace:
    """Create a fake GPU config object with all fields used by startup init."""

    return SimpleNamespace(
        gpu_memory_gb=24.0,
        tier="high",
        max_duration_with_lm=180,
        max_duration_without_lm=300,
        max_batch_size_with_lm=2,
        max_batch_size_without_lm=4,
        init_lm_default=init_lm_default,
        available_lm_models=["acestep-5Hz-lm-1.1B"],
    )


class StartupModelInitTests(unittest.TestCase):
    """Behavior tests for startup model-loading orchestration."""

    @patch("acestep.api.startup_model_init.initialize_llm_at_startup")
    @patch("acestep.api.startup_model_init.set_global_gpu_config")
    @patch("acestep.api.startup_model_init.get_gpu_config")
    def test_initialize_models_at_startup_skips_model_init_in_no_init_mode(
        self,
        mock_get_gpu_config: MagicMock,
        _mock_set_global_gpu_config: MagicMock,
        mock_initialize_llm_at_startup: MagicMock,
    ) -> None:
        """Helper should skip model initialization when ACESTEP_NO_INIT resolves true."""

        app = SimpleNamespace(state=SimpleNamespace())
        handler = MagicMock()
        llm_handler = MagicMock()
        mock_get_gpu_config.return_value = _gpu_config()

        def _env_bool(name: str, default: bool) -> bool:
            return True if name == "ACESTEP_NO_INIT" else default

        initialize_models_at_startup(
            app=app,
            handler=handler,
            llm_handler=llm_handler,
            handler2=None,
            handler3=None,
            config_path2="",
            config_path3="",
            get_project_root=MagicMock(return_value="k:/repo"),
            get_model_name=MagicMock(return_value="acestep-v15-turbo"),
            ensure_model_downloaded=MagicMock(),
            env_bool=_env_bool,
        )

        handler.initialize_service.assert_not_called()
        mock_initialize_llm_at_startup.assert_not_called()
        self.assertIsNotNone(getattr(app.state, "gpu_config", None))

    @patch("acestep.api.startup_model_init.initialize_llm_at_startup")
    @patch("acestep.api.startup_model_init.set_global_gpu_config")
    @patch("acestep.api.startup_model_init.get_gpu_config")
    def test_initialize_models_at_startup_initializes_primary_and_calls_llm(
        self,
        mock_get_gpu_config: MagicMock,
        _mock_set_global_gpu_config: MagicMock,
        mock_initialize_llm_at_startup: MagicMock,
    ) -> None:
        """Helper should initialize primary DiT and then call LLM startup helper."""

        app = SimpleNamespace(
            state=SimpleNamespace(
                _initialized=False,
                _initialized2=False,
                _initialized3=False,
                _init_error=None,
                _llm_initialized=False,
                _llm_init_error=None,
                _llm_lazy_load_disabled=False,
            )
        )
        handler = MagicMock()
        handler.initialize_service.return_value = ("ok", True)
        llm_handler = MagicMock()
        ensure_model_downloaded = MagicMock()
        mock_get_gpu_config.return_value = _gpu_config()

        with patch.dict(os.environ, {}, clear=True):
            initialize_models_at_startup(
                app=app,
                handler=handler,
                llm_handler=llm_handler,
                handler2=None,
                handler3=None,
                config_path2="",
                config_path3="",
                get_project_root=MagicMock(return_value="k:/repo"),
                get_model_name=MagicMock(return_value="acestep-v15-turbo"),
                ensure_model_downloaded=ensure_model_downloaded,
                env_bool=lambda _name, default: default,
            )

        handler.initialize_service.assert_called_once()
        ensure_model_downloaded.assert_any_call("acestep-v15-turbo", ANY)
        ensure_model_downloaded.assert_any_call("vae", ANY)
        self.assertTrue(app.state._initialized)
        mock_initialize_llm_at_startup.assert_called_once()

    @patch("acestep.api.startup_model_init.initialize_llm_at_startup")
    @patch("acestep.api.startup_model_init.set_global_gpu_config")
    @patch("acestep.api.startup_model_init.get_gpu_config")
    def test_initialize_models_at_startup_raises_on_primary_init_failure(
        self,
        mock_get_gpu_config: MagicMock,
        _mock_set_global_gpu_config: MagicMock,
        mock_initialize_llm_at_startup: MagicMock,
    ) -> None:
        """Helper should raise and persist init error when primary DiT fails."""

        app = SimpleNamespace(
            state=SimpleNamespace(
                _initialized=False,
                _init_error=None,
                _llm_initialized=False,
                _llm_init_error=None,
                _llm_lazy_load_disabled=False,
            )
        )
        handler = MagicMock()
        handler.initialize_service.return_value = ("boom", False)
        mock_get_gpu_config.return_value = _gpu_config()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                initialize_models_at_startup(
                    app=app,
                    handler=handler,
                    llm_handler=MagicMock(),
                    handler2=None,
                    handler3=None,
                    config_path2="",
                    config_path3="",
                    get_project_root=MagicMock(return_value="k:/repo"),
                    get_model_name=MagicMock(return_value="acestep-v15-turbo"),
                    ensure_model_downloaded=MagicMock(),
                    env_bool=lambda _name, default: default,
                )

        mock_initialize_llm_at_startup.assert_not_called()
        self.assertEqual("boom", app.state._init_error)


if __name__ == "__main__":
    unittest.main()
