"""Output and automation controls for generation advanced settings."""

from typing import Any

import gradio as gr

from acestep.ui.gradio.i18n import t


def build_output_controls(
    service_pre_initialized: bool,
    service_mode: bool,
    init_params: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create audio-output and post-processing controls for advanced settings.

    Args:
        service_pre_initialized: Whether existing init params should prefill values.
        service_mode: Whether the UI is running in service mode (disables some controls).
        init_params: Optional startup state containing persisted output values.

    Returns:
        A component map containing format, scoring, normalization, and latent controls.
    """

    params = init_params or {}
    with gr.Accordion(t("generation.advanced_output_section"), open=False, elem_classes=["has-info-container"]):
        with gr.Row():
            audio_format = gr.Dropdown(
                choices=[
                    ("FLAC", "flac"),
                    ("MP3", "mp3"),
                    ("Opus", "opus"),
                    ("AAC", "aac"),
                    ("WAV (16-bit)", "wav"),
                    ("WAV (32-bit Float)", "wav32"),
                ],
                value="mp3",
                label=t("generation.audio_format_label"),
                info=t("generation.audio_format_info"),
                elem_classes=["has-info-container"],
                interactive=not service_mode,
            )
            score_scale = gr.Slider(
                minimum=0.01,
                maximum=1.0,
                value=0.5,
                step=0.01,
                label=t("generation.score_sensitivity_label"),
                info=t("generation.score_sensitivity_info"),
                elem_classes=["has-info-container"],
                scale=1,
                visible=not service_mode,
            )
        with gr.Row():
            enable_normalization = gr.Checkbox(
                label=t("generation.enable_normalization"),
                value=params.get("enable_normalization", True) if service_pre_initialized else True,
                info=t("generation.enable_normalization_info"),
                elem_classes=["has-info-container"],
            )
            normalization_db = gr.Slider(
                label=t("generation.normalization_db"),
                minimum=-10.0,
                maximum=0.0,
                step=0.1,
                value=params.get("normalization_db", -1.0) if service_pre_initialized else -1.0,
                info=t("generation.normalization_db_info"),
                elem_classes=["has-info-container"],
            )
        with gr.Row():
            latent_shift = gr.Slider(
                label=t("generation.latent_shift"),
                minimum=-0.2,
                maximum=0.2,
                step=0.01,
                value=params.get("latent_shift", 0.0) if service_pre_initialized else 0.0,
                info=t("generation.latent_shift_info"),
                elem_classes=["has-info-container"],
            )
            latent_rescale = gr.Slider(
                label=t("generation.latent_rescale"),
                minimum=0.5,
                maximum=1.5,
                step=0.01,
                value=params.get("latent_rescale", 1.0) if service_pre_initialized else 1.0,
                info=t("generation.latent_rescale_info"),
                elem_classes=["has-info-container"],
            )
    return {
        "audio_format": audio_format,
        "score_scale": score_scale,
        "enable_normalization": enable_normalization,
        "normalization_db": normalization_db,
        "latent_shift": latent_shift,
        "latent_rescale": latent_rescale,
    }


def build_automation_controls(service_mode: bool) -> dict[str, Any]:
    """Create automation controls for LM batch chunking.

    Args:
        service_mode: Whether the UI is running in service mode (disables some controls).

    Returns:
        A component map containing ``lm_batch_chunk_size``.
    """

    with gr.Accordion(
        t("generation.advanced_automation_section"),
        open=False,
        elem_classes=["has-info-container"],
    ):
        with gr.Row():
            lm_batch_chunk_size = gr.Number(
                label=t("generation.lm_batch_chunk_label"),
                value=8,
                minimum=1,
                maximum=32,
                step=1,
                info=t("generation.lm_batch_chunk_info"),
                scale=1,
                interactive=not service_mode,
                elem_classes=["has-info-container"],
            )
    return {"lm_batch_chunk_size": lm_batch_chunk_size}
