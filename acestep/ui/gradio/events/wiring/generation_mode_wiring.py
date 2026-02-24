"""Generation mode and simple-mode event wiring helpers.

This module contains mode-switch and simple-mode related handlers to keep
``events.__init__`` as a thin facade.
"""

from typing import Any, Sequence

from .. import generation_handlers as gen_h
from .context import GenerationWiringContext


def register_generation_mode_handlers(
    context: GenerationWiringContext,
    mode_ui_outputs: Sequence[Any],
    auto_checkbox_inputs: Sequence[Any],
    auto_checkbox_outputs: Sequence[Any],
) -> None:
    """Register generation mode and simple-mode handlers."""

    generation_section = context.generation_section
    results_section = context.results_section
    llm_handler = context.llm_handler

    # ========== Generation Mode Change ==========
    generation_section["generation_mode"].change(
        fn=lambda mode, prev: gen_h.handle_generation_mode_change(mode, prev, llm_handler),
        inputs=[
            generation_section["generation_mode"],
            generation_section["previous_generation_mode"],
        ],
        outputs=mode_ui_outputs,
    )

    # ========== Extract Mode: Auto-fill caption from track_name ==========
    generation_section["track_name"].change(
        fn=gen_h.handle_extract_track_name_change,
        inputs=[
            generation_section["track_name"],
            generation_section["generation_mode"],
        ],
        outputs=[generation_section["captions"]],
    )

    # Validate source audio eagerly so users get immediate feedback on invalid files.
    generation_section["src_audio"].change(
        fn=lambda src_audio: gen_h.validate_uploaded_audio_file(src_audio, "source"),
        inputs=[generation_section["src_audio"]],
        outputs=[generation_section["src_audio"]],
    )

    # ========== Extract/Lego Mode: Auto-fill audio_duration from src_audio ==========
    generation_section["src_audio"].change(
        fn=gen_h.handle_extract_src_audio_change,
        inputs=[
            generation_section["src_audio"],
            generation_section["generation_mode"],
        ],
        outputs=[generation_section["audio_duration"]],
    )

    # ========== Simple Mode Instrumental Checkbox ==========
    generation_section["simple_instrumental_checkbox"].change(
        fn=gen_h.handle_simple_instrumental_change,
        inputs=[generation_section["simple_instrumental_checkbox"]],
        outputs=[generation_section["simple_vocal_language"]],
    )

    # ========== Random Description Button ==========
    generation_section["random_desc_btn"].click(
        fn=gen_h.load_random_simple_description,
        inputs=[],
        outputs=[
            generation_section["simple_query_input"],
            generation_section["simple_instrumental_checkbox"],
            generation_section["simple_vocal_language"],
        ],
    )

    # ========== Create Sample Button (Simple Mode) ==========
    generation_section["create_sample_btn"].click(
        fn=lambda query, instrumental, vocal_lang, temp, top_k, top_p, debug: gen_h.handle_create_sample(
            llm_handler, query, instrumental, vocal_lang, temp, top_k, top_p, debug
        ),
        inputs=[
            generation_section["simple_query_input"],
            generation_section["simple_instrumental_checkbox"],
            generation_section["simple_vocal_language"],
            generation_section["lm_temperature"],
            generation_section["lm_top_k"],
            generation_section["lm_top_p"],
            generation_section["constrained_decoding_debug"],
        ],
        outputs=[
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["bpm"],
            generation_section["audio_duration"],
            generation_section["key_scale"],
            generation_section["vocal_language"],
            generation_section["simple_vocal_language"],
            generation_section["time_signature"],
            generation_section["instrumental_checkbox"],
            generation_section["generate_btn"],
            generation_section["simple_sample_created"],
            generation_section["think_checkbox"],
            results_section["is_format_caption_state"],
            results_section["status_output"],
            generation_section["generation_mode"],
        ],
    ).then(
        fn=gen_h.uncheck_auto_for_populated_fields,
        inputs=list(auto_checkbox_inputs),
        outputs=list(auto_checkbox_outputs),
    )
