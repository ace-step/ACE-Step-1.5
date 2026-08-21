"""Model selection helpers for per-job DiT handler routing."""

from __future__ import annotations

import os
import re
import time
import traceback
from typing import Any, Callable, Optional, Tuple

_ON_DEMAND_MODEL_RE = re.compile(r"^acestep-v15-[A-Za-z0-9_-]+$")

# How long a failed on-demand fetch blocks retries of the same model name.
# Long enough that a hot request loop fails fast instead of stalling the
# queue on every job, short enough that transient failures (network blips,
# registry hiccups) become retryable without a server restart.
_FAILED_FETCH_COOLDOWN_SEC = 300.0


def _single_worker(env_name: str) -> bool:
    """True when ``env_name`` resolves to one worker after the same
    ``max(1, …)`` normalization the runtime applies; unparsable values count
    as multiple so the feature stays off rather than guessing."""
    try:
        return max(1, int(os.getenv(env_name, "1"))) == 1
    except (TypeError, ValueError):
        return False


def _on_demand_load_enabled() -> bool:
    """Whether a requested-but-unloaded model may be loaded at request time.

    Only safe when generations and API-triggered initializations are both
    serialized: one queue worker (the shared executor serializes generation
    jobs) and one API executor thread (the ``/models`` init route can run
    ``initialize_service`` on the same handler without taking a lock this
    executor thread could share).
    """
    enabled = os.getenv("ACESTEP_ON_DEMAND_MODEL_LOAD", "false").lower() in (
        "1", "true", "yes",
    )
    return (
        enabled
        and _single_worker("ACESTEP_QUEUE_WORKERS")
        and _single_worker("ACESTEP_API_WORKERS")
    )


def _prepare_on_demand_model(app_state: Any, requested_model: str) -> None:
    """Validate and fetch ``requested_model`` without touching the handler.

    Any failure here is safe to fall back from — the primary handler has not
    been mutated. Download failures are cached for ``_FAILED_FETCH_COOLDOWN_SEC``
    so a repeatedly requested unavailable name fails fast instead of stalling
    the queue on every job, while transient errors stay retryable.
    """
    if not _ON_DEMAND_MODEL_RE.match(requested_model):
        raise ValueError(f"unknown model name: {requested_model!r}")
    failed = getattr(app_state, "_on_demand_failed_models", None)
    if failed is None:
        failed = {}
        app_state._on_demand_failed_models = failed
    failed_at = failed.get(requested_model)
    if failed_at is not None:
        elapsed = time.monotonic() - failed_at
        if elapsed < _FAILED_FETCH_COOLDOWN_SEC:
            raise RuntimeError(
                f"a fetch of {requested_model!r} failed {elapsed:.0f}s ago; "
                f"retry blocked for {_FAILED_FETCH_COOLDOWN_SEC - elapsed:.0f}s"
            )
        del failed[requested_model]
    if getattr(app_state, "_service_init_kwargs", None) is None:
        raise RuntimeError("service init kwargs were not captured at startup")
    ensure_downloaded = getattr(app_state, "_ensure_model_downloaded", None)
    if ensure_downloaded is not None:
        try:
            ensure_downloaded(requested_model, app_state._checkpoint_dir)
        except Exception:
            failed[requested_model] = time.monotonic()
            raise


def _swap_primary_model(
    *,
    app_state: Any,
    requested_model: str,
    get_model_name: Callable[[str], str],
    job_id: str,
    log_fn: Callable[[str], None],
) -> Tuple[Any, str]:
    """Replace the primary model with the already-downloaded
    ``requested_model``. Runs in the generation executor thread (loads block
    for tens of seconds).

    ``initialize_service`` mutates the primary handler in place, so a failure
    here may leave it torn: the job must fail rather than fall back to a
    handler in unknown state. The config path is cleared so subsequent
    requests re-attempt a full load instead of short-circuiting onto it.
    """
    previous = get_model_name(app_state._config_path)
    log_fn(
        f"[API Server] Job {job_id}: Loading model on demand: "
        f"{requested_model} (replacing {previous})"
    )
    try:
        status_msg, ok = app_state.handler.initialize_service(
            config_path=requested_model, **app_state._service_init_kwargs
        )
    except Exception:
        app_state._config_path = ""
        raise
    if not ok:
        app_state._config_path = ""
        raise RuntimeError(f"on-demand load of {requested_model!r} failed: {status_msg}")
    app_state._config_path = requested_model
    log_fn(f"[API Server] Job {job_id}: Model loaded on demand: {requested_model}")
    return app_state.handler, requested_model


def select_generation_handler(
    *,
    app_state: Any,
    requested_model: Optional[str],
    get_model_name: Callable[[str], str],
    job_id: str,
    log_fn: Callable[[str], None] = print,
) -> Tuple[Any, str]:
    """Resolve the handler/model name for a generation job request.

    Args:
        app_state: Application state object containing primary/secondary/third handlers and config paths.
        requested_model: Optional requested model name from request payload.
        get_model_name: Callable that normalizes config path to display model name.
        job_id: Current job identifier for log messages.
        log_fn: Logger callable used for parity with existing print-based logs.

    Returns:
        Tuple of ``(selected_handler, selected_model_name)``.
    """

    selected_handler = app_state.handler
    selected_model_name = get_model_name(app_state._config_path)

    if not requested_model:
        return selected_handler, selected_model_name

    # Requesting the model that is already primary needs no routing — and,
    # with on-demand loading enabled, must not trigger a pointless reload.
    if requested_model == selected_model_name:
        return selected_handler, selected_model_name

    model_matched = False

    if app_state.handler2 and getattr(app_state, "_initialized2", False):
        model2_name = get_model_name(app_state._config_path2)
        if requested_model == model2_name:
            selected_handler = app_state.handler2
            selected_model_name = model2_name
            model_matched = True
            log_fn(f"[API Server] Job {job_id}: Using second model: {model2_name}")

    if not model_matched and app_state.handler3 and getattr(app_state, "_initialized3", False):
        model3_name = get_model_name(app_state._config_path3)
        if requested_model == model3_name:
            selected_handler = app_state.handler3
            selected_model_name = model3_name
            model_matched = True
            log_fn(f"[API Server] Job {job_id}: Using third model: {model3_name}")

    if not model_matched:
        if _on_demand_load_enabled():
            try:
                _prepare_on_demand_model(app_state, requested_model)
            except Exception as exc:
                log_fn(
                    f"[API Server] Job {job_id}: On-demand fetch of "
                    f"{requested_model!r} failed ({exc}); using primary: "
                    f"{selected_model_name}\n{traceback.format_exc()}"
                )
                return selected_handler, selected_model_name
            # Past this point the primary handler gets mutated in place;
            # failures propagate and fail the job (see _swap_primary_model).
            return _swap_primary_model(
                app_state=app_state,
                requested_model=requested_model,
                get_model_name=get_model_name,
                job_id=job_id,
                log_fn=log_fn,
            )
        available_models = [get_model_name(app_state._config_path)]
        if app_state.handler2 and getattr(app_state, "_initialized2", False):
            available_models.append(get_model_name(app_state._config_path2))
        if app_state.handler3 and getattr(app_state, "_initialized3", False):
            available_models.append(get_model_name(app_state._config_path3))
        log_fn(
            f"[API Server] Job {job_id}: Model '{requested_model}' not found in "
            f"{available_models}, using primary: {selected_model_name}"
        )

    return selected_handler, selected_model_name
