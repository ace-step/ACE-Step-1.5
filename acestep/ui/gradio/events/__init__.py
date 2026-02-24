"""
Gradio UI Event Handlers Module
Main entry point for setting up all event handlers
"""
# Import handler modules
from .wiring import (
    GenerationWiringContext,
    TrainingWiringContext,
    build_mode_ui_outputs,
    register_generation_batch_navigation_handlers,
    register_generation_metadata_file_handlers,
    register_generation_metadata_handlers,
    register_generation_mode_handlers,
    register_generation_run_handlers,
    register_results_aux_handlers,
    register_results_restore_and_lrc_handlers,
    register_results_save_button_handlers,
    register_generation_service_handlers,
    register_training_dataset_builder_handlers,
    register_training_dataset_load_handler,
    register_training_preprocess_handler,
    register_training_run_handlers,
)


def setup_event_handlers(demo, dit_handler, llm_handler, dataset_handler, dataset_section, generation_section, results_section):
    """Setup generation/results event wiring for the Gradio UI.

    Args:
        demo (Any): Root Gradio demo/container used to register events.
        dit_handler (Any): Inference service used by generation/results callbacks.
        llm_handler (Any): LLM service used by metadata/text callbacks.
        dataset_handler (Any): Dataset service used by generation wiring.
        dataset_section (dict[str, Any]): Dataset UI component map.
        generation_section (dict[str, Any]): Generation UI component map.
        results_section (dict[str, Any]): Results UI component map.

    Local wiring values:
        wiring_context (GenerationWiringContext): Shared typed context for
            generation/results wiring helper modules.
        auto_checkbox_inputs (list[Any]): Ordered metadata fields used for
            auto-checkbox synchronization; forwarded to
            register_generation_metadata_handlers and
            register_generation_mode_handlers.
        auto_checkbox_outputs (list[Any]): Ordered auto toggles plus derived
            metadata outputs returned by register_generation_service_handlers;
            forwarded to register_generation_metadata_handlers and
            register_generation_mode_handlers.
        mode_ui_outputs (list[Any]): Ordered mode-UI outputs from
            build_mode_ui_outputs; forwarded to
            register_generation_mode_handlers and register_results_aux_handlers.

    Returns:
        None: Registers event handlers in-place on the supplied components.
    """
    wiring_context = GenerationWiringContext(
        demo=demo,
        dit_handler=dit_handler,
        llm_handler=llm_handler,
        dataset_handler=dataset_handler,
        dataset_section=dataset_section,
        generation_section=generation_section,
        results_section=results_section,
    )
    
    auto_checkbox_inputs, auto_checkbox_outputs = register_generation_service_handlers(
        wiring_context
    )
    mode_ui_outputs = build_mode_ui_outputs(wiring_context)
    register_generation_metadata_handlers(
        wiring_context,
        auto_checkbox_inputs=auto_checkbox_inputs,
        auto_checkbox_outputs=auto_checkbox_outputs,
    )

    register_generation_mode_handlers(
        wiring_context,
        mode_ui_outputs=mode_ui_outputs,
        auto_checkbox_inputs=auto_checkbox_inputs,
        auto_checkbox_outputs=auto_checkbox_outputs,
    )

    register_generation_metadata_file_handlers(
        wiring_context,
        auto_checkbox_inputs=auto_checkbox_inputs,
        auto_checkbox_outputs=auto_checkbox_outputs,
    )
    register_results_save_button_handlers(wiring_context)
    register_results_aux_handlers(
        wiring_context,
        mode_ui_outputs=mode_ui_outputs,
    )
    register_generation_run_handlers(wiring_context)
    register_generation_batch_navigation_handlers(wiring_context)
    register_results_restore_and_lrc_handlers(wiring_context)


def setup_training_event_handlers(demo, dit_handler, llm_handler, training_section):
    """Setup event handlers for the training tab (dataset builder and LoRA training)"""
    training_context = TrainingWiringContext(
        demo=demo,
        dit_handler=dit_handler,
        llm_handler=llm_handler,
        training_section=training_section,
    )
    
    # ========== Load Existing Dataset (Top Section) ==========

    # Load existing dataset JSON at the top of Dataset Builder
    register_training_dataset_load_handler(
        training_context,
        button_key="load_json_btn",
        path_key="load_json_path",
        status_key="load_json_status",
    )
    # ========== Dataset Builder Handlers ==========
    register_training_dataset_builder_handlers(training_context)

    # ========== Preprocess Handlers ==========
    
    # Load existing dataset JSON for preprocessing
    # This also updates the preview section so users can view/edit samples
    register_training_dataset_load_handler(
        training_context,
        button_key="load_existing_dataset_btn",
        path_key="load_existing_dataset_path",
        status_key="load_existing_status",
    )
    
    # Preprocess dataset to tensor files
    register_training_preprocess_handler(training_context)
    register_training_run_handlers(training_context)
