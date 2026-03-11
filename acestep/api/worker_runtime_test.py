"""Unit tests for background worker task orchestration helper."""

from __future__ import annotations

import asyncio
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from acestep.api.worker_runtime import start_worker_tasks, stop_worker_tasks


class WorkerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Behavior tests for queue worker startup and shutdown helpers."""

    @patch("acestep.api.worker_runtime.run_job_store_cleanup_loop", new_callable=AsyncMock)
    @patch("acestep.api.worker_runtime.process_queue_item", new_callable=AsyncMock)
    async def test_start_and_stop_worker_tasks_processes_queue_items(
        self,
        mock_process_queue_item: AsyncMock,
        _mock_run_job_store_cleanup_loop: AsyncMock,
    ) -> None:
        """Worker orchestration should start tasks, process queue items, and stop cleanly."""

        processed = asyncio.Event()

        async def _process_queue_item_side_effect(**_kwargs) -> None:
            processed.set()

        mock_process_queue_item.side_effect = _process_queue_item_side_effect
        app_state = SimpleNamespace(job_queue=asyncio.Queue())
        store = MagicMock()
        run_one_job = AsyncMock()
        cleanup_job_temp_files = AsyncMock()

        workers, cleanup_task = start_worker_tasks(
            app_state=app_state,
            store=store,
            worker_count=0,
            run_one_job=run_one_job,
            cleanup_job_temp_files=cleanup_job_temp_files,
            cleanup_interval_seconds=300,
        )

        self.assertEqual(1, len(workers))
        await app_state.job_queue.put(("job-1", MagicMock()))
        await asyncio.wait_for(processed.wait(), timeout=1.0)

        executor = ThreadPoolExecutor(max_workers=1)
        with patch.object(executor, "shutdown") as mock_shutdown:
            stop_worker_tasks(
                workers=workers,
                cleanup_task=cleanup_task,
                executor=executor,
            )
            mock_shutdown.assert_called_once_with(wait=False, cancel_futures=True)

        await asyncio.gather(*workers, cleanup_task, return_exceptions=True)
        self.assertGreaterEqual(mock_process_queue_item.await_count, 1)


if __name__ == "__main__":
    unittest.main()
