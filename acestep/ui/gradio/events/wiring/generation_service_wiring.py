"""Generation service-layer event wiring helpers.

This module contains wiring related to service initialization, LoRA controls,
auto-checkbox controls, and visibility updates for generation components.
"""

from typing import Any

import gradio as gr

from .. import generation_handlers as gen_h
from ...i18n import get_i18n
from .context import (
    GenerationWiringContext,
    build_auto_checkbox_inputs,
    build_auto_checkbox_outputs,
)


def register_generation_service_handlers(
    context: GenerationWiringContext,
) -> tuple[list[Any], list[Any]]:
    """Register generation service/init handlers and return auto-checkbox lists."""

    dataset_section = context.dataset_section
    generation_section = context.generation_section
    results_section = context.results_section
    dit_handler = context.dit_handler
    llm_handler = context.llm_handler
    dataset_handler = context.dataset_handler

    # ========== Dataset Handlers ==========
    dataset_section["import_dataset_btn"].click(
        fn=dataset_handler.import_dataset,
        inputs=[dataset_section["dataset_type"]],
        outputs=[dataset_section["data_status"]],
    )

    # ========== Service Initialization ==========
    generation_section["refresh_btn"].click(
        fn=lambda: gen_h.refresh_checkpoints(dit_handler),
        outputs=[generation_section["checkpoint_dropdown"]],
    )

    generation_section["language_dropdown"].change(
        fn=lambda language: _apply_runtime_language(language),
        inputs=[generation_section["language_dropdown"]],
        outputs=[generation_section["language_dropdown"]],
    )

    generation_section["config_path"].change(
        fn=gen_h.update_model_type_settings,
        inputs=[generation_section["config_path"], generation_section["generation_mode"]],
        outputs=[
            generation_section["inference_steps"],
            generation_section["guidance_scale"],
            generation_section["use_adg"],
            generation_section["shift"],
            generation_section["cfg_interval_start"],
            generation_section["cfg_interval_end"],
            generation_section["task_type"],
            generation_section["generation_mode"],
            generation_section["init_llm_checkbox"],
        ],
    )

    # ========== Tier Override ==========
    generation_section["tier_dropdown"].change(
        fn=lambda tier: gen_h.on_tier_change(tier, llm_handler),
        inputs=[generation_section["tier_dropdown"]],
        outputs=[
            generation_section["offload_to_cpu_checkbox"],
            generation_section["offload_dit_to_cpu_checkbox"],
            generation_section["compile_model_checkbox"],
            generation_section["quantization_checkbox"],
            generation_section["backend_dropdown"],
            generation_section["lm_model_path"],
            generation_section["init_llm_checkbox"],
            generation_section["batch_size_input"],
            generation_section["audio_duration"],
            generation_section["gpu_info_display"],
        ],
    )

    generation_section["init_btn"].click(
        fn=lambda *args: gen_h.init_service_wrapper(dit_handler, llm_handler, *args),
        inputs=[
            generation_section["checkpoint_dropdown"],
            generation_section["config_path"],
            generation_section["device"],
            generation_section["init_llm_checkbox"],
            generation_section["lm_model_path"],
            generation_section["backend_dropdown"],
            generation_section["use_flash_attention_checkbox"],
            generation_section["offload_to_cpu_checkbox"],
            generation_section["offload_dit_to_cpu_checkbox"],
            generation_section["compile_model_checkbox"],
            generation_section["quantization_checkbox"],
            generation_section["mlx_dit_checkbox"],
            generation_section["generation_mode"],
            generation_section["batch_size_input"],
        ],
        outputs=[
            generation_section["init_status"],
            generation_section["generate_btn"],
            generation_section["service_config_accordion"],
            generation_section["inference_steps"],
            generation_section["guidance_scale"],
            generation_section["use_adg"],
            generation_section["shift"],
            generation_section["cfg_interval_start"],
            generation_section["cfg_interval_end"],
            generation_section["task_type"],
            generation_section["generation_mode"],
            generation_section["init_llm_checkbox"],
            generation_section["audio_duration"],
            generation_section["batch_size_input"],
            generation_section["think_checkbox"],
        ],
    )

    # ========== LoRA Handlers ==========
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

    # ========== Auto Checkbox Handlers ==========
    auto_field_map = {
        "bpm_auto": ("bpm", "bpm"),
        "key_auto": ("key_scale", "key_scale"),
        "timesig_auto": ("time_signature", "time_signature"),
        "vocal_lang_auto": ("vocal_language", "vocal_language"),
        "duration_auto": ("audio_duration", "audio_duration"),
    }
    for auto_key, (field_name, comp_key) in auto_field_map.items():
        generation_section[auto_key].change(
            fn=lambda checked, fn=field_name: gen_h.on_auto_checkbox_change(checked, fn),
            inputs=[generation_section[auto_key]],
            outputs=[generation_section[comp_key]],
        )

    auto_checkbox_outputs = build_auto_checkbox_outputs(context)
    auto_checkbox_inputs = build_auto_checkbox_inputs(context)

    generation_section["reset_all_auto_btn"].click(
        fn=gen_h.reset_all_auto,
        outputs=auto_checkbox_outputs,
    )

    # ========== UI Visibility Updates ==========
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


def _apply_runtime_language(language: str) -> dict[str, Any]:
    """Update global i18n language for runtime-generated messages.

    Args:
        language: Selected UI language code from the language dropdown.

    Returns:
        A ``gr.update`` payload preserving the selected dropdown value.
    """

    get_i18n(language)
    return gr.update(value=language)
