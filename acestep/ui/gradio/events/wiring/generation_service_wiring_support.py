"""Support wiring helpers for generation service interactions."""

from typing import Any

import gradio as gr

from .. import generation_handlers as gen_h
from .context import (
    GenerationWiringContext,
    build_auto_checkbox_inputs,
    build_auto_checkbox_outputs,
)


def register_generation_support_handlers(
    context: GenerationWiringContext,
) -> tuple[list[Any], list[Any]]:
    """Bind LoRA, auto-checkbox, and UI visibility support handlers."""

    generation_section = context.generation_section
    results_section = context.results_section
    dit_handler = context.dit_handler

    generation_section["load_lora_btn"].click(
        fn=dit_handler.load_lora,
        inputs=[generation_section["lora_path"]],
        outputs=[generation_section["lora_status"]],
    ).then(
        fn=lambda: gr.update(value=True),
        outputs=[generation_section["use_lora_checkbox"]],
    )
    generation_section["unload_lora_btn"].click(
        fn=dit_handler.unload_lora,
        outputs=[generation_section["lora_status"]],
    ).then(
        fn=lambda: gr.update(value=False),
        outputs=[generation_section["use_lora_checkbox"]],
    )
    generation_section["use_lora_checkbox"].change(
        fn=dit_handler.set_use_lora,
        inputs=[generation_section["use_lora_checkbox"]],
        outputs=[generation_section["lora_status"]],
    )
    generation_section["lora_scale_slider"].change(
        fn=dit_handler.set_lora_scale,
        inputs=[generation_section["lora_scale_slider"]],
        outputs=[generation_section["lora_status"]],
    )

    auto_field_map = {
        "bpm_auto": "bpm",
        "key_auto": "key_scale",
        "timesig_auto": "time_signature",
        "vocal_lang_auto": "vocal_language",
        "duration_auto": "audio_duration",
    }
    for auto_key, field_name in auto_field_map.items():
        generation_section[auto_key].change(
            fn=lambda checked, fn=field_name: gen_h.on_auto_checkbox_change(checked, fn),
            inputs=[generation_section[auto_key]],
            outputs=[generation_section[field_name]],
        )

    auto_checkbox_outputs = build_auto_checkbox_outputs(context)
    auto_checkbox_inputs = build_auto_checkbox_inputs(context)
    generation_section["reset_all_auto_btn"].click(
        fn=gen_h.reset_all_auto,
        outputs=auto_checkbox_outputs,
    )
    generation_section["init_llm_checkbox"].change(
        fn=gen_h.update_negative_prompt_visibility,
        inputs=[generation_section["init_llm_checkbox"]],
        outputs=[generation_section["lm_negative_prompt"]],
    )
    generation_section["batch_size_input"].change(
        fn=gen_h.update_audio_components_visibility,
        inputs=[generation_section["batch_size_input"]],
        outputs=[
            results_section["audio_col_1"],
            results_section["audio_col_2"],
            results_section["audio_col_3"],
            results_section["audio_col_4"],
            results_section["audio_row_5_8"],
            results_section["audio_col_5"],
            results_section["audio_col_6"],
            results_section["audio_col_7"],
            results_section["audio_col_8"],
        ],
    )
    return auto_checkbox_inputs, auto_checkbox_outputs
