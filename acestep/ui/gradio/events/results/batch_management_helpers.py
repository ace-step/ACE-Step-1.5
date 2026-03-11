"""Helper utilities for batch-management generation flows.

This module contains pure helper functions used by the batch wrapper and
background generation paths.
"""

from loguru import logger


def _extract_ui_core_outputs(result_tuple):
    """Return the fixed 46 core UI outputs from a generation result tuple.

    The generate-button wiring expects 46 generation outputs from the wrapper,
    followed by 9 batch-state outputs. Any trailing fields from
    ``generate_with_progress`` are intentionally ignored here.
    """
    return tuple(result_tuple[:46]) if len(result_tuple) >= 46 else tuple(result_tuple)


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
    """Build the parameter snapshot dict stored in batch history."""
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
    """Log background-generation parameter values for diagnostics."""
    logger.info(f"========== BACKGROUND GENERATION BATCH {next_batch_idx + 1} ==========")
    logger.info(f"  - captions: {params.get('captions', 'N/A')}")
    lyr = params.get("lyrics")
    logger.info(f"  - lyrics: {lyr[:50]}..." if lyr else "  - lyrics: N/A")
    logger.info(f"  - bpm: {params.get('bpm')}")
    logger.info(f"  - batch_size_input: {params.get('batch_size_input')}")
    logger.info(f"  - allow_lm_batch: {params.get('allow_lm_batch')}")
    logger.info(f"  - think_checkbox: {params.get('think_checkbox')}")
    logger.info(f"  - lm_temperature: {params.get('lm_temperature')}")
    logger.info(f"  - track_name: {params.get('track_name')}")
    codes_val = params.get("text2music_audio_code_string")
    logger.info(f"  - text2music_audio_code_string: {'<CLEARED>' if codes_val == '' else 'HAS_VALUE'}")
    logger.info("=========================================================")


def _apply_param_defaults(params):
    """Fill missing generation keys in ``params`` with safe defaults."""
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
    for key, value in defaults.items():
        params.setdefault(key, value)


def _extract_scores(final_result):
    """Extract score strings from generation tuple indices 12-19."""
    scores = []
    for idx in range(12, 20):
        if idx < len(final_result):
            val = final_result[idx]
            if hasattr(val, "value"):
                scores.append(val.value if val.value else "")
            elif isinstance(val, str):
                scores.append(val)
            else:
                scores.append("")
        else:
            scores.append("")
    return scores
