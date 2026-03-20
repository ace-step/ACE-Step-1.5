"""Background AutoGen batch generation orchestration."""

import gc
import traceback

import gradio as gr
import torch
from loguru import logger

from acestep.ui.gradio.events.results.batch_management_helpers import (
    _apply_param_defaults,
    _extract_scores,
    _log_background_params,
)
from acestep.ui.gradio.events.results.batch_queue import store_batch_in_queue
from acestep.ui.gradio.events.results.generation_progress import generate_with_progress
from acestep.ui.gradio.i18n import t


def generate_next_batch_background(
    dit_handler, llm_handler,
    autogen_enabled, generation_params,
    current_batch_index, total_batches, batch_queue,
    is_format_caption,
    progress=gr.Progress(track_tqdm=True),
):
    """Generate the next batch in background when AutoGen is enabled.

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

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if (hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache")
                and hasattr(torch.backends, "mps")
                and torch.backends.mps.is_available()):
            torch.mps.empty_cache()

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
            fade_in_duration=params.get("fade_in_duration", 0.0),
            fade_out_duration=params.get("fade_out_duration", 0.0),
            latent_shift=params.get("latent_shift", 0.0),
            latent_rescale=params.get("latent_rescale", 1.0),
            repaint_mode=params.get("repaint_mode", "balanced"),
            repaint_strength=params.get("repaint_strength", 0.5),
            progress=progress,
        )

        final_result = None
        for partial_result in generator:
            final_result = partial_result

        if final_result is None:
            raise RuntimeError("generate_with_progress yielded no results")

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

    except Exception as exc:
        error_msg = t("messages.batch_failed", error=str(exc))
        gr.Warning(error_msg)
        batch_queue[next_batch_idx] = {
            "status": "error",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        return batch_queue, total_batches, error_msg, gr.update(interactive=False)
