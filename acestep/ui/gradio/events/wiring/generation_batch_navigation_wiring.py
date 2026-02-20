"""Generation batch navigation event wiring helpers.

This module contains previous/next batch navigation wiring for generated
results and background next-batch preparation.
"""

from typing import Any

from .. import results_handlers as res_h
from .context import GenerationWiringContext


def _build_navigation_outputs(results_section: dict[str, Any], include_next_status: bool) -> list[Any]:
    """Return ordered outputs for prev/next batch navigation handlers."""

    outputs = [
        results_section["generated_audio_1"],
        results_section["generated_audio_2"],
        results_section["generated_audio_3"],
        results_section["generated_audio_4"],
        results_section["generated_audio_5"],
        results_section["generated_audio_6"],
        results_section["generated_audio_7"],
        results_section["generated_audio_8"],
        results_section["generated_audio_batch"],
        results_section["generation_info"],
        results_section["current_batch_index"],
        results_section["batch_indicator"],
        results_section["prev_batch_btn"],
        results_section["next_batch_btn"],
        results_section["status_output"],
    ]
    if include_next_status:
        outputs.append(results_section["next_batch_status"])
    outputs.extend(
        [
            results_section["score_display_1"],
            results_section["score_display_2"],
            results_section["score_display_3"],
            results_section["score_display_4"],
            results_section["score_display_5"],
            results_section["score_display_6"],
            results_section["score_display_7"],
            results_section["score_display_8"],
            results_section["codes_display_1"],
            results_section["codes_display_2"],
            results_section["codes_display_3"],
            results_section["codes_display_4"],
            results_section["codes_display_5"],
            results_section["codes_display_6"],
            results_section["codes_display_7"],
            results_section["codes_display_8"],
            results_section["lrc_display_1"],
            results_section["lrc_display_2"],
            results_section["lrc_display_3"],
            results_section["lrc_display_4"],
            results_section["lrc_display_5"],
            results_section["lrc_display_6"],
            results_section["lrc_display_7"],
            results_section["lrc_display_8"],
            results_section["details_accordion_1"],
            results_section["details_accordion_2"],
            results_section["details_accordion_3"],
            results_section["details_accordion_4"],
            results_section["details_accordion_5"],
            results_section["details_accordion_6"],
            results_section["details_accordion_7"],
            results_section["details_accordion_8"],
            results_section["restore_params_btn"],
        ]
    )
    return outputs


def _build_capture_current_params_inputs(generation_section: dict[str, Any]) -> list[Any]:
    """Return ordered generation controls captured before navigating batches."""

    return [
        generation_section["captions"],
        generation_section["lyrics"],
        generation_section["bpm"],
        generation_section["key_scale"],
        generation_section["time_signature"],
        generation_section["vocal_language"],
        generation_section["inference_steps"],
        generation_section["guidance_scale"],
        generation_section["random_seed_checkbox"],
        generation_section["seed"],
        generation_section["reference_audio"],
        generation_section["audio_duration"],
        generation_section["batch_size_input"],
        generation_section["src_audio"],
        generation_section["text2music_audio_code_string"],
        generation_section["repainting_start"],
        generation_section["repainting_end"],
        generation_section["instruction_display_gen"],
        generation_section["audio_cover_strength"],
        generation_section["cover_noise_strength"],
        generation_section["task_type"],
        generation_section["use_adg"],
        generation_section["cfg_interval_start"],
        generation_section["cfg_interval_end"],
        generation_section["shift"],
        generation_section["infer_method"],
        generation_section["custom_timesteps"],
        generation_section["audio_format"],
        generation_section["lm_temperature"],
        generation_section["think_checkbox"],
        generation_section["lm_cfg_scale"],
        generation_section["lm_top_k"],
        generation_section["lm_top_p"],
        generation_section["lm_negative_prompt"],
        generation_section["use_cot_metas"],
        generation_section["use_cot_caption"],
        generation_section["use_cot_language"],
        generation_section["constrained_decoding_debug"],
        generation_section["allow_lm_batch"],
        generation_section["auto_score"],
        generation_section["auto_lrc"],
        generation_section["score_scale"],
        generation_section["lm_batch_chunk_size"],
        generation_section["track_name"],
        generation_section["complete_track_classes"],
        generation_section["enable_normalization"],
        generation_section["normalization_db"],
        generation_section["latent_shift"],
        generation_section["latent_rescale"],
    ]


def register_generation_batch_navigation_handlers(context: GenerationWiringContext) -> None:
    """Register previous/next batch navigation handlers and pre-generation chain."""

    generation_section = context.generation_section
    results_section = context.results_section
    dit_handler = context.dit_handler
    llm_handler = context.llm_handler

    prev_navigation_outputs = _build_navigation_outputs(results_section, include_next_status=False)
    next_navigation_outputs = _build_navigation_outputs(results_section, include_next_status=True)

    results_section["prev_batch_btn"].click(
        fn=res_h.navigate_to_previous_batch,
        inputs=[
            results_section["current_batch_index"],
            results_section["batch_queue"],
        ],
        outputs=prev_navigation_outputs,
    )

    results_section["next_batch_btn"].click(
        fn=res_h.capture_current_params,
        inputs=_build_capture_current_params_inputs(generation_section),
        outputs=[results_section["generation_params_state"]],
    ).then(
        fn=res_h.navigate_to_next_batch,
        inputs=[
            generation_section["autogen_checkbox"],
            results_section["current_batch_index"],
            results_section["total_batches"],
            results_section["batch_queue"],
        ],
        outputs=next_navigation_outputs,
    ).then(
        fn=lambda *args: res_h.generate_next_batch_background(dit_handler, llm_handler, *args),
        inputs=[
            generation_section["autogen_checkbox"],
            results_section["generation_params_state"],
            results_section["current_batch_index"],
            results_section["total_batches"],
            results_section["batch_queue"],
            results_section["is_format_caption_state"],
        ],
        outputs=[
            results_section["batch_queue"],
            results_section["total_batches"],
            results_section["next_batch_status"],
            results_section["next_batch_btn"],
        ],
    )
