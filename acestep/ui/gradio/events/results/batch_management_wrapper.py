"""Foreground batch generation wrapper for UI streaming updates."""

import gc
import time as time_module

import gradio as gr
import torch
from loguru import logger

from acestep.ui.gradio.events.results.batch_management_helpers import (
    _build_saved_params,
    _extract_ui_core_outputs,
)
from acestep.ui.gradio.events.results.batch_queue import (
    store_batch_in_queue,
    update_batch_indicator,
    update_navigation_buttons,
)
from acestep.ui.gradio.events.results.generation_info import IS_WINDOWS
from acestep.ui.gradio.events.results.generation_progress import generate_with_progress
from acestep.ui.gradio.i18n import t


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
    """Wrap ``generate_with_progress`` with batch queue management state."""
    _ = generation_params_state  # reserved for API compatibility with wiring/state outputs
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
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
            ui_result = _extract_ui_core_outputs(partial_result)
            yield ui_result + (
                gr.skip(), gr.skip(), gr.skip(), gr.skip(),
                gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(),
            )

    result = final_result_from_inner
    if result is None:
        error_msg = t("messages.batch_failed", error="No generation result was produced")
        logger.warning("[generate_with_batch_management] generate_with_progress yielded no results")
        gr.Warning(error_msg)
        yield (gr.skip(),) * 55
        return

    all_audio_paths = result[8]

    if all_audio_paths is None:
        ui_result = _extract_ui_core_outputs(result)
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

    ui_core_list = list(_extract_ui_core_outputs(result))

    if auto_lrc and isinstance(extra_outputs_from_result, dict):
        lrcs = extra_outputs_from_result.get("lrcs", [""] * 8)
        for i in range(min(8, len(lrcs))):
            if lrcs[i]:
                ui_core_list[36 + i] = gr.update(value=lrcs[i], visible=True)

    logger.info(f"[generate_with_batch_management] Final yield: {len(ui_core_list)} core + 9 state")

    yield tuple(ui_core_list) + (
        current_batch_index, total_batches, batch_queue, next_params,
        batch_indicator_text,
        gr.update(interactive=can_prev),
        gr.update(interactive=can_next),
        next_batch_status_text,
        gr.update(interactive=True),
    )
    time_module.sleep(0.1)
