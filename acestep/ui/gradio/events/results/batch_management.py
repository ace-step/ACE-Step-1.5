"""Batch orchestration and AutoGen background generation.

Wraps the core generation loop with batch queue bookkeeping and
provides the background generator for the AutoGen workflow.
"""
import time as time_module
import traceback

import gradio as gr
from loguru import logger

from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.events.results.generation_info import IS_WINDOWS
from acestep.ui.gradio.events.results.generation_progress import generate_with_progress
from acestep.ui.gradio.events.results.batch_queue import (
    store_batch_in_queue,
    update_batch_indicator,
    update_navigation_buttons,
)


def generate_with_batch_management(
    dit_handler, llm_handler,
    captions, lyrics, bpm, key_scale, time_signature, vocal_language,
    inference_steps, guidance_scale, random_seed_checkbox, seed,
    reference_audio, audio_duration, batch_size_input, src_audio,
    text2music_audio_code_string, repainting_start, repainting_end,
    instruction_display_gen, audio_cover_strength, cover_noise_strength, task_type,
    use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method,
    custom_timesteps, audio_format, lm_temperature,
    think_checkbox, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
    use_cot_metas, use_cot_caption, use_cot_language, is_format_caption,
    constrained_decoding_debug,
    allow_lm_batch,
    auto_score,
    auto_lrc,
    score_scale,
    lm_batch_chunk_size,
    track_name,
    complete_track_classes,
    enable_normalization,
    normalization_db,
    latent_shift,
    latent_rescale,
    autogen_checkbox,
    current_batch_index,
    total_batches,
    batch_queue,
    generation_params_state,
    progress=gr.Progress(track_tqdm=True),
):
    """Wrapper for ``generate_with_progress`` that adds batch queue management.

    Yields progressive UI updates and, on completion, stores the batch
    results in *batch_queue* and updates navigation state.
    """
    generator = generate_with_progress(
        dit_handler, llm_handler,
        captions, lyrics, bpm, key_scale, time_signature, vocal_language,
        inference_steps, guidance_scale, random_seed_checkbox, seed,
        reference_audio, audio_duration, batch_size_input, src_audio,
        text2music_audio_code_string, repainting_start, repainting_end,
        instruction_display_gen, audio_cover_strength, cover_noise_strength, task_type,
        use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method,
        custom_timesteps, audio_format, lm_temperature,
        think_checkbox, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
        use_cot_metas, use_cot_caption, use_cot_language, is_format_caption,
        constrained_decoding_debug,
        allow_lm_batch, auto_score, auto_lrc, score_scale,
        lm_batch_chunk_size,
        enable_normalization, normalization_db, latent_shift, latent_rescale,
        progress,
    )

    final_result_from_inner = None
    for partial_result in generator:
        final_result_from_inner = partial_result
        if not IS_WINDOWS:
            ui_result = partial_result[:-2] if len(partial_result) > 47 else (
                partial_result[:-1] if len(partial_result) > 46 else partial_result
            )
            yield ui_result + (
                gr.skip(), gr.skip(), gr.skip(), gr.skip(),
                gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(),
            )

    result = final_result_from_inner
    all_audio_paths = result[8]

    if all_audio_paths is None:
        ui_result = result[:-2] if len(result) > 47 else (
            result[:-1] if len(result) > 46 else result
        )
        yield ui_result + (
            gr.skip(), gr.skip(), gr.skip(), gr.skip(),
            gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(),
        )
        return

    generation_info = result[9]
    seed_value_for_ui = result[11]
    lm_generated_metadata = result[44]

    raw_codes_list = result[47] if len(result) > 47 else [""] * 8
    generated_codes_batch = raw_codes_list if isinstance(raw_codes_list, list) else [""] * 8
    generated_codes_single = generated_codes_batch[0] if generated_codes_batch else ""

    if allow_lm_batch and batch_size_input >= 2:
        codes_to_store = generated_codes_batch[:int(batch_size_input)]
    else:
        codes_to_store = generated_codes_single

    saved_params = _build_saved_params(
        captions, lyrics, bpm, key_scale, time_signature, vocal_language,
        inference_steps, guidance_scale, random_seed_checkbox, seed,
        reference_audio, audio_duration, batch_size_input, src_audio,
        text2music_audio_code_string, repainting_start, repainting_end,
        instruction_display_gen, audio_cover_strength, cover_noise_strength, task_type,
        use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method,
        audio_format, lm_temperature,
        think_checkbox, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
        use_cot_metas, use_cot_caption, use_cot_language,
        constrained_decoding_debug, allow_lm_batch, auto_score, auto_lrc,
        score_scale, lm_batch_chunk_size,
        track_name, complete_track_classes,
        enable_normalization, normalization_db, latent_shift, latent_rescale,
    )

    next_params = saved_params.copy()
    next_params["text2music_audio_code_string"] = ""
    next_params["random_seed_checkbox"] = True

    extra_outputs_from_result = result[46] if len(result) > 46 and result[46] is not None else {}

    batch_queue = store_batch_in_queue(
        batch_queue, current_batch_index,
        all_audio_paths, generation_info, seed_value_for_ui,
        codes=codes_to_store,
        allow_lm_batch=allow_lm_batch,
        batch_size=int(batch_size_input),
        generation_params=saved_params,
        lm_generated_metadata=lm_generated_metadata,
        extra_outputs=extra_outputs_from_result,
        status="completed",
    )

    if auto_lrc and extra_outputs_from_result:
        batch_queue[current_batch_index]["lrcs"] = extra_outputs_from_result.get("lrcs", [""] * 8)
        batch_queue[current_batch_index]["subtitles"] = extra_outputs_from_result.get("subtitles", [None] * 8)

    total_batches = max(total_batches, current_batch_index + 1)
    batch_indicator_text = update_batch_indicator(current_batch_index, total_batches)
    can_prev, can_next = update_navigation_buttons(current_batch_index, total_batches)

    next_batch_status_text = t("messages.autogen_enabled") if autogen_checkbox else ""

    ui_core = result[:46]
    logger.info(f"[generate_with_batch_management] Final yield: {len(ui_core)} core + 9 state")

    yield tuple(ui_core) + (
        current_batch_index, total_batches, batch_queue, next_params,
        batch_indicator_text,
        gr.update(interactive=can_prev),
        gr.update(interactive=can_next),
        next_batch_status_text,
        gr.update(interactive=True),
    )
    time_module.sleep(0.1)


