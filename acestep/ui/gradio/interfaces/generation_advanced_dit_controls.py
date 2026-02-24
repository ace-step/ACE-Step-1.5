"""DiT diffusion controls for generation advanced settings."""

from typing import Any

import gradio as gr

from acestep.ui.gradio.help_content import create_help_button
from acestep.ui.gradio.i18n import t


def build_dit_controls(ui_config: dict[str, Any]) -> dict[str, Any]:
    """Create DiT diffusion controls for advanced settings.

    Args:
        ui_config: Visibility/range/value configuration returned by generation handler UI config logic.

    Returns:
        A component map containing DiT sampling, CFG interval, ADG, shift, and seed controls.
    """

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
                visible=ui_config["cfg_interval_start_visible"],
            )
            cfg_interval_end = gr.Slider(
                minimum=0.0,
                maximum=1.0,
                value=1.0,
                step=0.01,
                label=t("generation.cfg_interval_end"),
                visible=ui_config["cfg_interval_end_visible"],
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
    return {
        "inference_steps": inference_steps,
        "guidance_scale": guidance_scale,
        "infer_method": infer_method,
        "use_adg": use_adg,
        "shift": shift,
        "custom_timesteps": custom_timesteps,
        "cfg_interval_start": cfg_interval_start,
        "cfg_interval_end": cfg_interval_end,
        "seed": seed,
        "random_seed_checkbox": random_seed_checkbox,
    }
