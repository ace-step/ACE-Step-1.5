"""Unit tests for per-job model handler selection helper."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.api.job_model_selection import select_generation_handler


class JobModelSelectionTests(unittest.TestCase):
    """Behavior tests for model routing and fallback logging."""

    def _app_state(self) -> SimpleNamespace:
        return SimpleNamespace(
            handler=MagicMock(name="primary"),
            handler2=MagicMock(name="second"),
            handler3=MagicMock(name="third"),
            _initialized2=True,
            _initialized3=True,
            _config_path="acestep-v15-primary",
            _config_path2="acestep-v15-second",
            _config_path3="acestep-v15-third",
        )

    def test_select_generation_handler_defaults_to_primary(self) -> None:
        """No requested model should return primary handler/model."""

        app_state = self._app_state()
        handler, model = select_generation_handler(
            app_state=app_state,
            requested_model=None,
            get_model_name=lambda value: value.split("-")[-1] if value else "",
            job_id="job-1",
            log_fn=MagicMock(),
        )

        self.assertIs(handler, app_state.handler)
        self.assertEqual("primary", model)

    def test_select_generation_handler_uses_second_model_when_requested(self) -> None:
        """Requested model should route to second handler when initialized and matched."""

        app_state = self._app_state()
        logger = MagicMock()
        handler, model = select_generation_handler(
            app_state=app_state,
            requested_model="second",
            get_model_name=lambda value: value.split("-")[-1] if value else "",
            job_id="job-2",
            log_fn=logger,
        )

        self.assertIs(handler, app_state.handler2)
        self.assertEqual("second", model)
        logger.assert_called_once()

    def test_select_generation_handler_uses_third_model_when_second_not_matched(self) -> None:
        """Requested model should route to third handler when it is the first match."""

        app_state = self._app_state()
        logger = MagicMock()
        handler, model = select_generation_handler(
            app_state=app_state,
            requested_model="third",
            get_model_name=lambda value: value.split("-")[-1] if value else "",
            job_id="job-3",
            log_fn=logger,
        )

        self.assertIs(handler, app_state.handler3)
        self.assertEqual("third", model)
        logger.assert_called_once()

    def test_select_generation_handler_logs_fallback_on_unknown_model(self) -> None:
        """Unknown requested model should preserve fallback-to-primary behavior."""

        app_state = self._app_state()
        logger = MagicMock()
        handler, model = select_generation_handler(
            app_state=app_state,
            requested_model="unknown",
            get_model_name=lambda value: value.split("-")[-1] if value else "",
            job_id="job-4",
            log_fn=logger,
        )

        self.assertIs(handler, app_state.handler)
        self.assertEqual("primary", model)
        logger.assert_called_once()
        self.assertIn("not found", logger.call_args[0][0])


class OnDemandModelLoadTests(unittest.TestCase):
    """Behavior tests for ACESTEP_ON_DEMAND_MODEL_LOAD request-time loading."""

    def _app_state(self) -> SimpleNamespace:
        state = SimpleNamespace(
            handler=MagicMock(name="primary"),
            handler2=None,
            handler3=None,
            _initialized2=False,
            _initialized3=False,
            _config_path="acestep-v15-turbo",
            _checkpoint_dir="/ckpt",
            _service_init_kwargs={"device": "auto"},
            _ensure_model_downloaded=MagicMock(),
        )
        state.handler.initialize_service = MagicMock(return_value=("ok", True))
        return state

    def _select(self, app_state, requested, logger=None):
        return select_generation_handler(
            app_state=app_state,
            requested_model=requested,
            get_model_name=lambda value: value or "",
            job_id="job-od",
            log_fn=logger or MagicMock(),
        )

    _ENV_ON = {
        "ACESTEP_ON_DEMAND_MODEL_LOAD": "true",
        "ACESTEP_QUEUE_WORKERS": "1",
        "ACESTEP_API_WORKERS": "1",
    }

    @patch.dict(os.environ, _ENV_ON, clear=False)
    def test_loads_requested_model_when_enabled(self) -> None:
        """An unloaded requested model should download, load, and become primary."""

        app_state = self._app_state()
        handler, model = self._select(app_state, "acestep-v15-sft")

        self.assertIs(handler, app_state.handler)
        self.assertEqual("acestep-v15-sft", model)
        app_state._ensure_model_downloaded.assert_called_once_with(
            "acestep-v15-sft", "/ckpt"
        )
        app_state.handler.initialize_service.assert_called_once_with(
            config_path="acestep-v15-sft", device="auto"
        )
        self.assertEqual("acestep-v15-sft", app_state._config_path)

    @patch.dict(os.environ, _ENV_ON, clear=False)
    def test_requesting_primary_does_not_reload(self) -> None:
        """Requesting the already-primary model must not touch the handler."""

        app_state = self._app_state()
        handler, model = self._select(app_state, "acestep-v15-turbo")

        self.assertIs(handler, app_state.handler)
        self.assertEqual("acestep-v15-turbo", model)
        app_state.handler.initialize_service.assert_not_called()
        app_state._ensure_model_downloaded.assert_not_called()

    @patch.dict(os.environ, _ENV_ON, clear=False)
    def test_invalid_model_name_falls_back_without_loading(self) -> None:
        """Names outside the allowed pattern must not be downloaded or loaded."""

        app_state = self._app_state()
        logger = MagicMock()
        handler, model = self._select(app_state, "../evil", logger)

        self.assertIs(handler, app_state.handler)
        self.assertEqual("acestep-v15-turbo", model)
        app_state._ensure_model_downloaded.assert_not_called()
        app_state.handler.initialize_service.assert_not_called()
        self.assertIn("failed", logger.call_args[0][0])

    @patch.dict(os.environ, _ENV_ON, clear=False)
    def test_load_failure_fails_the_job_and_clears_config_path(self) -> None:
        """A failed initialize_service may leave the handler torn: the job
        must fail (no silent fallback), and the cleared config path forces the
        next request through a full reload instead of short-circuiting."""

        app_state = self._app_state()
        app_state.handler.initialize_service = MagicMock(return_value=("boom", False))

        with self.assertRaises(RuntimeError):
            self._select(app_state, "acestep-v15-sft")
        self.assertEqual("", app_state._config_path)

    @patch.dict(os.environ, _ENV_ON, clear=False)
    def test_download_failure_falls_back_safely_and_caches_name(self) -> None:
        """Download failures precede any handler mutation, so fallback is safe;
        the failed name is cached so repeated requests fail fast."""

        app_state = self._app_state()
        app_state._ensure_model_downloaded = MagicMock(side_effect=OSError("net down"))
        logger = MagicMock()

        handler, model = self._select(app_state, "acestep-v15-sft", logger)
        self.assertIs(handler, app_state.handler)
        self.assertEqual("acestep-v15-turbo", model)
        app_state.handler.initialize_service.assert_not_called()
        self.assertIn("failed", logger.call_args[0][0])

        handler, model = self._select(app_state, "acestep-v15-sft", logger)
        self.assertEqual("acestep-v15-turbo", model)
        app_state._ensure_model_downloaded.assert_called_once()

    @patch.dict(
        os.environ,
        {**_ENV_ON, "ACESTEP_API_WORKERS": "2"},
        clear=False,
    )
    def test_disabled_with_multiple_api_workers(self) -> None:
        """The /models init route can reinitialize the handler from another
        API executor thread, so on-demand loading requires a single one."""

        app_state = self._app_state()
        logger = MagicMock()
        handler, model = self._select(app_state, "acestep-v15-sft", logger)

        self.assertEqual("acestep-v15-turbo", model)
        app_state.handler.initialize_service.assert_not_called()
        self.assertIn("not found", logger.call_args[0][0])

    @patch.dict(
        os.environ,
        {**_ENV_ON, "ACESTEP_QUEUE_WORKERS": "0"},
        clear=False,
    )
    def test_worker_count_zero_counts_as_single(self) -> None:
        """The runtime normalizes worker count with max(1, …); the gate must
        apply the same normalization so 0 still enables the feature."""

        app_state = self._app_state()
        handler, model = self._select(app_state, "acestep-v15-sft")

        self.assertEqual("acestep-v15-sft", model)
        app_state.handler.initialize_service.assert_called_once()

    @patch.dict(
        os.environ,
        {"ACESTEP_ON_DEMAND_MODEL_LOAD": "true", "ACESTEP_QUEUE_WORKERS": "2"},
        clear=False,
    )
    def test_disabled_with_multiple_queue_workers(self) -> None:
        """On-demand loading must stay off when generations are not serialized."""

        app_state = self._app_state()
        logger = MagicMock()
        handler, model = self._select(app_state, "acestep-v15-sft", logger)

        self.assertIs(handler, app_state.handler)
        self.assertEqual("acestep-v15-turbo", model)
        app_state.handler.initialize_service.assert_not_called()
        self.assertIn("not found", logger.call_args[0][0])

    @patch.dict(os.environ, {"ACESTEP_ON_DEMAND_MODEL_LOAD": "false"}, clear=False)
    def test_disabled_by_default_preserves_fallback(self) -> None:
        """With the gate off, unknown models keep the silent-fallback behavior."""

        app_state = self._app_state()
        logger = MagicMock()
        handler, model = self._select(app_state, "acestep-v15-sft", logger)

        self.assertIs(handler, app_state.handler)
        self.assertEqual("acestep-v15-turbo", model)
        app_state.handler.initialize_service.assert_not_called()
        self.assertIn("not found", logger.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
