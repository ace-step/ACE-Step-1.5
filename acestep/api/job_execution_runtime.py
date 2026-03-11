"""Async job execution runtime helper for API queue workers."""

from __future__ import annotations

import asyncio
import time
import traceback
from typing import Any, Awaitable, Callable


async def run_one_job_runtime(
    *,
    app_state: Any,
    store: Any,
    job_id: str,
    req: Any,
    ensure_models_initialized_fn: Callable[[Any], Awaitable[None]],
    select_generation_handler_fn: Callable[..., tuple[Any, str]],
    get_model_name: Callable[[str], str],
    build_blocking_result_fn: Callable[[Any, str], dict[str, Any]],
    update_progress_job_cache_fn: Callable[..., None],
    update_terminal_job_cache_fn: Callable[..., None],
    map_status: Callable[[str], str],
    result_key_prefix: str,
    result_expire_seconds: int,
    log_fn: Callable[[str], None] = print,
) -> None:
    """Execute one queued job end-to-end with success/failure cache updates.

    Args:
        app_state: FastAPI app state object.
        store: Job store/cache facade.
        job_id: Current job identifier.
        req: Generation request object.
        ensure_models_initialized_fn: Async startup-guard callback.
        select_generation_handler_fn: Handler selection callback.
        get_model_name: Model-name resolver callback.
        build_blocking_result_fn: Blocking generation callback.
        update_progress_job_cache_fn: Local cache progress updater.
        update_terminal_job_cache_fn: Local cache terminal updater.
        map_status: Status mapping callback.
        result_key_prefix: Result key namespace prefix.
        result_expire_seconds: Result cache expiration window.
        log_fn: Logging callback.
    """

    job_store = app_state.job_store
    executor = app_state.executor

    await ensure_models_initialized_fn(app_state)
    job_store.mark_running(job_id)
    update_progress_job_cache_fn(
        app_state=app_state,
        store=store,
        job_id=job_id,
        progress=0.01,
        stage="running",
        map_status=map_status,
        result_key_prefix=result_key_prefix,
        result_expire_seconds=result_expire_seconds,
    )

    selected_handler, selected_model_name = select_generation_handler_fn(
        app_state=app_state,
        requested_model=req.model,
        get_model_name=get_model_name,
        job_id=job_id,
        log_fn=log_fn,
    )

    def _blocking_generate() -> dict[str, Any]:
        return build_blocking_result_fn(selected_handler, selected_model_name)

    t0 = time.time()
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(executor, _blocking_generate)
        job_store.mark_succeeded(job_id, result)
        update_terminal_job_cache_fn(
            app_state=app_state,
            store=store,
            job_id=job_id,
            result=result,
            status="succeeded",
            map_status=map_status,
            result_key_prefix=result_key_prefix,
            result_expire_seconds=result_expire_seconds,
        )
    except Exception as exc:
        error_traceback = traceback.format_exc()
        log_fn(f"[API Server] Job {job_id} FAILED: {exc}")
        log_fn(f"[API Server] Traceback:\n{error_traceback}")
        job_store.mark_failed(job_id, error_traceback)
        update_terminal_job_cache_fn(
            app_state=app_state,
            store=store,
            job_id=job_id,
            result=None,
            status="failed",
            map_status=map_status,
            result_key_prefix=result_key_prefix,
            result_expire_seconds=result_expire_seconds,
        )
    finally:
        try:
            if hasattr(selected_handler, "_empty_cache"):
                selected_handler._empty_cache()
            else:
                import torch

                if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                    torch.mps.empty_cache()
        except Exception:
            pass
        dt = max(0.0, time.time() - t0)
        async with app_state.stats_lock:
            app_state.recent_durations.append(dt)
            if app_state.recent_durations:
                app_state.avg_job_seconds = sum(app_state.recent_durations) / len(
                    app_state.recent_durations
                )
