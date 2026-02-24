"""Primary generation-tab controls shared across all generation modes."""

from typing import Any

import gradio as gr

from acestep.constants import DEFAULT_DIT_INSTRUCTION
from acestep.ui.gradio.i18n import t

from .generation_tab_simple_controls import build_simple_mode_controls
from .generation_tab_source_controls import build_source_track_and_code_controls


def build_mode_selector_controls(initial_mode_choices: list[str]) -> dict[str, Any]:
    """Create generation mode selector and load-metadata upload controls.

    Args:
        initial_mode_choices: Mode labels available for the currently selected model family.

    Returns:
        A component map containing ``generation_mode``, ``load_file``, and ``load_file_col``.
    """

    with gr.Row(equal_height=True):
        generation_mode = gr.Radio(
            choices=initial_mode_choices,
            value="Custom",
            label=t("generation.mode_label"),
            info=t("generation.mode_info_custom"),
            elem_classes=["has-info-container"],
            scale=10,
        )
        with gr.Column(scale=1, min_width=80, elem_classes="icon-btn-wrap") as load_file_col:
            load_file = gr.UploadButton(
                t("generation.load_btn"),
                file_types=[".json"],
                file_count="single",
                variant="secondary",
                size="lg",
            )
    return {
        "generation_mode": generation_mode,
        "load_file": load_file,
        "load_file_col": load_file_col,
    }


def build_hidden_generation_state() -> dict[str, Any]:
    """Create hidden/state controls consumed by generation event wiring.

    Args:
        None.

    Returns:
        A component map containing hidden task/instruction fields and Gradio state objects.
    """

    task_type = gr.Textbox(value="text2music", visible=False, label="task_type")
    instruction_display_gen = gr.Textbox(
        label=t("generation.instruction_label"),
        value=DEFAULT_DIT_INSTRUCTION,
        interactive=False,
        lines=1,
        info=t("generation.instruction_info"),
        elem_classes=["has-info-container"],
        visible=False,
    )
    simple_sample_created = gr.State(value=False)
    lyrics_before_instrumental = gr.State(value="")
    previous_generation_mode = gr.State(value="Custom")
    return {
        "task_type": task_type,
        "instruction_display_gen": instruction_display_gen,
        "simple_sample_created": simple_sample_created,
        "lyrics_before_instrumental": lyrics_before_instrumental,
        "previous_generation_mode": previous_generation_mode,
    }
