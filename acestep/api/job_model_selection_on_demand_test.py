"""Unit tests for ACESTEP_ON_DEMAND_MODEL_LOAD request-time model loading."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

from acestep.api.job_model_selection import (
    _FAILED_FETCH_COOLDOWN_SEC,
    select_generation_handler,
)


class OnDemandModelLoadTests(unittest.TestCase):
    """Behavior tests for ACESTEP_ON_DEMAND_MODEL_LOAD request-time loading."""

    def _app_state(self) -> SimpleNamespace:
        """Build an app-state stub with only the primary handler loaded."""

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
        """Run select_generation_handler; returns (handler, model_name)."""

        return select_generation_handler(
            app_state=app_state,
            requested_model=requested,
            get_model_name=lambda value: value or "",
            job_id="job-od",
            log_fn=logger or MagicMock(),
        )

    _ENV_ON: ClassVar[dict[str, str]] = {
        "ACESTEP_ON_DEMAND_MODEL_LOAD": "true",
        "ACESTEP_QUEUE_WORKERS": "1",
        "ACESTEP_API_WORKERS": "1",
    }

    def _assert_disabled_falls_back_to_primary(self) -> None:
        """Assert an unloaded model falls back to the untouched primary."""

        app_state = self._app_state()
        logger = MagicMock()
        handler, model = self._select(app_state, "acestep-v15-sft", logger)

        self.assertIs(handler, app_state.handler)
        self.assertEqual("acestep-v15-turbo", model)
        app_state.handler.initialize_service.assert_not_called()
        self.assertIn("not found", logger.call_args[0][0])

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
        """A failed initialize_service may leave the handler torn: fail the
        job and clear the config path to force a full reload next request."""

        app_state = self._app_state()
        app_state.handler.initialize_service = MagicMock(return_value=("boom", False))

        with self.assertRaises(RuntimeError):
            self._select(app_state, "acestep-v15-sft")
        self.assertEqual("", app_state._config_path)

    @patch.dict(os.environ, _ENV_ON, clear=False)
    def test_download_failure_falls_back_with_traceback_and_fails_fast(self) -> None:
        """Download failures fall back safely with a traceback in the log,
        and the cached name makes repeats inside the cooldown fail fast."""

        app_state = self._app_state()
        app_state._ensure_model_downloaded = MagicMock(side_effect=OSError("net down"))
        logger = MagicMock()

        handler, model = self._select(app_state, "acestep-v15-sft", logger)
        self.assertIs(handler, app_state.handler)
        self.assertEqual("acestep-v15-turbo", model)
        app_state.handler.initialize_service.assert_not_called()
        self.assertIn("failed", logger.call_args[0][0])
        self.assertIn("Traceback", logger.call_args[0][0])

        _, model = self._select(app_state, "acestep-v15-sft", logger)
        self.assertEqual("acestep-v15-turbo", model)
        app_state._ensure_model_downloaded.assert_called_once()

    @patch.dict(os.environ, _ENV_ON, clear=False)
    def test_failed_fetch_retries_after_cooldown(self) -> None:
        """A cached failure must expire so transient errors recover."""

        app_state = self._app_state()
        app_state._ensure_model_downloaded = MagicMock(side_effect=OSError("net down"))
        self._select(app_state, "acestep-v15-sft")

        app_state._on_demand_failed_models["acestep-v15-sft"] -= (
            _FAILED_FETCH_COOLDOWN_SEC + 1.0
        )
        app_state._ensure_model_downloaded = MagicMock()
        _, model = self._select(app_state, "acestep-v15-sft")

        self.assertEqual("acestep-v15-sft", model)
        app_state._ensure_model_downloaded.assert_called_once()

    @patch.dict(os.environ, {**_ENV_ON, "ACESTEP_API_WORKERS": "2"}, clear=False)
    def test_disabled_with_multiple_api_workers(self) -> None:
        """The /models init route can reinitialize the handler from another
        API executor thread, so on-demand loading requires a single one."""

        self._assert_disabled_falls_back_to_primary()

    @patch.dict(os.environ, {**_ENV_ON, "ACESTEP_QUEUE_WORKERS": "0"}, clear=False)
    def test_worker_count_zero_counts_as_single(self) -> None:
        """The runtime normalizes worker count with max(1, …); the gate must
        apply the same normalization so 0 still enables the feature."""

        app_state = self._app_state()
        _, model = self._select(app_state, "acestep-v15-sft")

        self.assertEqual("acestep-v15-sft", model)
        app_state.handler.initialize_service.assert_called_once()

    @patch.dict(os.environ, {**_ENV_ON, "ACESTEP_QUEUE_WORKERS": "abc"}, clear=False)
    def test_disabled_with_non_numeric_queue_workers(self) -> None:
        """Unparsable worker counts must disable the feature, not raise."""

        self._assert_disabled_falls_back_to_primary()

    @patch.dict(
        os.environ,
        {"ACESTEP_ON_DEMAND_MODEL_LOAD": "true", "ACESTEP_QUEUE_WORKERS": "2"},
        clear=False,
    )
    def test_disabled_with_multiple_queue_workers(self) -> None:
        """On-demand loading must stay off when generations are not serialized."""

        self._assert_disabled_falls_back_to_primary()

    @patch.dict(os.environ, {"ACESTEP_ON_DEMAND_MODEL_LOAD": "false"}, clear=False)
    def test_disabled_by_default_preserves_fallback(self) -> None:
        """With the gate off, unknown models keep the silent-fallback behavior."""

        self._assert_disabled_falls_back_to_primary()


if __name__ == "__main__":
    unittest.main()
