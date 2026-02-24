"""Core audio generation with progressive UI yields.

Contains the main ``generate_with_progress`` generator that drives the
Gradio generate button: validates GPU limits, calls the inference
pipeline, saves audio files, and optionally runs auto-scoring and
auto-LRC in a single streaming pass.
"""
import os
import json
import time as time_module

import gradio as gr
from loguru import logger

from acestep.inference import generate_music, GenerationParams, GenerationConfig
from acestep.audio_utils import save_audio
from acestep.gpu_config import (
    get_global_gpu_config,
    check_duration_limit,
    check_batch_size_limit,
)
from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.events.generation_handlers import parse_and_validate_timesteps
from acestep.ui.gradio.events.results.generation_info import (
    DEFAULT_RESULTS_DIR,
    _build_generation_info,
)
from acestep.ui.gradio.events.results.scoring import calculate_score_handler
from acestep.ui.gradio.events.results.lrc_utils import lrc_to_vtt_file


def generate_with_progress(
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
    enable_normalization,
    normalization_db,
    latent_shift,
    latent_rescale,
    progress=gr.Progress(track_tqdm=True),
):
    """Generate audio with progress tracking.

    This is a Gradio generator that yields partial UI updates as each
    sample is processed, enabling progressive display of results.

    Yields:
        Tuple of Gradio component updates for the 52-output generate event.
    """
    # GPU memory validation
    gpu_config = get_global_gpu_config()
    lm_initialized = llm_handler.llm_initialized if llm_handler else False

    if audio_duration is not None and audio_duration > 0:
        is_valid, warning_msg = check_duration_limit(audio_duration, gpu_config, lm_initialized)
        if not is_valid:
            gr.Warning(warning_msg)
            max_dur = gpu_config.max_duration_with_lm if lm_initialized else gpu_config.max_duration_without_lm
            audio_duration = min(audio_duration, max_dur)
            logger.warning(f"Duration clamped to {audio_duration}s due to GPU memory limits")

    if batch_size_input is not None and batch_size_input > 0:
        is_valid, warning_msg = check_batch_size_limit(int(batch_size_input), gpu_config, lm_initialized)
        if not is_valid:
            gr.Warning(warning_msg)
            max_bs = gpu_config.max_batch_size_with_lm if lm_initialized else gpu_config.max_batch_size_without_lm
            batch_size_input = min(int(batch_size_input), max_bs)
            logger.warning(f"Batch size clamped to {batch_size_input} due to GPU memory limits")

    # Skip Phase 1 metas COT if sample is already formatted
    actual_use_cot_metas = use_cot_metas
    if is_format_caption and use_cot_metas:
        actual_use_cot_metas = False
        logger.info("[generate_with_progress] Skipping Phase 1 metas COT: is_format_caption=True")
        gr.Info(t("messages.skipping_metas_cot"))

    parsed_timesteps, _has_ts_warn, _ = parse_and_validate_timesteps(custom_timesteps, inference_steps)
    actual_inference_steps = len(parsed_timesteps) - 1 if parsed_timesteps is not None else inference_steps

    if task_type == "text2music":
        src_audio = None

    # Defensive guard: cover/repaint/extract/lego tasks should never use
    # stale audio codes from the text2music_audio_code_string textbox.
    # Only text2music (Custom mode) with thinking disabled should pass codes.
    if task_type != "text2music":
        text2music_audio_code_string = ""

    gen_params = GenerationParams(
        task_type=task_type,
        instruction=instruction_display_gen,
        reference_audio=reference_audio,
        src_audio=src_audio,
        audio_codes=text2music_audio_code_string if not think_checkbox else "",
        caption=captions or "",
        lyrics=lyrics or "",
        instrumental=False,
        vocal_language=vocal_language,
        bpm=bpm,
        keyscale=key_scale,
        timesignature=time_signature,
        duration=audio_duration,
        inference_steps=actual_inference_steps,
        guidance_scale=guidance_scale,
        use_adg=use_adg,
        cfg_interval_start=cfg_interval_start,
        cfg_interval_end=cfg_interval_end,
        shift=shift,
        infer_method=infer_method,
        timesteps=parsed_timesteps,
        repainting_start=repainting_start,
        repainting_end=repainting_end,
        audio_cover_strength=audio_cover_strength,
        cover_noise_strength=cover_noise_strength,
        thinking=think_checkbox,
        lm_temperature=lm_temperature,
        lm_cfg_scale=lm_cfg_scale,
        lm_top_k=lm_top_k,
        lm_top_p=lm_top_p,
        lm_negative_prompt=lm_negative_prompt,
        use_cot_metas=actual_use_cot_metas,
        use_cot_caption=use_cot_caption,
        use_cot_language=use_cot_language,
        use_constrained_decoding=True,
        enable_normalization=enable_normalization,
        normalization_db=normalization_db,
        latent_shift=latent_shift,
        latent_rescale=latent_rescale,
    )

    if isinstance(seed, str) and seed.strip():
        seed_list = [int(s.strip()) for s in seed.split(",")] if "," in seed else [int(seed.strip())]
    else:
        seed_list = None

    gen_config = GenerationConfig(
        batch_size=batch_size_input,
        allow_lm_batch=allow_lm_batch,
        use_random_seed=random_seed_checkbox,
        seeds=seed_list,
        lm_batch_chunk_size=lm_batch_chunk_size,
        constrained_decoding_debug=constrained_decoding_debug,
        audio_format=audio_format,
    )

    result = generate_music(dit_handler, llm_handler, params=gen_params, config=gen_config, progress=progress)

    audio_outputs = [None] * 8
    all_audio_paths: list = []
    final_codes_list = [""] * 8
    final_scores_list = [""] * 8
    final_lrcs_list = [""] * 8
    final_subtitles_list = [None] * 8

    seed_value_for_ui = result.extra_outputs.get("seed_value", "")
    lm_generated_metadata = result.extra_outputs.get("lm_metadata", {})
    time_costs = result.extra_outputs.get("time_costs", {}).copy()

    audio_conversion_start_time = time_module.time()
    total_auto_score_time = 0.0
    total_auto_lrc_time = 0.0

    updated_audio_codes = text2music_audio_code_string if not think_checkbox else ""  # noqa: F841

    generation_info = _build_generation_info(
        lm_metadata=lm_generated_metadata,
        time_costs=time_costs,
        seed_value=seed_value_for_ui,
        inference_steps=inference_steps,
        num_audios=len(result.audios) if result.success else 0,
        audio_format=audio_format,
    )

    if not result.success:
        yield (
            (None,) * 8
            + (None, generation_info, result.status_message, gr.skip())
            + (gr.skip(),) * 8  # scores
            + (gr.skip(),) * 8  # codes_display
            + (gr.skip(),) * 8  # details_accordion
            + (gr.skip(),) * 8  # lrc_display
            + (None, is_format_caption, None, None)
        )
        return

    audios = result.audios
    progress(0.99, "Converting audio to mp3...")

    # Clear all scores/codes/lrc displays
    clear_scores = [gr.update(value="", visible=True) for _ in range(8)]
    clear_codes = [gr.update(value="", visible=True) for _ in range(8)]
    clear_lrcs = [gr.update(value="", visible=True) for _ in range(8)]
    clear_accordions = [gr.skip() for _ in range(8)]
    dump_audio = [gr.update(value=None, subtitles=None, playback_position=0) for _ in range(8)]

    yield (
        *dump_audio,
        None, generation_info, "Clearing previous results...", gr.skip(),
        *clear_scores, *clear_codes, *clear_accordions, *clear_lrcs,
        lm_generated_metadata, is_format_caption, None, None,
    )
    time_module.sleep(0.1)

    for i in range(8):
        if i >= len(audios):
            continue

        key = audios[i]["key"]
        audio_tensor = audios[i]["tensor"]
        sample_rate = audios[i]["sample_rate"]
        audio_params = audios[i]["params"]

        timestamp = int(time_module.time())
        temp_dir = os.path.join(DEFAULT_RESULTS_DIR, f"batch_{timestamp}")
        temp_dir = os.path.abspath(temp_dir).replace("\\", "/")
        os.makedirs(temp_dir, exist_ok=True)
        json_path = os.path.join(temp_dir, f"{key}.json").replace("\\", "/")

        ext = "wav" if audio_format == "wav32" else audio_format
        audio_path = os.path.join(temp_dir, f"{key}.{ext}").replace("\\", "/")

        saved_path = save_audio(
            audio_data=audio_tensor, output_path=audio_path,
            sample_rate=sample_rate, format=audio_format, channels_first=True,
        )
        if saved_path:
            audio_path = saved_path.replace("\\", "/")

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(audio_params, f, indent=2, ensure_ascii=False)

        audio_outputs[i] = audio_path
        all_audio_paths.append(audio_path)
        all_audio_paths.append(json_path)

        code_str = audio_params.get("audio_codes", "")
        final_codes_list[i] = code_str

        scores_ui_updates = [gr.skip() for _ in range(8)]
        score_str = "Done!"

        if auto_score:
            auto_score_start = time_module.time()
            sample_tensor_data = _extract_sample_tensor(result.extra_outputs, i)
            score_str = calculate_score_handler(
                llm_handler, code_str, captions, lyrics, lm_generated_metadata,
                bpm, key_scale, time_signature, audio_duration, vocal_language,
                score_scale, dit_handler, sample_tensor_data, inference_steps,
            )
            total_auto_score_time += time_module.time() - auto_score_start

        scores_ui_updates[i] = score_str
        final_scores_list[i] = score_str

        if auto_lrc:
            auto_lrc_start = time_module.time()
            _run_auto_lrc(
                dit_handler, result.extra_outputs, i,
                audio_duration, vocal_language, inference_steps,
                final_lrcs_list, final_subtitles_list,
            )
            total_auto_lrc_time += time_module.time() - auto_lrc_start

        # STEP 1: yield audio + clear LRC
        cur_audio = [gr.skip()] * 8
        cur_audio[i] = audio_path
        cur_codes = [gr.skip()] * 8
        cur_codes[i] = gr.update(value=code_str, visible=True)
        cur_accordions = [gr.skip()] * 8
        lrc_clear = [gr.skip()] * 8
        lrc_clear[i] = gr.update(value="", visible=True)

        yield (
            *cur_audio,
            all_audio_paths, generation_info, f"Encoding & Ready: {i + 1}/{len(audios)}", seed_value_for_ui,
            *scores_ui_updates, *cur_codes, *cur_accordions, *lrc_clear,
            lm_generated_metadata, is_format_caption, None, None,
        )
        time_module.sleep(0.05)

        # STEP 2: set actual LRC (triggers .change() for subtitles)
        if final_lrcs_list[i]:
            skip8 = [gr.skip()] * 8
            lrc_set = [gr.skip()] * 8
            lrc_set[i] = gr.update(value=final_lrcs_list[i], visible=True)
            yield (
                *skip8,
                gr.skip(), gr.skip(), gr.skip(), gr.skip(),
                *skip8, *skip8, *skip8, *lrc_set,
                gr.skip(), gr.skip(), None, None,
            )

        time_module.sleep(0.05)

    # Final timing
    audio_conversion_time = time_module.time() - audio_conversion_start_time
    if audio_conversion_time > 0:
        time_costs['audio_conversion_time'] = audio_conversion_time
    if total_auto_score_time > 0:
        time_costs['auto_score_time'] = total_auto_score_time
    if total_auto_lrc_time > 0:
        time_costs['auto_lrc_time'] = total_auto_lrc_time
    if 'pipeline_total_time' in time_costs:
        time_costs['pipeline_total_time'] += audio_conversion_time + total_auto_score_time + total_auto_lrc_time

    generation_info = _build_generation_info(
        lm_metadata=lm_generated_metadata,
        time_costs=time_costs,
        seed_value=seed_value_for_ui,
        inference_steps=inference_steps,
        num_audios=len(result.audios),
        audio_format=audio_format,
    )

    audio_playback_updates = []
    for idx in range(8):
        path = audio_outputs[idx]
        if path:
            audio_playback_updates.append(
                gr.update(value=path, label=f"Sample {idx + 1} (Ready)", interactive=False)
            )
            logger.info(f"[generate_with_progress] Audio {idx + 1} path: {path}")
        else:
            audio_playback_updates.append(gr.update(value=None, label="None", interactive=False))

    final_codes_display = [gr.skip()] * 8
    final_accordions = [gr.skip()] * 8

    yield (
        *audio_playback_updates,
        all_audio_paths, generation_info, "Generation Complete", seed_value_for_ui,
        *final_scores_list, *final_codes_display, *final_accordions, *final_lrcs_list,
        lm_generated_metadata, is_format_caption,
        {**result.extra_outputs, "lrcs": final_lrcs_list, "subtitles": final_subtitles_list},
        final_codes_list,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_sample_tensor(extra_outputs, sample_idx):
    """Slice per-sample tensor data from *extra_outputs* for scoring.

    Returns ``None`` when data is missing or incomplete.
    """
    try:
        full_pred = extra_outputs.get("pred_latents")
        if full_pred is None or sample_idx >= full_pred.shape[0]:
            return None
        data = {
            "pred_latent": full_pred[sample_idx:sample_idx + 1],
            "encoder_hidden_states": extra_outputs.get("encoder_hidden_states")[sample_idx:sample_idx + 1]
                if extra_outputs.get("encoder_hidden_states") is not None else None,
            "encoder_attention_mask": extra_outputs.get("encoder_attention_mask")[sample_idx:sample_idx + 1]
                if extra_outputs.get("encoder_attention_mask") is not None else None,
            "context_latents": extra_outputs.get("context_latents")[sample_idx:sample_idx + 1]
                if extra_outputs.get("context_latents") is not None else None,
            "lyric_token_ids": extra_outputs.get("lyric_token_idss")[sample_idx:sample_idx + 1]
                if extra_outputs.get("lyric_token_idss") is not None else None,
        }
        if any(v is None for v in data.values()):
            return None
        return data
    except Exception as e:
        print(f"[Auto Score] Failed to prepare tensor data for sample {sample_idx}: {e}")
        return None


def _run_auto_lrc(dit_handler, extra_outputs, sample_idx,
                  audio_duration, vocal_language, inference_steps,
                  final_lrcs_list, final_subtitles_list):
    """Run automatic LRC generation for a single sample in-place.

    Updates *final_lrcs_list* and *final_subtitles_list* at *sample_idx*.
    """
    logger.info(f"[auto_lrc] Starting LRC generation for sample {sample_idx + 1}")
    try:
        pred_latents = extra_outputs.get("pred_latents")
        enc_hs = extra_outputs.get("encoder_hidden_states")
        enc_am = extra_outputs.get("encoder_attention_mask")
        ctx_lat = extra_outputs.get("context_latents")
        lyric_ids = extra_outputs.get("lyric_token_idss")

        if not all(x is not None for x in [pred_latents, enc_hs, enc_am, ctx_lat, lyric_ids]):
            logger.warning(f"[auto_lrc] Missing required extra_outputs for sample {sample_idx + 1}")
            return

        actual_duration = audio_duration
        if actual_duration is None or actual_duration <= 0:
            actual_duration = pred_latents.shape[1] / 25.0

        lrc_result = dit_handler.get_lyric_timestamp(
            pred_latent=pred_latents[sample_idx:sample_idx + 1],
            encoder_hidden_states=enc_hs[sample_idx:sample_idx + 1],
            encoder_attention_mask=enc_am[sample_idx:sample_idx + 1],
            context_latents=ctx_lat[sample_idx:sample_idx + 1],
            lyric_token_ids=lyric_ids[sample_idx:sample_idx + 1],
            total_duration_seconds=float(actual_duration),
            vocal_language=vocal_language or "en",
            inference_steps=int(inference_steps),
            seed=42,
        )

        if lrc_result.get("success"):
            lrc_text = lrc_result.get("lrc_text", "")
            final_lrcs_list[sample_idx] = lrc_text
            logger.info(f"[auto_lrc] LRC text length for sample {sample_idx + 1}: {len(lrc_text)}")
            vtt_path = lrc_to_vtt_file(lrc_text, total_duration=float(actual_duration))
            final_subtitles_list[sample_idx] = vtt_path
    except Exception as e:
        logger.warning(f"[auto_lrc] Failed to generate LRC for sample {sample_idx + 1}: {e}")
