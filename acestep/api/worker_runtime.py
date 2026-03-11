"""Background worker task orchestration helpers for API server."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable

from acestep.api.jobs.worker_loops import process_queue_item, run_job_store_cleanup_loop


async def _queue_worker_loop(
    *,
    app_state: Any,
    store: Any,
    run_one_job: Callable[[str, Any], Awaitable[None]],
    cleanup_job_temp_files: Callable[[str], Awaitable[None]],
) -> None:
    """Continuously consume job queue entries and process each item."""

    while True:
        job_id, req = await app_state.job_queue.get()
        await process_queue_item(
            job_id=job_id,
            req=req,
            app_state=app_state,
            store=store,
            run_one_job=run_one_job,
            cleanup_job_temp_files=cleanup_job_temp_files,
        )


async def _job_store_cleanup_worker_loop(*, store: Any, cleanup_interval_seconds: int) -> None:
    """Run periodic completed-job cleanup loop."""

    await run_job_store_cleanup_loop(
        store=store,
        cleanup_interval_seconds=cleanup_interval_seconds,
    )


def start_worker_tasks(
    *,
    app_state: Any,
    store: Any,
    worker_count: int,
    run_one_job: Callable[[str, Any], Awaitable[None]],
    cleanup_job_temp_files: Callable[[str], Awaitable[None]],
    cleanup_interval_seconds: int,
) -> tuple[list[asyncio.Task], asyncio.Task]:
    """Start queue workers and cleanup worker; attach task refs to app state."""

    normalized_worker_count = max(1, worker_count)
    workers = [
        asyncio.create_task(
            _queue_worker_loop(
                app_state=app_state,
                store=store,
                run_one_job=run_one_job,
                cleanup_job_temp_files=cleanup_job_temp_files,
            )
        )
        for _ in range(normalized_worker_count)
    ]
    cleanup_task = asyncio.create_task(
        _job_store_cleanup_worker_loop(
            store=store,
            cleanup_interval_seconds=cleanup_interval_seconds,
        )
    )
    app_state.worker_tasks = workers
    app_state.cleanup_task = cleanup_task
    return workers, cleanup_task


def stop_worker_tasks(
    *,
    workers: list[asyncio.Task],
    cleanup_task: asyncio.Task,
    executor: ThreadPoolExecutor,
) -> None:
    """Cancel running worker tasks and shut down thread pool executor."""

    cleanup_task.cancel()
    for worker in workers:
        worker.cancel()
    executor.shutdown(wait=False, cancel_futures=True)
