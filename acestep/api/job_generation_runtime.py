"""Runtime helpers for executing generation runs and aggregating outputs."""

from __future__ import annotations

from typing import Any, Callable


def run_generation_with_optional_sequential_cover_mode(
    *,
    req: Any,
    job_id: str,
    handler_device: str,
    config: Any,
    params: Any,
    dit_handler: Any,
    llm_handler: Any,
    temp_audio_dir: str,
    generate_music_fn: Callable[..., Any],
    progress_cb: Callable[[float, str], None],
    log_fn: Callable[[str], None] = print,
) -> Any:
    """Run music generation and aggregate outputs across sequential MPS cover slices.

    Args:
        req: Generation request object.
        job_id: Job identifier for progress logs.
        handler_device: Device string for selected handler.
        config: GenerationConfig instance.
        params: GenerationParams instance.
        dit_handler: Active DiT handler.
        llm_handler: Optional active LLM handler.
        temp_audio_dir: Output directory for generated audio.
        generate_music_fn: Generation execution callback.
        progress_cb: Progress callback receiving value and optional description.
        log_fn: Logging callback for status messages.

    Returns:
        Any: Aggregated successful generation result object.

    Raises:
        RuntimeError: If generation fails or returns no results.
    """

    sequential_runs = 1
    if req.task_type == "cover" and handler_device == "mps":
        if config.batch_size is not None and config.batch_size > 1:
            sequential_runs = int(config.batch_size)
            config.batch_size = 1
            log_fn(
                f"[API Server] Job {job_id}: MPS cover sequential mode enabled "
                f"(runs={sequential_runs})"
            )

    def _progress_for_slice(start: float, end: float) -> Callable[[float, str], None]:
        base = {"seen": False, "value": 0.0}

        def _cb(value: float, desc: str = "") -> None:
            try:
                value_f = max(0.0, min(1.0, float(value)))
            except Exception:
                value_f = 0.0
            if not base["seen"]:
                base["seen"] = True
                base["value"] = value_f
            if value_f <= base["value"]:
                norm = 0.0
            else:
                denom = max(1e-6, 1.0 - base["value"])
                norm = min(1.0, (value_f - base["value"]) / denom)
            mapped = start + (end - start) * norm
            progress_cb(mapped, desc=desc)

        return _cb

    aggregated_result = None
    all_audios = []
    for run_idx in range(sequential_runs):
        if sequential_runs > 1:
            log_fn(f"[API Server] Job {job_id}: Sequential cover run {run_idx + 1}/{sequential_runs}")
        if sequential_runs > 1:
            start = run_idx / sequential_runs
            end = (run_idx + 1) / sequential_runs
            run_progress_cb = _progress_for_slice(start, end)
        else:
            run_progress_cb = progress_cb

        result = generate_music_fn(
            dit_handler=dit_handler,
            llm_handler=llm_handler,
            params=params,
            config=config,
            save_dir=temp_audio_dir,
            progress=run_progress_cb,
        )
        if not result.success:
            raise RuntimeError(f"Music generation failed: {result.error or result.status_message}")
        if aggregated_result is None:
            aggregated_result = result
        all_audios.extend(result.audios)

    if aggregated_result is None:
        raise RuntimeError("Music generation failed: no results")
    aggregated_result.audios = all_audios
    if not aggregated_result.success:
        raise RuntimeError(
            f"Music generation failed: {aggregated_result.error or aggregated_result.status_message}"
        )
    return aggregated_result
