"""Unit tests for async job execution runtime helper."""

from __future__ import annotations

import asyncio
import unittest
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from acestep.api.job_execution_runtime import run_one_job_runtime


class JobExecutionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Behavior tests for queue-worker runtime execution orchestration."""

    async def test_run_one_job_runtime_success_updates_terminal_cache(self) -> None:
        """Success path should mark succeeded and write terminal cache success status."""

        app_state = SimpleNamespace(
            job_store=MagicMock(),
            executor=MagicMock(),
            stats_lock=asyncio.Lock(),
            recent_durations=deque(maxlen=50),
            avg_job_seconds=5.0,
        )
        req = SimpleNamespace(model="acestep-v15")
        selected_handler = SimpleNamespace(_empty_cache=MagicMock())
        select_generation_handler_fn = MagicMock(return_value=(selected_handler, "model-A"))
        ensure_models_initialized_fn = AsyncMock()
        update_progress_job_cache_fn = MagicMock()
        update_terminal_job_cache_fn = MagicMock()
        build_blocking_result_fn = MagicMock(return_value={"status_message": "Success"})
        loop_mock = MagicMock()
        loop_mock.run_in_executor = AsyncMock(return_value={"status_message": "Success"})

        with patch("acestep.api.job_execution_runtime.asyncio.get_running_loop", return_value=loop_mock):
            await run_one_job_runtime(
                app_state=app_state,
                store=MagicMock(),
                job_id="job-1",
                req=req,
                ensure_models_initialized_fn=ensure_models_initialized_fn,
                select_generation_handler_fn=select_generation_handler_fn,
                get_model_name=MagicMock(return_value="m"),
                build_blocking_result_fn=build_blocking_result_fn,
                update_progress_job_cache_fn=update_progress_job_cache_fn,
                update_terminal_job_cache_fn=update_terminal_job_cache_fn,
                map_status=MagicMock(return_value="running"),
                result_key_prefix="prefix_",
                result_expire_seconds=3600,
                log_fn=MagicMock(),
            )

        app_state.job_store.mark_running.assert_called_once_with("job-1")
        app_state.job_store.mark_succeeded.assert_called_once_with(
            "job-1", {"status_message": "Success"}
        )
        update_progress_job_cache_fn.assert_called_once()
        update_terminal_job_cache_fn.assert_called_once()
        self.assertEqual("succeeded", update_terminal_job_cache_fn.call_args.kwargs["status"])
        selected_handler._empty_cache.assert_called_once()
        self.assertGreaterEqual(app_state.avg_job_seconds, 0.0)

    async def test_run_one_job_runtime_failure_marks_failed_and_updates_cache(self) -> None:
        """Failure path should mark failed and write terminal cache failed status."""

        app_state = SimpleNamespace(
            job_store=MagicMock(),
            executor=MagicMock(),
            stats_lock=asyncio.Lock(),
            recent_durations=deque(maxlen=50),
            avg_job_seconds=5.0,
        )
        req = SimpleNamespace(model="acestep-v15")
        selected_handler = SimpleNamespace(_empty_cache=MagicMock())
        select_generation_handler_fn = MagicMock(return_value=(selected_handler, "model-A"))
        ensure_models_initialized_fn = AsyncMock()
        update_progress_job_cache_fn = MagicMock()
        update_terminal_job_cache_fn = MagicMock()
        build_blocking_result_fn = MagicMock(side_effect=RuntimeError("boom"))

        async def _run_in_executor(_executor, fn):
            return fn()

        loop_mock = MagicMock()
        loop_mock.run_in_executor = AsyncMock(side_effect=_run_in_executor)
        log_fn = MagicMock()

        with patch("acestep.api.job_execution_runtime.asyncio.get_running_loop", return_value=loop_mock):
            await run_one_job_runtime(
                app_state=app_state,
                store=MagicMock(),
                job_id="job-2",
                req=req,
                ensure_models_initialized_fn=ensure_models_initialized_fn,
                select_generation_handler_fn=select_generation_handler_fn,
                get_model_name=MagicMock(return_value="m"),
                build_blocking_result_fn=build_blocking_result_fn,
                update_progress_job_cache_fn=update_progress_job_cache_fn,
                update_terminal_job_cache_fn=update_terminal_job_cache_fn,
                map_status=MagicMock(return_value="failed"),
                result_key_prefix="prefix_",
                result_expire_seconds=3600,
                log_fn=log_fn,
            )

        app_state.job_store.mark_failed.assert_called_once()
        self.assertEqual("failed", update_terminal_job_cache_fn.call_args.kwargs["status"])
        selected_handler._empty_cache.assert_called_once()
        self.assertTrue(any("FAILED" in str(call.args[0]) for call in log_fn.call_args_list))

    async def test_run_one_job_runtime_integration_uses_real_executor_and_wires_handler(self) -> None:
        """Integration-style check with real run_in_executor and callback wiring."""

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            app_state = SimpleNamespace(
                job_store=MagicMock(),
                executor=executor,
                stats_lock=asyncio.Lock(),
                recent_durations=deque(maxlen=50),
                avg_job_seconds=5.0,
            )
            req = SimpleNamespace(model="acestep-v15")
            selected_handler = SimpleNamespace(_empty_cache=MagicMock())
            select_generation_handler_fn = MagicMock(return_value=(selected_handler, "model-A"))
            ensure_models_initialized_fn = AsyncMock()
            update_progress_job_cache_fn = MagicMock()
            update_terminal_job_cache_fn = MagicMock()
            captured = {}

            def _build_blocking_result(handler, model_name):
                captured["handler"] = handler
                captured["model_name"] = model_name
                return {"status_message": "Success"}

            await run_one_job_runtime(
                app_state=app_state,
                store=MagicMock(),
                job_id="job-int-1",
                req=req,
                ensure_models_initialized_fn=ensure_models_initialized_fn,
                select_generation_handler_fn=select_generation_handler_fn,
                get_model_name=MagicMock(return_value="m"),
                build_blocking_result_fn=_build_blocking_result,
                update_progress_job_cache_fn=update_progress_job_cache_fn,
                update_terminal_job_cache_fn=update_terminal_job_cache_fn,
                map_status=MagicMock(return_value="running"),
                result_key_prefix="prefix_",
                result_expire_seconds=3600,
                log_fn=MagicMock(),
            )

            self.assertIs(captured["handler"], selected_handler)
            self.assertEqual("model-A", captured["model_name"])
            app_state.job_store.mark_succeeded.assert_called_once_with(
                "job-int-1", {"status_message": "Success"}
            )
            update_progress_job_cache_fn.assert_called_once()
            update_terminal_job_cache_fn.assert_called_once()
            selected_handler._empty_cache.assert_called_once()
        finally:
            executor.shutdown(wait=True, cancel_futures=True)


if __name__ == "__main__":
    unittest.main()
