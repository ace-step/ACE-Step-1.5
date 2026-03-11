"""Blocking generation orchestration helper for API jobs."""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from acestep.api.job_analysis_runtime import maybe_handle_analysis_only_modes
from acestep.api.job_generation_runtime import run_generation_with_optional_sequential_cover_mode
from acestep.api.job_llm_preparation import (
    ensure_llm_ready_for_request,
    prepare_llm_generation_inputs,
)
from acestep.api.job_runtime_state import update_progress_job_cache
from acestep.api.job_result_payload import build_generation_success_response
from acestep.api.job_generation_setup import build_generation_setup


def run_blocking_generate(
    *,
    app_state: Any,
    req: Any,
    job_id: str,
    store: Any,
    llm_handler: Any,
    selected_handler: Any,
    selected_model_name: str,
    map_status: Callable[[str], str],
    result_key_prefix: str,
    result_expire_seconds: int,
    get_project_root: Callable[[], str],
    get_model_name: Callable[[str], str],
    ensure_model_downloaded: Callable[[str, str], str],
    env_bool: Callable[[str, bool], bool],
    parse_description_hints: Callable[[str], tuple[str | None, bool]],
    parse_timesteps: Callable[[str | None], list[float] | None],
    is_instrumental: Callable[[str], bool],
    create_sample_fn: Callable[..., Any],
    format_sample_fn: Callable[..., Any],
    generate_music_fn: Callable[..., Any],
    default_dit_instruction: str,
    task_instructions: dict[str, str],
    build_generation_info_fn: Callable[..., str],
    path_to_audio_url_fn: Callable[[str], str],
    log_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Execute the blocking generation path for a job.

    Args:
        app_state: FastAPI app state object.
        req: Generation request object.
        job_id: Job identifier.
        store: Job store used for progress updates.
        llm_handler: LLM handler instance.
        selected_handler: Selected DiT handler instance.
        selected_model_name: Selected DiT model label.
        map_status: Status mapping callback for cache updates.
        result_key_prefix: Result key namespace prefix.
        result_expire_seconds: Result cache expiration window.
        get_project_root: Project-root callback.
        get_model_name: Model-name resolver callback.
        ensure_model_downloaded: Model download callback.
        env_bool: Environment boolean parser callback.
        parse_description_hints: Prompt-hints parser callback.
        parse_timesteps: Timesteps parser callback.
        is_instrumental: Instrumental detector callback.
        create_sample_fn: Sample generation callback.
        format_sample_fn: Sample formatting callback.
        generate_music_fn: Core generation callback.
        default_dit_instruction: Default instruction constant.
        task_instructions: Task instruction mapping.
        build_generation_info_fn: Generation-info builder callback.
        path_to_audio_url_fn: Audio path to URL callback.
        log_fn: Logging callback.

    Returns:
        dict[str, Any]: Final success payload for job completion.
    """

    def _ensure_llm_ready() -> None:
        ensure_llm_ready_for_request(
            app_state=app_state,
            llm_handler=llm_handler,
            req=req,
            get_project_root=get_project_root,
            get_model_name=get_model_name,
            ensure_model_downloaded=ensure_model_downloaded,
            env_bool=env_bool,
            log_fn=log_fn,
        )

    prepared_inputs = prepare_llm_generation_inputs(
        app_state=app_state,
        llm_handler=llm_handler,
        req=req,
        selected_handler_device=selected_handler.device,
        parse_description_hints=parse_description_hints,
        create_sample_fn=create_sample_fn,
        format_sample_fn=format_sample_fn,
        ensure_llm_ready_fn=_ensure_llm_ready,
        log_fn=log_fn,
    )

    generation_setup = build_generation_setup(
        req=req,
        caption=prepared_inputs.caption,
        global_caption=prepared_inputs.global_caption,
        lyrics=prepared_inputs.lyrics,
        bpm=prepared_inputs.bpm,
        key_scale=prepared_inputs.key_scale,
        time_signature=prepared_inputs.time_signature,
        audio_duration=prepared_inputs.audio_duration,
        thinking=prepared_inputs.thinking,
        sample_mode=prepared_inputs.sample_mode,
        format_has_duration=prepared_inputs.format_has_duration,
        use_cot_caption=prepared_inputs.use_cot_caption,
        use_cot_language=prepared_inputs.use_cot_language,
        lm_top_k=prepared_inputs.lm_top_k,
        lm_top_p=prepared_inputs.lm_top_p,
        parse_timesteps=parse_timesteps,
        is_instrumental=is_instrumental,
        default_dit_instruction=default_dit_instruction,
        task_instructions=task_instructions,
    )
    params = generation_setup.params
    config = generation_setup.config

    llm_is_initialized = getattr(app_state, "_llm_initialized", False)
    llm_to_pass = llm_handler if llm_is_initialized else None

    last_progress = {"value": -1.0, "time": 0.0, "stage": ""}

    def _progress_cb(value: float, desc: str = "") -> None:
        now = time.time()
        try:
            value_f = max(0.0, min(1.0, float(value)))
        except Exception:
            value_f = 0.0
        stage = desc or last_progress["stage"] or "running"
        if (
            value_f - last_progress["value"] >= 0.01
            or stage != last_progress["stage"]
            or (now - last_progress["time"]) >= 0.5
        ):
            last_progress["value"] = value_f
            last_progress["time"] = now
            last_progress["stage"] = stage
            store.update_progress(job_id, value_f, stage=stage)
            update_progress_job_cache(
                app_state=app_state,
                store=store,
                job_id=job_id,
                progress=value_f,
                stage=stage,
                map_status=map_status,
                result_key_prefix=result_key_prefix,
                result_expire_seconds=result_expire_seconds,
            )

    analysis_result = maybe_handle_analysis_only_modes(
        req=req,
        params=params,
        config=config,
        llm_handler=llm_to_pass,
        dit_handler=selected_handler,
        store=store,
        job_id=job_id,
    )
    if analysis_result is not None:
        return analysis_result

    result = run_generation_with_optional_sequential_cover_mode(
        req=req,
        job_id=job_id,
        handler_device=selected_handler.device,
        config=config,
        params=params,
        dit_handler=selected_handler,
        llm_handler=llm_to_pass,
        temp_audio_dir=app_state.temp_audio_dir,
        generate_music_fn=generate_music_fn,
        progress_cb=_progress_cb,
        log_fn=log_fn,
    )

    lm_model_name = os.getenv("ACESTEP_LM_MODEL_PATH", "acestep-5Hz-lm-0.6B")
    return build_generation_success_response(
        result=result,
        params=params,
        bpm=prepared_inputs.bpm,
        audio_duration=prepared_inputs.audio_duration,
        key_scale=prepared_inputs.key_scale,
        time_signature=prepared_inputs.time_signature,
        original_prompt=prepared_inputs.original_prompt,
        original_lyrics=prepared_inputs.original_lyrics,
        inference_steps=req.inference_steps,
        path_to_audio_url=path_to_audio_url_fn,
        build_generation_info=build_generation_info_fn,
        lm_model_name=lm_model_name,
        dit_model_name=selected_model_name,
    )
