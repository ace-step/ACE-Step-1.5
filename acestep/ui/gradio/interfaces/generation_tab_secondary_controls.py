"""Secondary generation-tab controls (cover, custom prompt, repaint)."""

from typing import Any

import gradio as gr

from acestep.ui.gradio.help_content import create_help_button
from acestep.ui.gradio.i18n import t


def build_cover_strength_controls() -> dict[str, Any]:
    """Create code/remix strength controls used by non-simple generation modes.

    Args:
        None.

    Returns:
        A component map containing audio/code strength sliders and remix help group.
    """

    audio_cover_strength = gr.Slider(
        minimum=0.0,
        maximum=1.0,
        value=1.0,
        step=0.01,
        label=t("generation.codes_strength_label"),
        info=t("generation.codes_strength_info"),
        elem_classes=["has-info-container"],
        visible=True,
    )
    with gr.Group(visible=False) as remix_help_group:
        create_help_button("generation_remix")
        no_fsq = gr.Checkbox(
            label="no_fsq",
            value=False,
            info="Use source-audio latents directly instead of FSQ-quantized audio codes.",
        )
    cover_noise_strength = gr.Slider(
        minimum=0.0,
        maximum=1.0,
        value=0.0,
        step=0.01,
        label=t("generation.cover_noise_strength_label"),
        info=t("generation.cover_noise_strength_info"),
        elem_classes=["has-info-container"],
        visible=False,
    )
    return {
        "audio_cover_strength": audio_cover_strength,
        "remix_help_group": remix_help_group,
        "no_fsq": no_fsq,
        "cover_noise_strength": cover_noise_strength,
    }


def build_custom_mode_controls() -> dict[str, Any]:
    """Create custom-mode caption, lyrics, and reference-audio controls.

    Args:
        None.

    Returns:
        A component map containing custom-mode text/audio inputs and formatting actions.
    """

    with gr.Group(visible=True, elem_classes=["has-info-container"]) as custom_mode_group:
        create_help_button("generation_custom")
        with gr.Row(equal_height=True):
            with gr.Column(scale=2, min_width=200):
                reference_audio = gr.Audio(
                    label=t("generation.reference_audio"),
                    type="filepath",
                    show_label=True,
                )
            with gr.Column(scale=8):
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1):
                        captions = gr.Textbox(
                            label=t("generation.caption_label"),
                            placeholder=t("generation.caption_placeholder"),
                            lines=12,
                            max_lines=12,
                        )
                        with gr.Row(elem_classes="instrumental-row"):
                            format_caption_btn = gr.Button(
                                t("generation.format_caption_btn"),
                                variant="secondary",
                                size="sm",
                            )
                    with gr.Column(scale=1):
                        lyrics = gr.Textbox(
                            label=t("generation.lyrics_label"),
                            placeholder=t("generation.lyrics_placeholder"),
                            lines=12,
                            max_lines=12,
                        )
                        with gr.Row(elem_classes="instrumental-row"):
                            instrumental_checkbox = gr.Checkbox(
                                label=t("generation.instrumental_label"),
                                value=False,
                                scale=1,
                            )
                            format_lyrics_btn = gr.Button(
                                t("generation.format_lyrics_btn"),
                                variant="secondary",
                                size="sm",
                                scale=2,
                            )
            with gr.Column(scale=1, min_width=80, elem_classes="icon-btn-wrap"):
                sample_btn = gr.Button(t("generation.sample_btn"), variant="primary", size="lg")
    return {
        "custom_mode_group": custom_mode_group,
        "reference_audio": reference_audio,
        "captions": captions,
        "format_caption_btn": format_caption_btn,
        "lyrics": lyrics,
        "instrumental_checkbox": instrumental_checkbox,
        "format_lyrics_btn": format_lyrics_btn,
        "sample_btn": sample_btn,
    }


