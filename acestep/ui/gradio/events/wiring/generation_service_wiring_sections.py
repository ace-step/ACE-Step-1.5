"""Focused helper sections for generation service wiring."""

from .. import generation_handlers as gen_h
def register_dataset_handlers(dataset_section, dataset_handler) -> None:
    """Bind dataset import actions for the generation page."""

    dataset_section["import_dataset_btn"].click(
        fn=dataset_handler.import_dataset,
        inputs=[dataset_section["dataset_type"]],
        outputs=[dataset_section["data_status"]],
    )
def register_generation_model_handlers(generation_section, dit_handler) -> None:
    """Bind checkpoint refresh and model-type update actions."""

    generation_section["refresh_btn"].click(
        fn=lambda: gen_h.refresh_checkpoints(dit_handler),
        outputs=[generation_section["checkpoint_dropdown"]],
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
def register_external_lm_field_handlers(generation_section) -> None:
    """Bind provider/base-url field synchronization for external LM setup."""

    generation_section["external_llm_provider"].change(
        fn=gen_h.hydrate_external_lm_setup_fields,
        inputs=[generation_section["external_llm_provider"]],
        outputs=[
            generation_section["external_llm_model"],
            generation_section["external_llm_base_url"],
            generation_section["external_llm_base_url_preset"],
            generation_section["external_llm_status"],
        ],
    )
    generation_section["external_llm_base_url_preset"].change(
        fn=gen_h.apply_external_lm_base_url_preset,
        inputs=[
            generation_section["external_llm_provider"],
            generation_section["external_llm_base_url_preset"],
            generation_section["external_llm_base_url"],
        ],
        outputs=[generation_section["external_llm_base_url"]],
    )
    generation_section["external_llm_base_url"].change(
        fn=gen_h.sync_external_lm_base_url_preset,
        inputs=[
            generation_section["external_llm_provider"],
            generation_section["external_llm_base_url"],
        ],
        outputs=[generation_section["external_llm_base_url_preset"]],
    )
def register_generation_init_handlers(generation_section, dit_handler, llm_handler) -> None:
    """Bind tier-change and service initialization actions."""

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
            generation_section["external_llm_provider"],
            generation_section["external_llm_model"],
            generation_section["external_llm_base_url"],
            generation_section["external_llm_api_key"],
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
