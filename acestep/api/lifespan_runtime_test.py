"""Unit tests for lifespan runtime bootstrap helper."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.api.lifespan_runtime import initialize_lifespan_runtime


class LifespanRuntimeTests(unittest.TestCase):
    """Behavior tests for API lifespan runtime/state initialization."""

    @patch("acestep.api.lifespan_runtime._initialize_local_cache")
    @patch("acestep.api.lifespan_runtime.os.makedirs")
    def test_initialize_lifespan_runtime_sets_expected_default_state(
        self,
        mock_makedirs: MagicMock,
        mock_initialize_local_cache: MagicMock,
    ) -> None:
        """Bootstrap helper should initialize default app.state runtime fields."""

        app = SimpleNamespace(state=SimpleNamespace())
        store = object()
        training_state_init = MagicMock()
        handler = MagicMock(name="handler")
        ace_handler_cls = MagicMock(return_value=handler)
        llm_handler = MagicMock(name="llm_handler")
        llm_handler_cls = MagicMock(return_value=llm_handler)

        with patch.dict(os.environ, {}, clear=True):
            runtime = initialize_lifespan_runtime(
                app=app,
                store=store,
                queue_maxsize=200,
                avg_window=50,
                initial_avg_job_seconds=5.0,
                get_project_root=MagicMock(return_value="k:/repo"),
                initialize_training_state_fn=training_state_init,
                ace_handler_cls=ace_handler_cls,
                llm_handler_cls=llm_handler_cls,
            )

        self.assertEqual(200, app.state.job_queue.maxsize)
        self.assertEqual(5.0, app.state.avg_job_seconds)
        self.assertEqual("acestep-v15-turbo", app.state._config_path)
        self.assertIs(app.state.handler, handler)
        self.assertIs(app.state.llm_handler, llm_handler)
        self.assertIsNone(runtime.handler2)
        self.assertIsNone(runtime.handler3)
        training_state_init.assert_called_once_with(app)
        mock_initialize_local_cache.assert_called_once_with(app, runtime.cache_root)
        self.assertTrue(mock_makedirs.called)

    @patch("acestep.api.lifespan_runtime._initialize_local_cache")
    @patch("acestep.api.lifespan_runtime.os.makedirs")
    def test_initialize_lifespan_runtime_supports_secondary_and_third_model_handlers(
        self,
        _mock_makedirs: MagicMock,
        _mock_initialize_local_cache: MagicMock,
    ) -> None:
        """Bootstrap helper should create extra handlers when secondary config paths exist."""

        app = SimpleNamespace(state=SimpleNamespace())
        store = object()
        training_state_init = MagicMock()
        handler_values = [MagicMock(), MagicMock(), MagicMock()]
        ace_handler_cls = MagicMock(side_effect=handler_values)
        llm_handler_cls = MagicMock(return_value=MagicMock())

        with patch.dict(
            os.environ,
            {
                "ACESTEP_TMPDIR": "k:/tmp/acestep",
                "ACESTEP_CONFIG_PATH2": "acestep-v15-second",
                "ACESTEP_CONFIG_PATH3": "acestep-v15-third",
                "ACESTEP_API_WORKERS": "3",
            },
            clear=True,
        ):
            runtime = initialize_lifespan_runtime(
                app=app,
                store=store,
                queue_maxsize=50,
                avg_window=20,
                initial_avg_job_seconds=2.5,
                get_project_root=MagicMock(return_value="k:/repo"),
                initialize_training_state_fn=training_state_init,
                ace_handler_cls=ace_handler_cls,
                llm_handler_cls=llm_handler_cls,
            )
            self.assertEqual("k:/tmp/acestep", os.environ.get("TMPDIR"))

        self.assertIsNotNone(runtime.handler2)
        self.assertIsNotNone(runtime.handler3)
        self.assertEqual("acestep-v15-second", runtime.config_path2)
        self.assertEqual("acestep-v15-third", runtime.config_path3)
        self.assertEqual("acestep-v15-second", app.state._config_path2)
        self.assertEqual("acestep-v15-third", app.state._config_path3)
        self.assertTrue(str(app.state.temp_audio_dir).endswith("api_audio"))


if __name__ == "__main__":
    unittest.main()
