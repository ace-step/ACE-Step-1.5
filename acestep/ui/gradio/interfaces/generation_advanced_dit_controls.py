"""DiT diffusion controls for generation advanced settings."""

from typing import Any

import gradio as gr

from acestep.gpu_config import get_global_gpu_config, is_mps_platform
from acestep.ui.gradio.events.dcw_defaults import get_dcw_defaults_for_think
from acestep.ui.gradio.help_content import create_help_button
from acestep.ui.gradio.i18n import t


def build_dit_controls(ui_config: dict[str, Any], think_enabled: bool = False) -> dict[str, Any]:
    """Create DiT diffusion controls for advanced settings.

    Args:
        ui_config: Visibility/range/value configuration returned by generation handler UI config logic.
        think_enabled: Whether initial Think-mode DCW defaults should be used.

    Returns:
        A component map containing DiT sampling, CFG interval, ADG, shift, and seed controls.
    """
    dcw_defaults = get_dcw_defaults_for_think(think_enabled)

    with gr.Accordion(t("generation.advanced_dit_section"), open=True, elem_classes=["has-info-container"]):
        create_help_button("generation_advanced")
        with gr.Row():
            inference_steps = gr.Slider(
                minimum=ui_config["inference_steps_minimum"],
                maximum=ui_config["inference_steps_maximum"],
                value=ui_config["inference_steps_value"],
                step=1,
                label=t("generation.inference_steps_label"),
                info=t("generation.inference_steps_info"),
                elem_classes=["has-info-container"],
            )
            guidance_scale = gr.Slider(
                minimum=1.0,
                maximum=15.0,
                value=7.0,
                step=0.1,
                label=t("generation.guidance_scale_label"),
                info=t("generation.guidance_scale_info"),
                elem_classes=["has-info-container"],
                visible=ui_config["guidance_scale_visible"],
            )
            infer_method = gr.Dropdown(
                choices=["ode", "sde"],
                value="ode",
                label=t("generation.infer_method_label"),
                info=t("generation.infer_method_info"),
                elem_classes=["has-info-container"],
            )
            sampler_mode = gr.Dropdown(
                choices=["euler", "heun"],
                value="euler",
                label=t("generation.sampler_mode_label"),
                info=t("generation.sampler_mode_info"),
                elem_classes=["has-info-container"],
            )
        with gr.Row():
            velocity_norm_threshold = gr.Slider(
                minimum=0.0,
                maximum=5.0,
                value=0.0,
                step=0.1,
                label=t("generation.velocity_norm_threshold_label"),
                info=t("generation.velocity_norm_threshold_info"),
                elem_classes=["has-info-container"],
            )
            velocity_ema_factor = gr.Slider(
                minimum=0.0,
                maximum=0.5,
                value=0.0,
                step=0.01,
                label=t("generation.velocity_ema_factor_label"),
                info=t("generation.velocity_ema_factor_info"),
                elem_classes=["has-info-container"],
            )
        with gr.Accordion(t("generation.dcw_section"), open=False, elem_classes=["has-info-container"]):
            with gr.Row():
                dcw_enabled = gr.Checkbox(
                    label=t("generation.dcw_enabled_label"),
                    value=True,
                    info=t("generation.dcw_enabled_info"),
                    elem_classes=["has-info-container"],
                )
                dcw_mode = gr.Dropdown(
                    choices=["low", "high", "double", "pix"],
                    value=dcw_defaults["mode"],
                    label=t("generation.dcw_mode_label"),
                    info=t("generation.dcw_mode_info"),
                    elem_classes=["has-info-container"],
                )
                dcw_wavelet = gr.Dropdown(
                    choices=["haar", "db2", "db4", "sym4", "sym8", "coif2"],
                    value="haar",
                    label=t("generation.dcw_wavelet_label"),
                    info=t("generation.dcw_wavelet_info"),
                    elem_classes=["has-info-container"],
                )
            with gr.Row():
                dcw_scaler = gr.Slider(
                    minimum=0.0,
                    maximum=0.1,
                    value=dcw_defaults["scaler"],
                    step=0.005,
                    label=t("generation.dcw_scaler_label"),
                    info=t("generation.dcw_scaler_info"),
                    elem_classes=["has-info-container"],
                )
                dcw_high_scaler = gr.Slider(
                    minimum=0.0,
                    maximum=0.1,
                    value=dcw_defaults["high_scaler"],
                    step=0.005,
                    label=t("generation.dcw_high_scaler_label"),
                    info=t("generation.dcw_high_scaler_info"),
                    elem_classes=["has-info-container"],
                )
        with gr.Row():
            use_adg = gr.Checkbox(
                label=t("generation.use_adg_label"),
                value=False,
                info=t("generation.use_adg_info"),
                elem_classes=["has-info-container"],
                visible=ui_config["use_adg_visible"],
            )
            shift = gr.Slider(
                minimum=1.0,
                maximum=5.0,
                value=ui_config["shift_value"],
                step=0.1,
                label=t("generation.shift_label"),
                info=t("generation.shift_info"),
                elem_classes=["has-info-container"],
                visible=ui_config["shift_visible"],
            )
        with gr.Row():
            custom_timesteps = gr.Textbox(
                label=t("generation.custom_timesteps_label"),
                placeholder="0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0",
                value="",
                info=t("generation.custom_timesteps_info"),
                elem_classes=["has-info-container"],
            )
        with gr.Row():
            cfg_interval_start = gr.Slider(
                minimum=0.0,
                maximum=1.0,
                value=0.0,
                step=0.01,
                label=t("generation.cfg_interval_start"),
                info=t("generation.cfg_interval_start_info"),
                visible=ui_config["cfg_interval_start_visible"],
                elem_classes=["has-info-container"],
            )
            cfg_interval_end = gr.Slider(
                minimum=0.0,
                maximum=1.0,
                value=1.0,
                step=0.01,
                label=t("generation.cfg_interval_end"),
                info=t("generation.cfg_interval_end_info"),
                visible=ui_config["cfg_interval_end_visible"],
                elem_classes=["has-info-container"],
            )
        with gr.Row():
            with gr.Column():
                seed = gr.Textbox(
                    label=t("generation.seed_label"),
                    value="-1",
                    info=t("generation.seed_info"),
                    elem_classes=["has-info-container"],
                )
                random_seed_checkbox = gr.Checkbox(
                    label=t("generation.random_seed_label"),
                    value=True,
                    info=t("generation.random_seed_info"),
                    elem_classes=["has-info-container"],
                )
        _gpu_config = get_global_gpu_config()
        _show_mlx_chunk = is_mps_platform()
        with gr.Row(visible=_show_mlx_chunk):
            mlx_vae_chunk_size = gr.Slider(
                minimum=192,
                maximum=2048,
                value=_gpu_config.mlx_vae_chunk_size,
                step=64,
                label="MLX VAE Chunk Size",
                info="Larger = faster decode but more memory. Auto-detected based on your system.",
                elem_classes=["has-info-container"],
            )
    return {
        "inference_steps": inference_steps,
        "guidance_scale": guidance_scale,
        "infer_method": infer_method,
        "sampler_mode": sampler_mode,
        "velocity_norm_threshold": velocity_norm_threshold,
        "velocity_ema_factor": velocity_ema_factor,
        "dcw_enabled": dcw_enabled,
        "dcw_mode": dcw_mode,
        "dcw_scaler": dcw_scaler,
        "dcw_high_scaler": dcw_high_scaler,
        "dcw_wavelet": dcw_wavelet,
        "use_adg": use_adg,
        "shift": shift,
        "custom_timesteps": custom_timesteps,
        "cfg_interval_start": cfg_interval_start,
        "cfg_interval_end": cfg_interval_end,
        "seed": seed,
        "random_seed_checkbox": random_seed_checkbox,
        "mlx_vae_chunk_size": mlx_vae_chunk_size,
    }
