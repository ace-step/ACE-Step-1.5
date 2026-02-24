"""Source-audio, track selection, and LM-code hint controls for generation tab."""

from typing import Any

import gradio as gr

from acestep.constants import TRACK_NAMES
from acestep.ui.gradio.help_content import create_help_button
from acestep.ui.gradio.i18n import t


def build_source_audio_controls() -> dict[str, Any]:
    """Create source-audio controls used by remix/repaint/extract flows.

    Args:
        None.

    Returns:
        A component map containing ``src_audio_row``, ``src_audio``, ``analyze_btn``, and ``extract_help_group``.
    """

    with gr.Row(equal_height=True, visible=False) as src_audio_row:
        src_audio = gr.Audio(label=t("generation.source_audio"), type="filepath", scale=10)
        with gr.Column(scale=1, min_width=80):
            analyze_btn = gr.Button(
                t("generation.analyze_btn"),
                variant="secondary",
                size="lg",
            )

    with gr.Group(visible=False) as extract_help_group:
        create_help_button("generation_extract")
    return {
        "src_audio_row": src_audio_row,
        "src_audio": src_audio,
        "analyze_btn": analyze_btn,
        "extract_help_group": extract_help_group,
    }


def build_track_selection_controls() -> dict[str, Any]:
    """Create track selection controls for extract and complete generation modes.

    Args:
        None.

    Returns:
        A component map containing ``track_name``, ``complete_help_group``, and ``complete_track_classes``.
    """

    track_name = gr.Dropdown(
        choices=TRACK_NAMES,
        value=None,
        label=t("generation.track_name_label"),
        info=t("generation.track_name_info"),
        elem_classes=["has-info-container"],
        visible=False,
    )
    with gr.Group(visible=False) as complete_help_group:
        create_help_button("generation_complete")
    complete_track_classes = gr.CheckboxGroup(
        choices=TRACK_NAMES,
        label=t("generation.track_classes_label"),
        info=t("generation.track_classes_info"),
        elem_classes=["has-info-container"],
        visible=False,
    )
    return {
        "track_name": track_name,
        "complete_help_group": complete_help_group,
        "complete_track_classes": complete_track_classes,
    }


def build_lm_code_hint_controls() -> dict[str, Any]:
    """Create optional LM code-hint controls for text2music generation.

    Args:
        None.

    Returns:
        A component map containing LM code hint controls and action buttons.
    """

    with gr.Accordion(
        t("generation.lm_codes_hints"),
        open=False,
        visible=True,
        elem_classes=["has-info-container"],
    ) as text2music_audio_codes_group:
        with gr.Row(equal_height=True):
            lm_codes_audio_upload = gr.Audio(label=t("generation.source_audio"), type="filepath", scale=3)
            text2music_audio_code_string = gr.Textbox(
                label=t("generation.lm_codes_label"),
                placeholder=t("generation.lm_codes_placeholder"),
                lines=6,
                info=t("generation.lm_codes_info"),
                elem_classes=["has-info-container"],
                scale=6,
            )
        with gr.Row():
            convert_src_to_codes_btn = gr.Button(
                t("generation.convert_codes_btn"),
                variant="secondary",
                size="sm",
                scale=1,
            )
            transcribe_btn = gr.Button(
                t("generation.transcribe_btn"),
                variant="secondary",
                size="sm",
                scale=1,
            )
    return {
        "text2music_audio_codes_group": text2music_audio_codes_group,
        "lm_codes_audio_upload": lm_codes_audio_upload,
        "text2music_audio_code_string": text2music_audio_code_string,
        "convert_src_to_codes_btn": convert_src_to_codes_btn,
        "transcribe_btn": transcribe_btn,
    }


def build_source_track_and_code_controls() -> dict[str, Any]:
    """Create source-audio, track-selector, and LM-code hint controls.

    Args:
        None.

    Returns:
        A component map containing source audio actions, track selectors, and LM code controls.
    """

    source_audio_controls = build_source_audio_controls()
    track_selection_controls = build_track_selection_controls()
    lm_code_hint_controls = build_lm_code_hint_controls()

    return {
        "src_audio_row": source_audio_controls["src_audio_row"],
        "src_audio": source_audio_controls["src_audio"],
        "analyze_btn": source_audio_controls["analyze_btn"],
        "extract_help_group": source_audio_controls["extract_help_group"],
        "track_name": track_selection_controls["track_name"],
        "complete_help_group": track_selection_controls["complete_help_group"],
        "complete_track_classes": track_selection_controls["complete_track_classes"],
        "text2music_audio_codes_group": lm_code_hint_controls["text2music_audio_codes_group"],
        "lm_codes_audio_upload": lm_code_hint_controls["lm_codes_audio_upload"],
        "text2music_audio_code_string": lm_code_hint_controls["text2music_audio_code_string"],
        "convert_src_to_codes_btn": lm_code_hint_controls["convert_src_to_codes_btn"],
        "transcribe_btn": lm_code_hint_controls["transcribe_btn"],
    }
