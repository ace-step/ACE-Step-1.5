"""Generation text-format event wiring helpers.

This module isolates caption/lyrics formatting event registration.
"""

from typing import Any, Sequence

from .. import generation_handlers as gen_h
from .context import GenerationWiringContext


def register_generation_text_format_handlers(
    context: GenerationWiringContext,
    auto_checkbox_inputs: Sequence[Any],
    auto_checkbox_outputs: Sequence[Any],
) -> None:
    """Register caption/lyrics format handlers and their auto-checkbox sync."""

    generation_section = context.generation_section
    results_section = context.results_section
    llm_handler = context.llm_handler

    # ========== Format Caption Button ==========
    generation_section["format_caption_btn"].click(
        fn=lambda caption, lyrics, bpm, duration, key_scale, time_sig, temp, top_k, top_p, debug: gen_h.handle_format_caption(
            llm_handler, caption, lyrics, bpm, duration, key_scale, time_sig, temp, top_k, top_p, debug
        ),
        inputs=[
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["bpm"],
            generation_section["audio_duration"],
            generation_section["key_scale"],
            generation_section["time_signature"],
            generation_section["lm_temperature"],
            generation_section["lm_top_k"],
            generation_section["lm_top_p"],
            generation_section["constrained_decoding_debug"],
        ],
        outputs=[
            generation_section["captions"],
            generation_section["bpm"],
            generation_section["audio_duration"],
            generation_section["key_scale"],
            generation_section["vocal_language"],
            generation_section["time_signature"],
            results_section["is_format_caption_state"],
            results_section["status_output"],
        ],
    ).then(
        fn=gen_h.uncheck_auto_for_populated_fields,
        inputs=list(auto_checkbox_inputs),
        outputs=list(auto_checkbox_outputs),
    )

    # ========== Edit: Copy Current Caption/Lyrics into Source Fields ==========
    # Quick way to bootstrap V_src with the user-level prompt before they
    # edit the top-level fields to define V_tar.
    generation_section["flow_edit_copy_from_current_btn"].click(
        fn=lambda caption, lyrics: (caption or "", lyrics or ""),
        inputs=[
            generation_section["captions"],
            generation_section["lyrics"],
        ],
        outputs=[
            generation_section["flow_edit_source_caption"],
            generation_section["flow_edit_source_lyrics"],
        ],
    )

    # ========== Retake × Think interaction warning ==========
    # Retake's variation is only meaningful if every other condition (LM
    # codes included) matches the baseline.  When Think is on the LM
    # regenerates codes per call, so Retake's noise blend layers on top
    # of an already-different starting point.  Surface a one-line warning
    # in the Retake panel whenever both checkboxes are simultaneously on.
    def _retake_think_warn(retake_on: bool, think_on: bool):
        import gradio as _gr  # local import — module top reserved for typing
        return _gr.update(visible=bool(retake_on and think_on))

    for trigger in (
        generation_section["retake_enabled"],
        generation_section["think_checkbox"],
    ):
        trigger.change(
            fn=_retake_think_warn,
            inputs=[
                generation_section["retake_enabled"],
                generation_section["think_checkbox"],
            ],
            outputs=[generation_section["retake_think_warning"]],
        )

    # ========== Format Lyrics Button ==========
    generation_section["format_lyrics_btn"].click(
        fn=lambda caption, lyrics, bpm, duration, key_scale, time_sig, temp, top_k, top_p, debug: gen_h.handle_format_lyrics(
            llm_handler, caption, lyrics, bpm, duration, key_scale, time_sig, temp, top_k, top_p, debug
        ),
        inputs=[
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["bpm"],
            generation_section["audio_duration"],
            generation_section["key_scale"],
            generation_section["time_signature"],
            generation_section["lm_temperature"],
            generation_section["lm_top_k"],
            generation_section["lm_top_p"],
            generation_section["constrained_decoding_debug"],
        ],
        outputs=[
            generation_section["lyrics"],
            generation_section["bpm"],
            generation_section["audio_duration"],
            generation_section["key_scale"],
            generation_section["vocal_language"],
            generation_section["time_signature"],
            results_section["is_format_caption_state"],
            results_section["status_output"],
        ],
    ).then(
        fn=gen_h.uncheck_auto_for_populated_fields,
        inputs=list(auto_checkbox_inputs),
        outputs=list(auto_checkbox_outputs),
    )
