"""Optional-parameter controls for the generation tab."""

from typing import Any

import gradio as gr

from acestep.constants import VALID_LANGUAGES
from acestep.ui.gradio.i18n import t


def build_optional_parameter_controls(
    max_duration: float,
    max_batch_size: int,
    default_batch_size: int,
    service_mode: bool,
) -> dict[str, Any]:
    """Create optional generation metadata controls and auto-toggle controls.

    Args:
        max_duration: Maximum allowed duration derived from current GPU profile.
        max_batch_size: Maximum allowed batch size derived from current GPU profile.
        default_batch_size: Initial batch size value shown in the UI.
        service_mode: Whether the UI is running in service mode (disables some controls).

    Returns:
        A component map containing optional metadata fields and auto-toggle controls.
    """

    with gr.Accordion(
        t("generation.optional_params"),
        open=False,
        visible=True,
        elem_classes=["has-info-container"],
    ) as optional_params_accordion:
        with gr.Row():
            bpm = gr.Number(
                label=t("generation.bpm_label"),
                value=None,
                step=1,
                info=t("generation.bpm_info"),
                elem_classes=["has-info-container"],
                interactive=not service_mode,
            )
            key_scale = gr.Textbox(
                label=t("generation.keyscale_label"),
                placeholder=t("generation.keyscale_placeholder"),
                value="",
                info=t("generation.keyscale_info"),
                elem_classes=["has-info-container"],
                interactive=not service_mode,
            )
            time_signature = gr.Dropdown(
                choices=["", "2", "3", "4", "6", "N/A"],
                value="",
                label=t("generation.timesig_label"),
                allow_custom_value=True,
                info=t("generation.timesig_info"),
                elem_classes=["has-info-container"],
                interactive=not service_mode,
            )
            vocal_language = gr.Dropdown(
                choices=[(lang if lang != "unknown" else "Instrumental / auto", lang) for lang in VALID_LANGUAGES],
                value="unknown",
                label=t("generation.vocal_language_label"),
                info=t("generation.vocal_language_info"),
                allow_custom_value=True,
                elem_classes=["has-info-container"],
                interactive=not service_mode,
            )
        with gr.Row(elem_classes=["auto-toggles-row"]):
            bpm_auto = gr.Checkbox(
                label=t("generation.bpm_auto_label"),
                value=True,
                container=False,
                elem_classes=["auto-toggle"],
            )
            key_auto = gr.Checkbox(
                label=t("generation.key_auto_label"),
                value=True,
                container=False,
                elem_classes=["auto-toggle"],
            )
            timesig_auto = gr.Checkbox(
                label=t("generation.timesig_auto_label"),
                value=True,
                container=False,
                elem_classes=["auto-toggle"],
            )
            vocal_lang_auto = gr.Checkbox(
                label=t("generation.vocal_lang_auto_label"),
                value=True,
                container=False,
                elem_classes=["auto-toggle"],
            )
        with gr.Row():
            audio_duration = gr.Number(
                label=t("generation.duration_label"),
                value=-1,
                minimum=-1,
                maximum=float(max_duration),
                step=0.1,
                info=t("generation.duration_info")
                + f" (Max: {max_duration}s / {max_duration // 60} min)",
                elem_classes=["has-info-container"],
                interactive=not service_mode,
            )
            batch_size_input = gr.Number(
                label=t("generation.batch_size_label"),
                value=default_batch_size,
                minimum=1,
                maximum=max_batch_size,
                step=1,
                info=t("generation.batch_size_info") + f" (Max: {max_batch_size})",
                elem_classes=["has-info-container"],
                interactive=not service_mode,
            )
        with gr.Row(elem_classes=["auto-toggles-row"]):
            duration_auto = gr.Checkbox(
                label=t("generation.duration_auto_label"),
                value=True,
                container=False,
                elem_classes=["auto-toggle"],
            )
            gr.HTML("<span></span>")
        reset_all_auto_btn = gr.Button(t("generation.reset_all_auto"), variant="secondary", size="sm")

    return {
        "optional_params_accordion": optional_params_accordion,
        "bpm": bpm,
        "key_scale": key_scale,
        "time_signature": time_signature,
        "vocal_language": vocal_language,
        "bpm_auto": bpm_auto,
        "key_auto": key_auto,
        "timesig_auto": timesig_auto,
        "vocal_lang_auto": vocal_lang_auto,
        "audio_duration": audio_duration,
        "batch_size_input": batch_size_input,
        "duration_auto": duration_auto,
        "reset_all_auto_btn": reset_all_auto_btn,
    }
