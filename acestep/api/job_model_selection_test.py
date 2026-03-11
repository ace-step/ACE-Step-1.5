"""Unit tests for per-job model handler selection helper."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

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


if __name__ == "__main__":
    unittest.main()
