"""Unit tests for runtime job-state helper functions."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.api.job_runtime_state import (
    cleanup_job_temp_files,
    ensure_models_initialized,
    update_progress_job_cache,
    update_terminal_job_cache,
)


class JobRuntimeStateTests(unittest.IsolatedAsyncioTestCase):
    """Behavior tests for runtime cache and job-state helpers."""

    async def test_ensure_models_initialized_raises_on_prior_error(self) -> None:
        """Should propagate error from a previous failed initialization attempt."""

        app_state_error = SimpleNamespace(_init_error="boom", _initialized=False)
        with self.assertRaisesRegex(RuntimeError, "boom"):
            await ensure_models_initialized(app_state_error)

    async def test_ensure_models_initialized_returns_immediately_when_ready(self) -> None:
        """Fast path: no-op when models are already initialized."""

        app_state_ready = SimpleNamespace(_init_error=None, _initialized=True)
        await ensure_models_initialized(app_state_ready)

    async def test_ensure_models_initialized_raises_without_init_kwargs(self) -> None:
        """Should raise when not initialized and no lazy-init kwargs available."""

        app_state_no_kwargs = SimpleNamespace(
            _init_error=None,
            _initialized=False,
            _init_lock=asyncio.Lock(),
        )
        with self.assertRaisesRegex(RuntimeError, "no init kwargs"):
            await ensure_models_initialized(app_state_no_kwargs)

    async def test_ensure_models_initialized_lazy_loads_on_first_request(self) -> None:
        """Should call do_model_initialization lazily when init kwargs are present."""

        handler = MagicMock()
        handler.initialize_service.return_value = ("ok", True)

        app_state = SimpleNamespace(
            _init_error=None,
            _initialized=False,
            _init_lock=asyncio.Lock(),
            _model_init_kwargs=dict(
                handler=handler,
                llm_handler=MagicMock(),
                handler2=None,
                handler3=None,
                config_path2="",
                config_path3="",
                get_project_root=MagicMock(return_value="/repo"),
                get_model_name=MagicMock(return_value="acestep-v15-turbo"),
                ensure_model_downloaded=MagicMock(),
                env_bool=lambda _name, default: default,
            ),
            gpu_config=SimpleNamespace(
                gpu_memory_gb=24.0,
                tier="high",
            ),
        )

        with patch("acestep.api.startup_model_init.do_model_initialization") as mock_init:
            await ensure_models_initialized(app_state)
            mock_init.assert_called_once()

    async def test_cleanup_job_temp_files_removes_tracked_paths(self) -> None:
        """Cleanup helper should remove tracked files and clear job mapping."""

        fd, file_path = tempfile.mkstemp(prefix="acestep-runtime-state-", suffix=".tmp")
        os.close(fd)
        app_state = SimpleNamespace(
            job_temp_files={"job-1": [file_path, "missing-file.tmp"]},
            job_temp_files_lock=asyncio.Lock(),
        )

        await cleanup_job_temp_files(app_state, "job-1")

        self.assertFalse(os.path.exists(file_path))
        self.assertEqual({}, app_state.job_temp_files)

    @patch("acestep.api.job_runtime_state.update_local_cache")
    @patch("acestep.api.job_runtime_state.update_local_cache_progress")
    async def test_cache_helpers_delegate_to_local_cache_update_functions(
        self,
        mock_update_local_cache_progress: MagicMock,
        mock_update_local_cache: MagicMock,
    ) -> None:
        """Cache helper wrappers should forward parameters unchanged."""

        app_state = SimpleNamespace(local_cache=MagicMock())
        store = MagicMock()
        map_status = MagicMock(return_value=1)

        update_terminal_job_cache(
            app_state=app_state,
            store=store,
            job_id="job-1",
            result={"ok": True},
            status="succeeded",
            map_status=map_status,
            result_key_prefix="prefix",
            result_expire_seconds=60,
        )
        update_progress_job_cache(
            app_state=app_state,
            store=store,
            job_id="job-1",
            progress=0.5,
            stage="running",
            map_status=map_status,
            result_key_prefix="prefix",
            result_expire_seconds=60,
        )

        mock_update_local_cache.assert_called_once()
        mock_update_local_cache_progress.assert_called_once()


if __name__ == "__main__":
    unittest.main()
