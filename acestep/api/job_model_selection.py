"""Model selection helpers for per-job DiT handler routing."""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Optional, Tuple

_ON_DEMAND_MODEL_RE = re.compile(r"^acestep-v15-[A-Za-z0-9_-]+$")


def _on_demand_load_enabled() -> bool:
    """Whether a requested-but-unloaded model may be loaded at request time.

    Only safe with a single queue worker: the shared executor serializes
    generations, so no other job can be mid-generation on the handler
    being reloaded.
    """
    enabled = os.getenv("ACESTEP_ON_DEMAND_MODEL_LOAD", "false").lower() in (
        "1", "true", "yes",
    )
    return enabled and int(os.getenv("ACESTEP_QUEUE_WORKERS", "1")) == 1


def _load_model_on_demand(
    *,
    app_state: Any,
    requested_model: str,
    get_model_name: Callable[[str], str],
    job_id: str,
    log_fn: Callable[[str], None],
) -> Tuple[Any, str]:
    """Replace the primary model with ``requested_model``, downloading it first
    if needed. Runs in the generation executor thread (model loads block for
    tens of seconds; downloads for minutes)."""
    if not _ON_DEMAND_MODEL_RE.match(requested_model):
        raise ValueError(f"unknown model name: {requested_model!r}")
    init_kwargs = getattr(app_state, "_model_init_kwargs", None)
    if init_kwargs is None:
        raise RuntimeError("model init kwargs were not captured at startup")
    ensure_downloaded = getattr(app_state, "_ensure_model_downloaded", None)
    if ensure_downloaded is not None:
        ensure_downloaded(requested_model, app_state._checkpoint_dir)
    previous = get_model_name(app_state._config_path)
    log_fn(
        f"[API Server] Job {job_id}: Loading model on demand: "
        f"{requested_model} (replacing {previous})"
    )
    status_msg, ok = app_state.handler.initialize_service(
        config_path=requested_model, **init_kwargs
    )
    if not ok:
        raise RuntimeError(status_msg)
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
                return _load_model_on_demand(
                    app_state=app_state,
                    requested_model=requested_model,
                    get_model_name=get_model_name,
                    job_id=job_id,
                    log_fn=log_fn,
                )
            except Exception as exc:
                log_fn(
                    f"[API Server] Job {job_id}: On-demand load of "
                    f"'{requested_model}' failed ({exc}); using primary: "
                    f"{selected_model_name}"
                )
                return selected_handler, selected_model_name
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
