"""Unit tests for queue worker loop helper functions."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from acestep.api.jobs.test_fakes import _DoneEvent, _FakeJobQueue, _FakeStore
from acestep.api.jobs.worker_loops import (
    process_queue_item,
    run_job_store_cleanup_loop,
)


class WorkerLoopTests(unittest.TestCase):
    """Behavior tests for extracted queue worker helper logic."""

    def test_process_queue_item_success_notifies_result_and_done(self):
        """Success path should emit result+done and cleanup queue bookkeeping."""

        async def _run() -> None:
            """Execute success-path queue item processing and assert notifications."""

            progress_queue = asyncio.Queue()
            done_event = _DoneEvent()
            record = SimpleNamespace(
                status="running",
                result=None,
                error=None,
                progress_queue=progress_queue,
                done_event=done_event,
            )
            store = _FakeStore(record=record)
            app_state = SimpleNamespace(
                pending_lock=asyncio.Lock(),
                pending_ids=["job-1"],
                job_queue=_FakeJobQueue(),
            )
            cleanup_calls = []

            async def _run_one_job(job_id: str, _req) -> None:
                """Mark record as succeeded and attach deterministic result payload."""

                record.status = "succeeded"
                record.result = {"job_id": job_id, "ok": True}

            async def _cleanup_job_temp_files(job_id: str) -> None:
                """Record cleanup invocation for assertion."""

                cleanup_calls.append(job_id)

            await process_queue_item(
                job_id="job-1",
                req=SimpleNamespace(),
                app_state=app_state,
                store=store,
                run_one_job=_run_one_job,
                cleanup_job_temp_files=_cleanup_job_temp_files,
            )

            msg1 = await progress_queue.get()
            msg2 = await progress_queue.get()
            self.assertEqual({"type": "result", "result": {"job_id": "job-1", "ok": True}}, msg1)
            self.assertEqual({"type": "done"}, msg2)
            self.assertTrue(done_event.was_set)
            self.assertEqual([], app_state.pending_ids)
            self.assertEqual(["job-1"], cleanup_calls)
            self.assertEqual(1, app_state.job_queue.task_done_calls)

        asyncio.run(_run())

    def test_process_queue_item_failure_marks_failed_and_notifies_error(self):
        """Failure path should mark failed, emit error+done, and perform cleanup."""

        async def _run() -> None:
            """Execute failure-path queue item processing and assert error signaling."""

            progress_queue = asyncio.Queue()
            done_event = _DoneEvent()
            record = SimpleNamespace(
                status="running",
                result=None,
                error=None,
                progress_queue=progress_queue,
                done_event=done_event,
            )
            store = _FakeStore(record=record)
            app_state = SimpleNamespace(
                pending_lock=asyncio.Lock(),
                pending_ids=["job-2"],
                job_queue=_FakeJobQueue(),
            )
            cleanup_calls = []

            async def _run_one_job(_job_id: str, _req) -> None:
                """Raise deterministic runtime error to exercise failure branch."""

                raise RuntimeError("boom")

            async def _cleanup_job_temp_files(job_id: str) -> None:
                """Record cleanup invocation for assertion."""

                cleanup_calls.append(job_id)

            await process_queue_item(
                job_id="job-2",
                req=SimpleNamespace(),
                app_state=app_state,
                store=store,
                run_one_job=_run_one_job,
                cleanup_job_temp_files=_cleanup_job_temp_files,
            )

            msg1 = await progress_queue.get()
            msg2 = await progress_queue.get()
            self.assertEqual({"type": "error", "content": "boom"}, msg1)
            self.assertEqual({"type": "done"}, msg2)
            self.assertTrue(done_event.was_set)
            self.assertEqual([("job-2", "boom")], store.mark_failed_calls)
            self.assertEqual([], app_state.pending_ids)
            self.assertEqual(["job-2"], cleanup_calls)
            self.assertEqual(1, app_state.job_queue.task_done_calls)

        asyncio.run(_run())

    def test_run_job_store_cleanup_loop_logs_cleanup_and_stops_on_cancel(self):
        """Cleanup loop should log cleanup stats and exit on cancellation."""

        async def _run() -> None:
            """Run one cleanup iteration and then cancel to verify graceful exit."""

            store = _FakeStore()
            store.cleanup_returns = [2]
            store.stats = {"total": 3, "succeeded": 2, "failed": 1}
            logs = []
            calls = {"count": 0}

            async def _sleep_fn(_seconds: float) -> None:
                """Allow first tick, then cancel loop on second tick."""

                calls["count"] += 1
                if calls["count"] == 1:
                    return
                raise asyncio.CancelledError

            await run_job_store_cleanup_loop(
                store=store,
                cleanup_interval_seconds=1,
                sleep_fn=_sleep_fn,
                log_fn=logs.append,
            )

            self.assertEqual(1, store.cleanup_call_count)
            self.assertEqual(1, len(logs))
            self.assertIn("Cleaned up 2 old jobs", logs[0])

        asyncio.run(_run())

    def test_run_job_store_cleanup_loop_logs_errors_and_continues(self):
        """Cleanup loop should log non-cancel exceptions and continue until cancelled."""

        async def _run() -> None:
            """Raise one cleanup error, continue, then cancel on subsequent tick."""

            store = _FakeStore()
            store.cleanup_returns = [RuntimeError("cleanup-failed"), 0]
            logs = []
            calls = {"count": 0}

            async def _sleep_fn(_seconds: float) -> None:
                """Permit two iterations before raising cancellation."""

                calls["count"] += 1
                if calls["count"] <= 2:
                    return
                raise asyncio.CancelledError

            await run_job_store_cleanup_loop(
                store=store,
                cleanup_interval_seconds=1,
                sleep_fn=_sleep_fn,
                log_fn=logs.append,
            )

            self.assertGreaterEqual(store.cleanup_call_count, 2)
            self.assertTrue(any("Job cleanup error: cleanup-failed" in line for line in logs))

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
