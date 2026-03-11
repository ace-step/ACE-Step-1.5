"""Helper functions for generation mode UI update construction."""

import gradio as gr

from acestep.ui.gradio.i18n import t


def _compute_field_updates_for_mode(
    is_extract: bool,
    is_lego: bool,
    not_simple: bool,
    leaving_extract_or_lego: bool,
):
    """Compute gr.update() for captions, lyrics, bpm, and key_scale."""
    if is_extract:
        return (
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            gr.update(value=None, interactive=False, visible=False),
            gr.update(value="", interactive=False, visible=False),
        )
    if is_lego:
        return (
            gr.update(visible=True, interactive=True),
            gr.update(visible=True, interactive=True),
            gr.update(value=None, interactive=False, visible=False),
            gr.update(value="", interactive=False, visible=False),
        )
    if not_simple:
        if leaving_extract_or_lego:
            return (
                gr.update(value="", visible=True, interactive=True),
                gr.update(value="", visible=True, interactive=True),
                gr.update(value=None, visible=True, interactive=False),
                gr.update(value="", visible=True, interactive=False),
            )
        return (
            gr.update(visible=True, interactive=True),
            gr.update(visible=True, interactive=True),
            gr.update(visible=True),
            gr.update(visible=True),
        )
    if leaving_extract_or_lego:
        return (
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=None),
            gr.update(value=""),
        )
    return gr.update(), gr.update(), gr.update(), gr.update()


def _compute_meta_updates_for_mode(
    is_extract: bool,
    is_lego: bool,
    not_simple: bool,
    leaving_extract_or_lego: bool,
):
    """Compute gr.update() for time_signature, vocal_language, audio_duration."""
    if is_extract or is_lego:
        return (
            gr.update(value="", interactive=False, visible=False),
            gr.update(value="unknown", interactive=False, visible=False),
            gr.update(value=-1, interactive=False, visible=False),
        )
    if not_simple:
        if leaving_extract_or_lego:
            return (
                gr.update(value="", visible=True, interactive=False),
                gr.update(value="en", visible=True, interactive=False),
                gr.update(value=-1, visible=True, interactive=False),
            )
        return (
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=True),
        )
    if leaving_extract_or_lego:
        return (
            gr.update(value=""),
            gr.update(value="en"),
            gr.update(value=-1),
        )
    return gr.update(), gr.update(), gr.update()


def _compute_automation_updates(is_extract: bool, is_lego: bool, not_simple: bool):
    """Compute gr.update() for auto_score, autogen, auto_lrc, and analyze_btn."""
    if is_extract or is_lego:
        return (
            gr.update(visible=False, value=False, interactive=False),
            gr.update(visible=False, value=False, interactive=False),
            gr.update(visible=False, value=False, interactive=False),
            gr.update(visible=False),
        )
    if not_simple:
        return (
            gr.update(visible=True, interactive=True),
            gr.update(visible=True, interactive=True),
            gr.update(visible=True, interactive=True),
            gr.update(visible=True),
        )
    return gr.update(), gr.update(), gr.update(), gr.update()


def _compute_repainting_labels(is_lego: bool, is_repaint: bool):
    """Compute gr.update() for repainting header, start, and end labels."""
    if is_lego:
        return (
            gr.update(value=f"<h5>{t('generation.stem_area_controls')}</h5>"),
            gr.update(label=t("generation.stem_start")),
            gr.update(label=t("generation.stem_end")),
        )
    if is_repaint:
        return (
            gr.update(value=f"<h5>{t('generation.repainting_controls')}</h5>"),
            gr.update(label=t("generation.repainting_start")),
            gr.update(label=t("generation.repainting_end")),
        )
    return gr.update(), gr.update(), gr.update()