def build_flow_edit_morph_controls() -> dict[str, Any]:
    """Create flow-edit morph controls (visible only in Remix mode).

    Layered as an overlay on cover/cover-nofsq dispatch: when ``flow_edit_morph``
    is checked, the V_delta = V_tar - V_src integration kicks in.  The
    user's existing caption/lyrics serve as the *target*; the source
    fields below describe the *original* audio so V_src has meaningful
    paired conditioning.
    """

    with gr.Group(visible=False) as flow_edit_morph_group:
        create_help_button("generation_flow_edit_morph")
        flow_edit_morph = gr.Checkbox(
            label="Smooth morph (flow-edit) — API preview",
            value=False,
            info=(
                "Layer V_delta integration on top of remix.  v1 wiring is "
                "Python-API only (see scripts/flow_edit_overlay_smoke.py); "
                "UI run-handler threading lands in the follow-up PR."
            ),
        )
        with gr.Group(visible=False) as flow_edit_inner:
            flow_edit_source_caption = gr.Textbox(
                label="Source caption",
                placeholder="Describe the ORIGINAL audio (what V_src is conditioned on).",
                lines=2,
                max_lines=4,
            )
            flow_edit_source_lyrics = gr.Textbox(
                label="Source lyrics",
                placeholder="Original lyrics — leave the user's lyrics field for the target.",
                lines=4,
                max_lines=8,
            )
            with gr.Row():
                flow_edit_n_min = gr.Slider(
                    minimum=0.0, maximum=1.0, value=0.0, step=0.05,
                    label="n_min",
                    info="Edit window start (0=full schedule).",
                )
                flow_edit_n_max = gr.Slider(
                    minimum=0.0, maximum=1.0, value=1.0, step=0.05,
                    label="n_max",
                    info="Edit window end (1=full schedule).",
                )
                flow_edit_n_avg = gr.Slider(
                    minimum=1, maximum=8, value=1, step=1,
                    label="n_avg",
                    info="Monte-Carlo samples per step (higher = more stable, slower).",
                )
        flow_edit_morph.change(
            lambda v: gr.update(visible=bool(v)),
            inputs=[flow_edit_morph],
            outputs=[flow_edit_inner],
        )
    return {
        "flow_edit_morph_group": flow_edit_morph_group,
        "flow_edit_morph": flow_edit_morph,
        "flow_edit_inner": flow_edit_inner,
        "flow_edit_source_caption": flow_edit_source_caption,
        "flow_edit_source_lyrics": flow_edit_source_lyrics,
        "flow_edit_n_min": flow_edit_n_min,
        "flow_edit_n_max": flow_edit_n_max,
        "flow_edit_n_avg": flow_edit_n_avg,
    }


def build_repainting_controls() -> dict[str, Any]:
    """Create repainting range controls used by repaint/lego flows.

    Args:
        None.

    Returns:
        A component map containing repainting group, header, and start/end controls.
    """

    with gr.Group(visible=False) as repainting_group:
        create_help_button("generation_repaint")
        repainting_header_html = gr.HTML(f"<h5>{t('generation.repainting_controls')}</h5>")
        with gr.Row():
            repainting_start = gr.Number(
                label=t("generation.repainting_start"),
                value=0.0,
                step=0.1,
            )
            repainting_end = gr.Number(
                label=t("generation.repainting_end"),
                value=-1,
                minimum=-1,
                step=0.1,
            )
        with gr.Row():
            repaint_mode = gr.Dropdown(
                label="Repaint Mode",
                choices=["conservative", "balanced", "aggressive"],
                value="balanced",
                info="conservative=preserve source, aggressive=full regeneration",
            )
            repaint_strength = gr.Slider(
                label="Repaint Strength",
                minimum=0.0,
                maximum=1.0,
                step=0.05,
                value=0.5,
                info="0=conservative, 1=aggressive (balanced mode only)",
            )
        repaint_strength_memory = gr.State(value=0.5)
    return {
        "repainting_group": repainting_group,
        "repainting_header_html": repainting_header_html,
        "repainting_start": repainting_start,
        "repainting_end": repainting_end,
        "repaint_mode": repaint_mode,
        "repaint_strength": repaint_strength,
        "repaint_strength_memory": repaint_strength_memory,
    }


