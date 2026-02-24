"""Batch queue CRUD, parameter capture, and restore.

Manages the in-memory batch queue that stores generation results and
parameters for navigation, replay, and AutoGen workflows.
"""
import datetime

import gradio as gr

from acestep.ui.gradio.i18n import t


def store_batch_in_queue(
    batch_queue,
    batch_index,
    audio_paths,
    generation_info,
    seeds,
    codes=None,
    scores=None,
    allow_lm_batch=False,
    batch_size=2,
    generation_params=None,
    lm_generated_metadata=None,
    extra_outputs=None,
    status="completed",
):
    """Store batch results in queue with all generation parameters.

    Args:
        batch_queue: The mutable batch queue dict.
        batch_index: Index of this batch.
        audio_paths: List of generated audio file paths.
        generation_info: Formatted generation timing string.
        seeds: Seed value(s) used.
        codes: Audio codes (list for batch, string for single).
        scores: List of score display strings.
        allow_lm_batch: Whether batch LM mode was used.
        batch_size: Batch size used.
        generation_params: Complete parameter dictionary.
        lm_generated_metadata: LM metadata for scoring.
        extra_outputs: Tensor dict for LRC generation.
        status: Batch status string.

    Returns:
        The updated *batch_queue*.
    """
    batch_queue[batch_index] = {
        "status": status,
        "audio_paths": audio_paths,
        "generation_info": generation_info,
        "seeds": seeds,
        "codes": codes,
        "scores": scores if scores else [""] * 8,
        "allow_lm_batch": allow_lm_batch,
        "batch_size": batch_size,
        "generation_params": generation_params if generation_params else {},
        "lm_generated_metadata": lm_generated_metadata,
        "extra_outputs": extra_outputs if extra_outputs else {},
        "timestamp": datetime.datetime.now().isoformat(),
    }
    return batch_queue


def update_batch_indicator(current_batch, total_batches):
    """Return localised batch indicator text."""
    return t("results.batch_indicator", current=current_batch + 1, total=total_batches)


def update_navigation_buttons(current_batch, total_batches):
    """Determine navigation button interactive states.

    Returns:
        Tuple of ``(can_go_previous, can_go_next)`` booleans.
    """
    return current_batch > 0, current_batch < total_batches - 1


def capture_current_params(
    captions, lyrics, bpm, key_scale, time_signature, vocal_language,
    inference_steps, guidance_scale, random_seed_checkbox, seed,
    reference_audio, audio_duration, batch_size_input, src_audio,
    text2music_audio_code_string, repainting_start, repainting_end,
    instruction_display_gen, audio_cover_strength, cover_noise_strength, task_type,
    use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method,
    custom_timesteps, audio_format, lm_temperature,
    think_checkbox, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
    use_cot_metas, use_cot_caption, use_cot_language,
    constrained_decoding_debug, allow_lm_batch, auto_score, auto_lrc,
    score_scale, lm_batch_chunk_size,
    track_name, complete_track_classes,
    enable_normalization, normalization_db,
    latent_shift, latent_rescale,
):
    """Capture current UI parameters for next-batch generation.

    Audio codes are cleared so AutoGen batches always generate fresh content.
    """
    return {
        "captions": captions,
        "lyrics": lyrics,
        "bpm": bpm,
        "key_scale": key_scale,
        "time_signature": time_signature,
        "vocal_language": vocal_language,
        "inference_steps": inference_steps,
        "guidance_scale": guidance_scale,
        "random_seed_checkbox": True,
        "seed": seed,
        "reference_audio": reference_audio,
        "audio_duration": audio_duration,
        "batch_size_input": batch_size_input,
        "src_audio": src_audio,
        "text2music_audio_code_string": "",
        "repainting_start": repainting_start,
        "repainting_end": repainting_end,
        "instruction_display_gen": instruction_display_gen,
        "audio_cover_strength": audio_cover_strength,
        "cover_noise_strength": cover_noise_strength,
        "task_type": task_type,
        "use_adg": use_adg,
        "cfg_interval_start": cfg_interval_start,
        "cfg_interval_end": cfg_interval_end,
        "shift": shift,
        "infer_method": infer_method,
        "custom_timesteps": custom_timesteps,
        "audio_format": audio_format,
        "lm_temperature": lm_temperature,
        "think_checkbox": think_checkbox,
        "lm_cfg_scale": lm_cfg_scale,
        "lm_top_k": lm_top_k,
        "lm_top_p": lm_top_p,
        "lm_negative_prompt": lm_negative_prompt,
        "use_cot_metas": use_cot_metas,
        "use_cot_caption": use_cot_caption,
        "use_cot_language": use_cot_language,
        "constrained_decoding_debug": constrained_decoding_debug,
        "allow_lm_batch": allow_lm_batch,
        "auto_score": auto_score,
        "auto_lrc": auto_lrc,
        "score_scale": score_scale,
        "lm_batch_chunk_size": lm_batch_chunk_size,
        "track_name": track_name,
        "complete_track_classes": complete_track_classes,
        "enable_normalization": enable_normalization,
        "normalization_db": normalization_db,
        "latent_shift": latent_shift,
        "latent_rescale": latent_rescale,
    }


def restore_batch_parameters(current_batch_index, batch_queue):
    """Restore parameters from the currently viewed batch to the Input UI.

    Args:
        current_batch_index: Index of the batch to restore from.
        batch_queue: The batch queue dict.

    Returns:
        Tuple of restored parameter values for Gradio outputs.
    """
    if current_batch_index not in batch_queue:
        gr.Warning(t("messages.no_batch_data"))
        return [gr.update()] * 20

    batch_data = batch_queue[current_batch_index]
    params = batch_data.get("generation_params", {})

    captions = params.get("captions", "")
    lyrics = params.get("lyrics", "")
    bpm = params.get("bpm", None)
    key_scale = params.get("key_scale", "")
    time_signature = params.get("time_signature", "")
    vocal_language = params.get("vocal_language", "unknown")
    audio_duration = params.get("audio_duration", -1)
    batch_size_input = params.get("batch_size_input", 2)
    inference_steps = params.get("inference_steps", 8)
    lm_temperature = params.get("lm_temperature", 0.85)
    lm_cfg_scale = params.get("lm_cfg_scale", 2.0)
    lm_top_k = params.get("lm_top_k", 0)
    lm_top_p = params.get("lm_top_p", 0.9)
    think_checkbox = params.get("think_checkbox", True)
    use_cot_caption = params.get("use_cot_caption", True)
    use_cot_language = params.get("use_cot_language", True)
    allow_lm_batch = params.get("allow_lm_batch", True)
    track_name = params.get("track_name", None)
    complete_track_classes = params.get("complete_track_classes", [])
    enable_normalization = params.get("enable_normalization", True)
    normalization_db = params.get("normalization_db", -1.0)
    latent_shift = params.get("latent_shift", 0.0)
    latent_rescale = params.get("latent_rescale", 1.0)

    stored_codes = batch_data.get("codes", "")
    if stored_codes:
        codes_main = stored_codes[0] if isinstance(stored_codes, list) and stored_codes else stored_codes
    else:
        codes_main = ""

    gr.Info(t("messages.params_restored", n=current_batch_index + 1))

    return (
        codes_main, captions, lyrics, bpm, key_scale, time_signature,
        vocal_language, audio_duration, batch_size_input, inference_steps,
        lm_temperature, lm_cfg_scale, lm_top_k, lm_top_p, think_checkbox,
        use_cot_caption, use_cot_language, allow_lm_batch,
        track_name, complete_track_classes,
        enable_normalization, normalization_db,
        latent_shift, latent_rescale,
    )
