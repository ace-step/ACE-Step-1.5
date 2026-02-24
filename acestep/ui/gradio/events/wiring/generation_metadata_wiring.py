"""Generation metadata/text event wiring helpers.

This module contains wiring for source analysis, transcribe/sample operations,
and caption/lyrics formatting flows.
"""

from typing import Any, Sequence

from .. import generation_handlers as gen_h
from .context import GenerationWiringContext
from .generation_text_format_wiring import register_generation_text_format_handlers


def register_generation_metadata_handlers(
    context: GenerationWiringContext,
    auto_checkbox_inputs: Sequence[Any],
    auto_checkbox_outputs: Sequence[Any],
) -> None:
    """Register metadata and text-format generation handlers."""

    generation_section = context.generation_section
    results_section = context.results_section
    dit_handler = context.dit_handler
    llm_handler = context.llm_handler

    # ========== Audio Conversion (LM Codes Hints accordion in Custom mode) ==========
    generation_section["convert_src_to_codes_btn"].click(
        fn=lambda src: gen_h.convert_src_audio_to_codes_wrapper(dit_handler, src),
        inputs=[generation_section["lm_codes_audio_upload"]],
        outputs=[generation_section["text2music_audio_code_string"]],
    )

    # ========== Analyze Source Audio (Remix/Repaint: convert to codes + transcribe) ==========
    generation_section["analyze_btn"].click(
        fn=lambda src, debug: gen_h.analyze_src_audio(dit_handler, llm_handler, src, debug),
        inputs=[
            generation_section["src_audio"],
            generation_section["constrained_decoding_debug"],
        ],
        outputs=[
            generation_section["text2music_audio_code_string"],
            results_section["status_output"],
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["bpm"],
            generation_section["audio_duration"],
            generation_section["key_scale"],
            generation_section["vocal_language"],
            generation_section["time_signature"],
            results_section["is_format_caption_state"],
        ],
    ).then(
        fn=gen_h.uncheck_auto_for_populated_fields,
        inputs=list(auto_checkbox_inputs),
        outputs=list(auto_checkbox_outputs),
    )

    # ========== Instruction UI Updates ==========
    for trigger in [
        generation_section["task_type"],
        generation_section["track_name"],
        generation_section["complete_track_classes"],
        generation_section["reference_audio"],
    ]:
        trigger.change(
            fn=lambda *args: gen_h.update_instruction_ui(dit_handler, *args),
            inputs=[
                generation_section["task_type"],
                generation_section["track_name"],
                generation_section["complete_track_classes"],
                generation_section["init_llm_checkbox"],
                generation_section["reference_audio"],
            ],
            outputs=[generation_section["instruction_display_gen"]],
        )

    # Validate reference audio eagerly so users get immediate feedback on invalid files.
    generation_section["reference_audio"].change(
        fn=lambda reference_audio: gen_h.validate_uploaded_audio_file(reference_audio, "reference"),
        inputs=[generation_section["reference_audio"]],
        outputs=[generation_section["reference_audio"]],
    )

    # ========== Sample/Transcribe Handlers ==========
    generation_section["sample_btn"].click(
        fn=lambda task: gen_h.load_random_example(task, llm_handler) + (True,),
        inputs=[generation_section["task_type"]],
        outputs=[
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["think_checkbox"],
            generation_section["bpm"],
            generation_section["audio_duration"],
            generation_section["key_scale"],
            generation_section["vocal_language"],
            generation_section["time_signature"],
            results_section["is_format_caption_state"],
        ],
    ).then(
        fn=gen_h.uncheck_auto_for_populated_fields,
        inputs=list(auto_checkbox_inputs),
        outputs=list(auto_checkbox_outputs),
    )

    generation_section["text2music_audio_code_string"].change(
        fn=gen_h.update_transcribe_button_text,
        inputs=[generation_section["text2music_audio_code_string"]],
        outputs=[generation_section["transcribe_btn"]],
    )

    generation_section["transcribe_btn"].click(
        fn=lambda codes, debug: gen_h.transcribe_audio_codes(llm_handler, codes, debug),
        inputs=[
            generation_section["text2music_audio_code_string"],
            generation_section["constrained_decoding_debug"],
        ],
        outputs=[
            results_section["status_output"],
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["bpm"],
            generation_section["audio_duration"],
            generation_section["key_scale"],
            generation_section["vocal_language"],
            generation_section["time_signature"],
            results_section["is_format_caption_state"],
        ],
    ).then(
        fn=gen_h.uncheck_auto_for_populated_fields,
        inputs=list(auto_checkbox_inputs),
        outputs=list(auto_checkbox_outputs),
    )

    # ========== Reset Format Caption Flag ==========
    for trigger in [
        generation_section["captions"],
        generation_section["lyrics"],
        generation_section["bpm"],
        generation_section["key_scale"],
        generation_section["time_signature"],
        generation_section["vocal_language"],
        generation_section["audio_duration"],
    ]:
        trigger.change(
            fn=gen_h.reset_format_caption_flag,
            inputs=[],
            outputs=[results_section["is_format_caption_state"]],
        )

    # ========== Instrumental Checkbox ==========
    generation_section["instrumental_checkbox"].change(
        fn=gen_h.handle_instrumental_checkbox,
        inputs=[
            generation_section["instrumental_checkbox"],
            generation_section["lyrics"],
            generation_section["lyrics_before_instrumental"],
        ],
        outputs=[
            generation_section["lyrics"],
            generation_section["lyrics_before_instrumental"],
        ],
    )

    register_generation_text_format_handlers(
        context,
        auto_checkbox_inputs=auto_checkbox_inputs,
        auto_checkbox_outputs=auto_checkbox_outputs,
    )
