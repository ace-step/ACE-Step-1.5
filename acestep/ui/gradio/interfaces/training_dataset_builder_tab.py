"""Dataset-builder tab facade for the Gradio training interface."""

from __future__ import annotations

import gradio as gr

from acestep.ui.gradio.help_content import create_help_button
from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.interfaces.training_dataset_tab_label_preview import (
    build_dataset_label_and_preview_controls,
)
from acestep.ui.gradio.interfaces.training_dataset_tab_save_preprocess import (
    build_dataset_save_and_preprocess_controls,
)
from acestep.ui.gradio.interfaces.training_dataset_tab_scan_settings import (
    build_dataset_scan_and_settings_controls,
)


def create_dataset_builder_tab() -> dict[str, object]:
    """Create the Dataset Builder tab and return all exposed component handles."""

    with gr.Tab(t("training.tab_dataset_builder")):
        create_help_button("training_dataset")
        tab_controls: dict[str, object] = {}
        tab_controls.update(build_dataset_scan_and_settings_controls())
        tab_controls.update(build_dataset_label_and_preview_controls())
        tab_controls.update(build_dataset_save_and_preprocess_controls())
    return tab_controls
