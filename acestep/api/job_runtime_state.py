"""Runtime state helpers for API job execution flow."""

from __future__ import annotations

import os
from typing import Any, Optional

from acestep.api.jobs.local_cache_updates import update_local_cache, update_local_cache_progress


async def ensure_models_initialized(app_state: Any) -> None:
    """Ensure models are initialized, loading them lazily on first request if needed.

    If models were already loaded at startup (``ACESTEP_NO_INIT=false``), this
    returns immediately.  Otherwise it performs on-demand initialization using
    the kwargs stored on ``app_state._model_init_kwargs`` during lifespan setup.

    Args:
        app_state: Application state object containing initialization flags.

    Raises:
        RuntimeError: If model initialization previously failed.
    """

    # Fast path: already initialized
    if getattr(app_state, "_initialized", False):
        return

    # Previous init attempt failed — propagate the error
    if getattr(app_state, "_init_error", None):
        raise RuntimeError(app_state._init_error)

    # Lazy initialization with double-check locking
    async with app_state._init_lock:
        # Re-check after acquiring lock
        if getattr(app_state, "_initialized", False):
            return
        if getattr(app_state, "_init_error", None):
            raise RuntimeError(app_state._init_error)

        init_kwargs = getattr(app_state, "_model_init_kwargs", None)
        if init_kwargs is None:
            raise RuntimeError("Model not initialized and no init kwargs available")

        print("[API Server] First request received — lazy-loading models...")
        from acestep.api.startup_model_init import do_model_initialization

        # app_state belongs to app; recover the app reference via the
        # FastAPI convention: app_state._app or we pass app via kwargs.
        # The init kwargs were stored without 'app' — we need the app object.
        # We stored the kwargs from initialize_models_at_startup which has
        # access to 'app'. We need to find it. The app_state is app.state,
        # and app.state._app is not standard. Instead, we'll use a small
        # wrapper that sets _initialized on app_state directly.
        class _AppProxy:
            """Thin proxy so do_model_initialization can set app.state attrs."""

            def __init__(self, state: Any) -> None:
                self.state = state

        do_model_initialization(app=_AppProxy(app_state), **init_kwargs)


async def cleanup_job_temp_files(app_state: Any, job_id: str) -> None:
    """Delete temporary upload files tracked for a completed job.

    Args:
        app_state: Application state object containing temp-file tracking state.
        job_id: Job identifier whose tracked temp files should be deleted.
    """

    async with app_state.job_temp_files_lock:
        paths = app_state.job_temp_files.pop(job_id, [])
    for path in paths:
        try:
            os.remove(path)
        except Exception:
            pass


def update_terminal_job_cache(
    *,
    app_state: Any,
    store: Any,
    job_id: str,
    result: Optional[dict[str, Any]],
    status: str,
    map_status: Any,
    result_key_prefix: str,
    result_expire_seconds: int,
) -> None:
    """Persist final job result state in optional local cache.

    Args:
        app_state: Application state object containing optional local cache.
        store: Job store used for fetching current job data.
        job_id: Job identifier to update in local cache.
        result: Final job result payload, if present.
        status: Final status value (for example, ``succeeded`` or ``failed``).
        map_status: Callable that maps textual status to integer code.
        result_key_prefix: Cache key prefix for result records.
        result_expire_seconds: Cache TTL for result records.
    """

    update_local_cache(
        local_cache=getattr(app_state, "local_cache", None),
        store=store,
        job_id=job_id,
        result=result,
        status=status,
        map_status=map_status,
        result_key_prefix=result_key_prefix,
        result_expire_seconds=result_expire_seconds,
    )


def update_progress_job_cache(
    *,
    app_state: Any,
    store: Any,
    job_id: str,
    progress: float,
    stage: str,
    map_status: Any,
    result_key_prefix: str,
    result_expire_seconds: int,
) -> None:
    """Persist non-terminal job progress state in optional local cache.

    Args:
        app_state: Application state object containing optional local cache.
        store: Job store used for fetching current job data.
        job_id: Job identifier to update in local cache.
        progress: Progress value in ``[0.0, 1.0]``.
        stage: Text stage label for current progress.
        map_status: Callable that maps textual status to integer code.
        result_key_prefix: Cache key prefix for result records.
        result_expire_seconds: Cache TTL for result records.
    """

    update_local_cache_progress(
        local_cache=getattr(app_state, "local_cache", None),
        store=store,
        job_id=job_id,
        progress=progress,
        stage=stage,
        map_status=map_status,
        result_key_prefix=result_key_prefix,
        result_expire_seconds=result_expire_seconds,
    )
