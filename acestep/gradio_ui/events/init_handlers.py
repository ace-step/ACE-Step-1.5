"""
Initialization Event Handlers
Handles app load and UI synchronization with server state
"""
import gradio as gr
from acestep.gradio_ui.events.generation_handlers import get_model_type_ui_settings

def on_app_load(dit_handler, llm_handler):
    """
    Called when the Gradio app loads in the browser.
    Syncs the client-side UI state with the server-side model state.

    Returns updates for:
    - service_config_accordion (open/closed)
    - init_status (text)
    - generate_btn (interactive)
    - inference_steps (value, max)
    - guidance_scale (visible)
    - use_adg (visible)
    - shift (visible)
    - cfg_interval_start (visible)
    - cfg_interval_end (visible)
    - task_type (choices)
    """
    is_model_initialized = dit_handler.model is not None

    if is_model_initialized:
        status_msg = f"✅ Model already initialized (Persistent State)\nConfig: {dit_handler.loaded_config_path}\nDevice: {dit_handler.loaded_device}"
        if llm_handler.llm_initialized:
            status_msg += f"\n✅ LM initialized: {llm_handler.loaded_model_path}"

        # Get model specific settings
        is_turbo = dit_handler.is_turbo_model()
        model_settings = get_model_type_ui_settings(is_turbo)

        return (
            gr.update(open=False),     # Close accordion
            status_msg,                # Update status
            gr.update(interactive=True), # Enable generate button
            *model_settings            # Expand model settings
        )
    else:
        # Not initialized
        # Return default updates (keep accordion open, generate disabled)
        # For model settings, we can default to base model settings or just skip updates
        # But we must return the correct number of outputs

        # Default fallback settings (base model style)
        default_settings = get_model_type_ui_settings(is_turbo=True) # Default to turbo settings UI

        return (
            gr.update(open=True),
            "",
            gr.update(interactive=False),
            *default_settings
        )
