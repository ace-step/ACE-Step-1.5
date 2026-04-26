"""Output and automation controls for generation advanced settings."""

from typing import Any

import gradio as gr

from acestep.ui.gradio.i18n import t


_MP3_BITRATE_CHOICES = [("128 kbps", "128k"), ("192 kbps", "192k"), ("256 kbps", "256k"), ("320 kbps", "320k")]
_MP3_SAMPLE_RATE_CHOICES = [("48 kHz", 48000), ("44.1 kHz", 44100)]


def _update_mp3_control_visibility(audio_format: str, service_mode: bool = False):
    """Return visibility and interactivity updates for MP3-only controls."""
    visible = audio_format == "mp3"
    interactive = visible and not service_mode
    return (
        gr.update(visible=visible),
        gr.update(choices=_MP3_BITRATE_CHOICES, visible=visible, interactive=interactive),
        gr.update(choices=_MP3_SAMPLE_RATE_CHOICES, visible=visible, interactive=interactive),
    )


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
    initial_audio_format = params.get("audio_format", "mp3")
    initial_mp3_visible = initial_audio_format == "mp3"
    with gr.Accordion(t("generation.advanced_output_section"), open=False, elem_classes=["has-info-container"]):
        with gr.Row():
            with gr.Column(scale=1):
                audio_format = gr.Dropdown(
                    choices=[
                        ("FLAC", "flac"),
                        ("MP3", "mp3"),
                        ("Opus", "opus"),
                        ("AAC", "aac"),
                        ("WAV (16-bit)", "wav"),
                        ("WAV (32-bit Float)", "wav32"),
                    ],
                    value=initial_audio_format,
                    label=t("generation.audio_format_label"),
                    info=t("generation.audio_format_info"),
                    elem_id="acestep-audio-format",
                    elem_classes=["has-info-container"],
                    interactive=not service_mode,
                )
                with gr.Row(visible=initial_mp3_visible) as mp3_controls_row:
                    mp3_bitrate = gr.Dropdown(
                        choices=[
                            ("128 kbps", "128k"),
                            ("192 kbps", "192k"),
                            ("256 kbps", "256k"),
                            ("320 kbps", "320k"),
                        ],
                        value=params.get("mp3_bitrate", "128k"),
                        label=t("generation.mp3_bitrate_label"),
                        info=t("generation.mp3_bitrate_info"),
                        elem_id="acestep-mp3-bitrate",
                        elem_classes=["has-info-container"],
                        visible=initial_mp3_visible,
                        interactive=initial_mp3_visible and not service_mode,
                        scale=1,
                    )
                    mp3_sample_rate = gr.Dropdown(
                        choices=[
                            ("48 kHz", 48000),
                            ("44.1 kHz", 44100),
                        ],
                        value=params.get("mp3_sample_rate", 48000),
                        label=t("generation.mp3_sample_rate_label"),
                        info=t("generation.mp3_sample_rate_info"),
                        elem_id="acestep-mp3-sample-rate",
                        elem_classes=["has-info-container"],
                        visible=initial_mp3_visible,
                        interactive=initial_mp3_visible and not service_mode,
                        scale=1,
                    )
            with gr.Column(scale=1):
                score_scale = gr.Slider(
                    minimum=0.01,
                    maximum=1.0,
                    value=0.5,
                    step=0.01,
                    label=t("generation.score_sensitivity_label"),
                    info=t("generation.score_sensitivity_info"),
                    elem_id="acestep-score-scale",
                    elem_classes=["has-info-container"],
                    scale=1,
                    visible=not service_mode,
                )
        audio_format.change(
            fn=lambda value: _update_mp3_control_visibility(value, service_mode),
            inputs=[audio_format],
            outputs=[mp3_controls_row, mp3_bitrate, mp3_sample_rate],
        )
        with gr.Row():
            enable_normalization = gr.Checkbox(
                label=t("generation.enable_normalization"),
                value=params.get("enable_normalization", True) if service_pre_initialized else True,
                info=t("generation.enable_normalization_info"),
                elem_id="acestep-enable-normalization",
                elem_classes=["has-info-container"],
            )
            normalization_db = gr.Slider(
                label=t("generation.normalization_db"),
                minimum=-10.0,
                maximum=0.0,
                step=0.1,
                value=params.get("normalization_db", -1.0) if service_pre_initialized else -1.0,
                info=t("generation.normalization_db_info"),
                elem_id="acestep-normalization-db",
                elem_classes=["has-info-container"],
            )
        with gr.Row():
            fade_in_duration = gr.Slider(
                label=t("generation.fade_in_duration"),
                minimum=0.0,
                maximum=10.0,
                step=0.1,
                value=params.get("fade_in_duration", 0.0) if service_pre_initialized else 0.0,
                info=t("generation.fade_in_duration_info"),
                elem_id="acestep-fade-in-duration",
                elem_classes=["has-info-container"],
            )
            fade_out_duration = gr.Slider(
                label=t("generation.fade_out_duration"),
                minimum=0.0,
                maximum=10.0,
                step=0.1,
                value=params.get("fade_out_duration", 0.0) if service_pre_initialized else 0.0,
                info=t("generation.fade_out_duration_info"),
                elem_id="acestep-fade-out-duration",
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
                elem_id="acestep-latent-shift",
                elem_classes=["has-info-container"],
            )
            latent_rescale = gr.Slider(
                label=t("generation.latent_rescale"),
                minimum=0.5,
                maximum=1.5,
                step=0.01,
                value=params.get("latent_rescale", 1.0) if service_pre_initialized else 1.0,
                info=t("generation.latent_rescale_info"),
                elem_id="acestep-latent-rescale",
                elem_classes=["has-info-container"],
            )
    return {
        "audio_format": audio_format,
        "mp3_controls_row": mp3_controls_row,
        "mp3_bitrate": mp3_bitrate,
        "mp3_sample_rate": mp3_sample_rate,
        "score_scale": score_scale,
        "enable_normalization": enable_normalization,
        "normalization_db": normalization_db,
        "fade_in_duration": fade_in_duration,
        "fade_out_duration": fade_out_duration,
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
                elem_id="acestep-lm-batch-chunk-size",
                elem_classes=["has-info-container"],
            )
    return {"lm_batch_chunk_size": lm_batch_chunk_size}
