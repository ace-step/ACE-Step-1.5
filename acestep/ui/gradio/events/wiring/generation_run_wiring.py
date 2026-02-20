"""Generation run event wiring helpers.

This module isolates the primary generation-button click chain that clears
outputs, runs batched generation, and schedules background pre-generation.
"""

from .. import results_handlers as res_h
from .context import GenerationWiringContext


def register_generation_run_handlers(context: GenerationWiringContext) -> None:
    """Register batched generation-run event wiring for audio inference.

    Args:
        context (GenerationWiringContext): Shared wiring context used by
        `register_generation_run_handlers`; reads `generation_section`,
        `results_section`, `dit_handler`, and `llm_handler` to bind the
        generate-button click chain.

    Returns:
        None: Registers click/then handlers in-place on generation components.
    """

    generation_section = context.generation_section
    results_section = context.results_section
    dit_handler = context.dit_handler
    llm_handler = context.llm_handler

    def generation_wrapper(*args):
        """Proxy passthrough to `res_h.generate_with_batch_management`.

        Args:
            *args (Any): Positional passthrough inputs forwarded unchanged to
                `res_h.generate_with_batch_management(dit_handler, llm_handler, *args)`.

        Yields:
            Any: Streamed generation updates yielded by
            `res_h.generate_with_batch_management`.

        Raises:
            Exception: Propagates exceptions raised by
            `res_h.generate_with_batch_management`.
        """

        yield from res_h.generate_with_batch_management(dit_handler, llm_handler, *args)

    generation_section["generate_btn"].click(
        fn=res_h.clear_audio_outputs_for_new_generation,
        outputs=[
            results_section["generated_audio_1"],
            results_section["generated_audio_2"],
            results_section["generated_audio_3"],
            results_section["generated_audio_4"],
            results_section["generated_audio_5"],
            results_section["generated_audio_6"],
            results_section["generated_audio_7"],
            results_section["generated_audio_8"],
            results_section["generated_audio_batch"],
        ],
    ).then(
        fn=generation_wrapper,
        inputs=[
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
            results_section["is_format_caption_state"],
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
            generation_section["autogen_checkbox"],
            results_section["current_batch_index"],
            results_section["total_batches"],
            results_section["batch_queue"],
            results_section["generation_params_state"],
        ],
        outputs=[
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
            results_section["status_output"],
            generation_section["seed"],
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
            results_section["details_accordion_1"],
            results_section["details_accordion_2"],
            results_section["details_accordion_3"],
            results_section["details_accordion_4"],
            results_section["details_accordion_5"],
            results_section["details_accordion_6"],
            results_section["details_accordion_7"],
            results_section["details_accordion_8"],
            results_section["lrc_display_1"],
            results_section["lrc_display_2"],
            results_section["lrc_display_3"],
            results_section["lrc_display_4"],
            results_section["lrc_display_5"],
            results_section["lrc_display_6"],
            results_section["lrc_display_7"],
            results_section["lrc_display_8"],
            results_section["lm_metadata_state"],
            results_section["is_format_caption_state"],
            results_section["current_batch_index"],
            results_section["total_batches"],
            results_section["batch_queue"],
            results_section["generation_params_state"],
            results_section["batch_indicator"],
            results_section["prev_batch_btn"],
            results_section["next_batch_btn"],
            results_section["next_batch_status"],
            results_section["restore_params_btn"],
        ],
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
