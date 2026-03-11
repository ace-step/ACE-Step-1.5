"""Model selection helpers for per-job DiT handler routing."""

from __future__ import annotations

from typing import Any, Callable, Optional, Tuple


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
