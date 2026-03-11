"""LoRA training-tab facade for the Gradio training interface."""

from __future__ import annotations

import gradio as gr

from acestep.ui.gradio.help_content import create_help_button
from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.interfaces.training_lora_tab_dataset import (
    build_lora_dataset_and_adapter_controls,
)
from acestep.ui.gradio.interfaces.training_lora_tab_run_export import (
    build_lora_run_and_export_controls,
)


def create_training_lora_tab(
    *,
    epoch_min: int,
    epoch_step: int,
    epoch_default: int,
) -> dict[str, object]:
    """Create the LoRA training tab and return component handles for wiring."""

    with gr.Tab(t("training.tab_train_lora")):
        create_help_button("training_train")
        tab_controls: dict[str, object] = {}
        tab_controls.update(build_lora_dataset_and_adapter_controls())
        tab_controls.update(
            build_lora_run_and_export_controls(
                epoch_min=epoch_min,
                epoch_step=epoch_step,
                epoch_default=epoch_default,
            )
        )
    return tab_controls
