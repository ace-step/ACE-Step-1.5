"""Gradio UI training-tab facade that composes focused tab builders."""

from __future__ import annotations

import gradio as gr

from acestep.constants import DEBUG_TRAINING
from acestep.ui.gradio.interfaces.training_dataset_builder_tab import (
    create_dataset_builder_tab,
)
from acestep.ui.gradio.interfaces.training_lokr_tab import create_training_lokr_tab
from acestep.ui.gradio.interfaces.training_lora_tab import create_training_lora_tab


def _resolve_epoch_slider_defaults() -> tuple[int, int, int]:
    """Return epoch slider defaults adjusted for training debug mode."""

    debug_training_enabled = str(DEBUG_TRAINING).strip().upper() != "OFF"
    if debug_training_enabled:
        return 1, 1, 1
    return 100, 100, 1000


def create_training_section(dit_handler, llm_handler, init_params=None) -> dict:
    """Create the training-tab content without the outer ``gr.Tab`` wrapper.

    Args:
        dit_handler: DiT handler instance.
        llm_handler: LLM handler instance.
        init_params: Optional initialization parameters.

    Returns:
        Mapping of component keys to Gradio components for training-event wiring.
    """

    del dit_handler, llm_handler, init_params

    epoch_min, epoch_step, epoch_default = _resolve_epoch_slider_defaults()

    gr.HTML(
        """
    <div style="text-align: center; padding: 10px; margin-bottom: 15px;">
        <h2>🎵 LoRA Training for ACE-Step</h2>
        <p>Build datasets from your audio files and train custom LoRA adapters</p>
    </div>
    """
    )

    training_section: dict[str, object] = {}
    with gr.Tabs():
        training_section.update(create_dataset_builder_tab())
        training_section.update(
            create_training_lora_tab(
                epoch_min=epoch_min,
                epoch_step=epoch_step,
                epoch_default=epoch_default,
            )
        )
        training_section.update(create_training_lokr_tab())
        dataset_builder_state = gr.State(None)
        training_state = gr.State({"is_training": False, "should_stop": False})
        training_section.update(
            {
                "dataset_builder_state": dataset_builder_state,
                "training_state": training_state,
            }
        )
    return training_section
