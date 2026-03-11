"""LoKr training-tab facade for the Gradio training interface."""

from __future__ import annotations

import gradio as gr

from acestep.ui.gradio.help_content import create_help_button
from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.interfaces.training_lokr_tab_dataset import (
    build_lokr_dataset_and_adapter_controls,
)
from acestep.ui.gradio.interfaces.training_lokr_tab_run_export import (
    build_lokr_run_and_export_controls,
)


def create_training_lokr_tab() -> dict[str, object]:
    """Create the LoKr training tab and return component handles for wiring."""

    with gr.Tab(t("training.tab_train_lokr")):
        create_help_button("training_lokr")
        tab_controls: dict[str, object] = {}
        tab_controls.update(build_lokr_dataset_and_adapter_controls())
        tab_controls.update(build_lokr_run_and_export_controls())
    return tab_controls