def generate_next_batch_background(
    dit_handler, llm_handler,
    autogen_enabled, generation_params,
    current_batch_index, total_batches, batch_queue,
    is_format_caption,
    progress=gr.Progress(track_tqdm=True),
):
    """Generate next batch in background if AutoGen is enabled.

    Returns:
        Tuple of ``(batch_queue, total_batches, status_text, next_btn_update)``.
    """
    if not autogen_enabled:
        return batch_queue, total_batches, "", gr.update(interactive=False)

    next_batch_idx = current_batch_index + 1

    if next_batch_idx in batch_queue and batch_queue[next_batch_idx].get("status") == "completed":
        total_batches = max(total_batches, next_batch_idx + 1)
        return (
            batch_queue, total_batches,
            t("messages.batch_ready", n=next_batch_idx + 1),
            gr.update(interactive=True),
        )

    total_batches = next_batch_idx + 1
    gr.Info(t("messages.batch_generating", n=next_batch_idx + 1))

    params = generation_params.copy()
    _log_background_params(params, next_batch_idx)

    try:
        _apply_param_defaults(params)

        generator = generate_with_progress(
            dit_handler, llm_handler,
            captions=params.get("captions"),
            lyrics=params.get("lyrics"),
            bpm=params.get("bpm"),
            key_scale=params.get("key_scale"),
            time_signature=params.get("time_signature"),
            vocal_language=params.get("vocal_language"),
            inference_steps=params.get("inference_steps"),
            guidance_scale=params.get("guidance_scale"),
            random_seed_checkbox=params.get("random_seed_checkbox"),
            seed=params.get("seed"),
            reference_audio=params.get("reference_audio"),
            audio_duration=params.get("audio_duration"),
            batch_size_input=params.get("batch_size_input"),
            src_audio=params.get("src_audio"),
            text2music_audio_code_string=params.get("text2music_audio_code_string"),
            repainting_start=params.get("repainting_start"),
            repainting_end=params.get("repainting_end"),
            instruction_display_gen=params.get("instruction_display_gen"),
            audio_cover_strength=params.get("audio_cover_strength"),
            cover_noise_strength=params.get("cover_noise_strength", 0.0),
            task_type=params.get("task_type"),
            use_adg=params.get("use_adg"),
            cfg_interval_start=params.get("cfg_interval_start"),
            cfg_interval_end=params.get("cfg_interval_end"),
            shift=params.get("shift"),
            infer_method=params.get("infer_method"),
            custom_timesteps=params.get("custom_timesteps"),
            audio_format=params.get("audio_format"),
            lm_temperature=params.get("lm_temperature"),
            think_checkbox=params.get("think_checkbox"),
            lm_cfg_scale=params.get("lm_cfg_scale"),
            lm_top_k=params.get("lm_top_k"),
            lm_top_p=params.get("lm_top_p"),
            lm_negative_prompt=params.get("lm_negative_prompt"),
            use_cot_metas=params.get("use_cot_metas"),
            use_cot_caption=params.get("use_cot_caption"),
            use_cot_language=params.get("use_cot_language"),
            is_format_caption=is_format_caption,
            constrained_decoding_debug=params.get("constrained_decoding_debug"),
            allow_lm_batch=params.get("allow_lm_batch"),
            auto_score=params.get("auto_score"),
            auto_lrc=params.get("auto_lrc"),
            score_scale=params.get("score_scale"),
            lm_batch_chunk_size=params.get("lm_batch_chunk_size"),
            enable_normalization=params.get("enable_normalization"),
            normalization_db=params.get("normalization_db"),
            latent_shift=params.get("latent_shift", 0.0),
            latent_rescale=params.get("latent_rescale", 1.0),
            progress=progress,
        )

        final_result = None
        for partial_result in generator:
            final_result = partial_result

        all_audio_paths = final_result[8]
        generation_info = final_result[9]
        seed_value_for_ui = final_result[11]
        lm_generated_metadata = final_result[44]

        raw_codes_list = final_result[47] if len(final_result) > 47 else [""] * 8
        generated_codes_batch = raw_codes_list if isinstance(raw_codes_list, list) else [""] * 8
        generated_codes_single = generated_codes_batch[0] if generated_codes_batch else ""

        extra_outputs_from_bg = final_result[46] if len(final_result) > 46 and final_result[46] is not None else {}

        scores_from_bg = _extract_scores(final_result)

        batch_size = params.get("batch_size_input", 2)
        allow_lm_batch_val = params.get("allow_lm_batch", False)
        if allow_lm_batch_val and batch_size >= 2:
            codes_to_store = generated_codes_batch[:int(batch_size)]
        else:
            codes_to_store = generated_codes_single

        logger.info(f"Codes extraction for Batch {next_batch_idx + 1}:")
        logger.info(f"  - extra_outputs_from_bg exists: {extra_outputs_from_bg is not None}")
        logger.info(f"  - scores_from_bg: {[bool(s) for s in scores_from_bg]}")

        batch_queue = store_batch_in_queue(
            batch_queue, next_batch_idx,
            all_audio_paths, generation_info, seed_value_for_ui,
            codes=codes_to_store,
            scores=scores_from_bg,
            allow_lm_batch=allow_lm_batch_val,
            batch_size=int(batch_size),
            generation_params=params,
            lm_generated_metadata=lm_generated_metadata,
            extra_outputs=extra_outputs_from_bg,
            status="completed",
        )

        auto_lrc_flag = params.get("auto_lrc", False)
        if auto_lrc_flag and extra_outputs_from_bg:
            batch_queue[next_batch_idx]["lrcs"] = extra_outputs_from_bg.get("lrcs", [""] * 8)
            batch_queue[next_batch_idx]["subtitles"] = extra_outputs_from_bg.get("subtitles", [None] * 8)

        logger.info(f"Batch {next_batch_idx + 1} stored in queue successfully")

        return (
            batch_queue, total_batches,
            t("messages.batch_ready", n=next_batch_idx + 1),
            gr.update(interactive=True),
        )

    except Exception as e:
        error_msg = t("messages.batch_failed", error=str(e))
        gr.Warning(error_msg)
        batch_queue[next_batch_idx] = {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        return batch_queue, total_batches, error_msg, gr.update(interactive=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_saved_params(
    captions, lyrics, bpm, key_scale, time_signature, vocal_language,
    inference_steps, guidance_scale, random_seed_checkbox, seed,
    reference_audio, audio_duration, batch_size_input, src_audio,
    text2music_audio_code_string, repainting_start, repainting_end,
    instruction_display_gen, audio_cover_strength, cover_noise_strength, task_type,
    use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method,
    audio_format, lm_temperature,
    think_checkbox, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
    use_cot_metas, use_cot_caption, use_cot_language,
    constrained_decoding_debug, allow_lm_batch, auto_score, auto_lrc,
    score_scale, lm_batch_chunk_size,
    track_name, complete_track_classes,
    enable_normalization, normalization_db, latent_shift, latent_rescale,
):
    """Build the parameter snapshot dict for batch history."""
    return {
        "captions": captions, "lyrics": lyrics, "bpm": bpm,
        "key_scale": key_scale, "time_signature": time_signature,
        "vocal_language": vocal_language, "inference_steps": inference_steps,
        "guidance_scale": guidance_scale,
        "random_seed_checkbox": random_seed_checkbox, "seed": seed,
        "reference_audio": reference_audio, "audio_duration": audio_duration,
        "batch_size_input": batch_size_input, "src_audio": src_audio,
        "text2music_audio_code_string": text2music_audio_code_string,
        "repainting_start": repainting_start, "repainting_end": repainting_end,
        "instruction_display_gen": instruction_display_gen,
        "audio_cover_strength": audio_cover_strength,
        "cover_noise_strength": cover_noise_strength,
        "task_type": task_type, "use_adg": use_adg,
        "cfg_interval_start": cfg_interval_start,
        "cfg_interval_end": cfg_interval_end,
        "shift": shift, "infer_method": infer_method,
        "audio_format": audio_format, "lm_temperature": lm_temperature,
        "think_checkbox": think_checkbox, "lm_cfg_scale": lm_cfg_scale,
        "lm_top_k": lm_top_k, "lm_top_p": lm_top_p,
        "lm_negative_prompt": lm_negative_prompt,
        "use_cot_metas": use_cot_metas, "use_cot_caption": use_cot_caption,
        "use_cot_language": use_cot_language,
        "constrained_decoding_debug": constrained_decoding_debug,
        "allow_lm_batch": allow_lm_batch,
        "auto_score": auto_score, "auto_lrc": auto_lrc,
        "score_scale": score_scale, "lm_batch_chunk_size": lm_batch_chunk_size,
        "track_name": track_name, "complete_track_classes": complete_track_classes,
        "enable_normalization": enable_normalization,
        "normalization_db": normalization_db,
        "latent_shift": latent_shift, "latent_rescale": latent_rescale,
    }


def _log_background_params(params, next_batch_idx):
    """Log parameters for background generation debugging."""
    logger.info(f"========== BACKGROUND GENERATION BATCH {next_batch_idx + 1} ==========")
    logger.info(f"  - captions: {params.get('captions', 'N/A')}")
    lyr = params.get('lyrics')
    logger.info(f"  - lyrics: {lyr[:50]}..." if lyr else "  - lyrics: N/A")
    logger.info(f"  - bpm: {params.get('bpm')}")
    logger.info(f"  - batch_size_input: {params.get('batch_size_input')}")
    logger.info(f"  - allow_lm_batch: {params.get('allow_lm_batch')}")
    logger.info(f"  - think_checkbox: {params.get('think_checkbox')}")
    logger.info(f"  - lm_temperature: {params.get('lm_temperature')}")
    logger.info(f"  - track_name: {params.get('track_name')}")
    codes_val = params.get('text2music_audio_code_string')
    logger.info(f"  - text2music_audio_code_string: {'<CLEARED>' if codes_val == '' else 'HAS_VALUE'}")
    logger.info("=========================================================")


def _apply_param_defaults(params):
    """Fill missing keys in *params* with safe defaults."""
    defaults = {
        "captions": "", "lyrics": "", "bpm": None, "key_scale": "",
        "time_signature": "", "vocal_language": "unknown",
        "inference_steps": 8, "guidance_scale": 7.0,
        "random_seed_checkbox": True, "seed": "-1",
        "reference_audio": None, "audio_duration": -1,
        "batch_size_input": 2, "src_audio": None,
        "text2music_audio_code_string": "",
        "repainting_start": 0.0, "repainting_end": -1,
        "instruction_display_gen": "",
        "audio_cover_strength": 1.0, "cover_noise_strength": 0.0,
        "task_type": "text2music", "use_adg": False,
        "cfg_interval_start": 0.0, "cfg_interval_end": 1.0,
        "shift": 1.0, "infer_method": "ode", "custom_timesteps": "",
        "audio_format": "flac", "lm_temperature": 0.85,
        "think_checkbox": True, "lm_cfg_scale": 2.0,
        "lm_top_k": 0, "lm_top_p": 0.9,
        "lm_negative_prompt": "NO USER INPUT",
        "use_cot_metas": True, "use_cot_caption": True,
        "use_cot_language": True,
        "constrained_decoding_debug": False,
        "allow_lm_batch": True, "auto_score": False,
        "auto_lrc": False, "score_scale": 0.5,
        "lm_batch_chunk_size": 8,
        "track_name": None, "complete_track_classes": [],
        "enable_normalization": True, "normalization_db": -1.0,
        "latent_shift": 0.0, "latent_rescale": 1.0,
    }
    for k, v in defaults.items():
        params.setdefault(k, v)


def _extract_scores(final_result):
    """Extract score strings from generation result tuple indices 12-19."""
    scores = []
    for idx in range(12, 20):
        if idx < len(final_result):
            val = final_result[idx]
            if hasattr(val, 'value'):
                scores.append(val.value if val.value else "")
            elif isinstance(val, str):
                scores.append(val)
            else:
                scores.append("")
        else:
            scores.append("")
    return scores
