"""Generate-row controls for the generation tab."""

from typing import Any

import gradio as gr

from acestep.ui.gradio.i18n import t


def _build_left_generate_toggles(
    lm_initialized: bool,
    service_mode: bool,
) -> tuple[gr.Checkbox, gr.Checkbox]:
    """Create the left-side runtime toggles shown next to the generate button.

    Args:
        lm_initialized: Whether LM is initialized, used to gate Think interactivity.
        service_mode: Whether UI is in service mode, used to gate toggle interactivity.

    Returns:
        The ``think_checkbox`` and ``auto_score`` controls in creation order.
    """

    with gr.Column(scale=1, variant="compact"):
        think_checkbox = gr.Checkbox(
            label=t("generation.think_label"),
            value=lm_initialized,
            scale=1,
            interactive=lm_initialized,
        )
        auto_score = gr.Checkbox(
            label=t("generation.auto_score_label"),
            value=False,
            scale=1,
            interactive=not service_mode,
        )
    return think_checkbox, auto_score


def _build_right_generate_toggles(service_mode: bool) -> tuple[gr.Checkbox, gr.Checkbox]:
    """Create the right-side runtime toggles shown next to the generate button.

    Args:
        service_mode: Whether UI is in service mode, used to gate toggle interactivity.

    Returns:
        The ``autogen_checkbox`` and ``auto_lrc`` controls in creation order.
    """

    with gr.Column(scale=1, variant="compact"):
        autogen_checkbox = gr.Checkbox(
            label=t("generation.autogen_label"),
            value=False,
            scale=1,
            interactive=not service_mode,
        )
        auto_lrc = gr.Checkbox(
            label=t("generation.auto_lrc_label"),
            value=False,
            scale=1,
            interactive=not service_mode,
        )
    return autogen_checkbox, auto_lrc


def build_generate_row_controls(
    service_pre_initialized: bool,
    init_params: dict[str, Any] | None,
    lm_initialized: bool,
    service_mode: bool,
) -> dict[str, Any]:
    """Compose generate-row controls from toggle helpers and the generate button.

    Args:
        service_pre_initialized: Whether startup params should prefill interactive defaults.
        init_params: Optional startup state containing generate-button enable state.
        lm_initialized: Whether LM is initialized, used to gate think-checkbox interactivity.
        service_mode: Whether the UI is running in service mode (disables some controls).

    Returns:
        A component map containing generate button, runtime toggles, and row container.
    """

    params = init_params or {}
    generate_btn_interactive = params.get("enable_generate", False) if service_pre_initialized else False
    with gr.Row(equal_height=True, visible=True) as generate_btn_row:
        think_checkbox, auto_score = _build_left_generate_toggles(
            lm_initialized=lm_initialized,
            service_mode=service_mode,
        )
        with gr.Column(scale=18):
            generate_btn = gr.Button(
                t("generation.generate_btn"),
                variant="primary",
                size="lg",
                interactive=generate_btn_interactive,
                elem_id="acestep-generate-btn",
            )
        autogen_checkbox, auto_lrc = _build_right_generate_toggles(service_mode=service_mode)
    return {
        "think_checkbox": think_checkbox,
        "auto_score": auto_score,
        "generate_btn": generate_btn,
        "generate_btn_row": generate_btn_row,
        "autogen_checkbox": autogen_checkbox,
        "auto_lrc": auto_lrc,
    }
