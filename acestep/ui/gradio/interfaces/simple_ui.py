"""5-step simplified UI component builder with SVG icons and hamburger menu."""

from typing import Any

import gradio as gr

_STEP_LABELS = ["Describe Song", "Lyrics", "Remix", "Creating", "Done"]


def _step_indicator_html(current: int) -> str:
    """Generate inline SVG step indicator with connected dots and labels."""
    total = len(_STEP_LABELS)
    spacing = 120
    padding = 40
    width = padding * 2 + (total - 1) * spacing
    height = 70

    circles = []
    lines = []
    for i in range(total):
        cx = padding + i * spacing
        if i < current - 1:
            circles.append(
                f'<circle cx="{cx}" cy="28" r="9" fill="#667eea" stroke="none"/>'
                f'<path d="M{cx - 4} 28l{3} {3}l{6} -{6}" stroke="white" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        elif i == current - 1:
            circles.append(
                f'<circle cx="{cx}" cy="28" r="11" fill="#667eea" stroke="white" stroke-width="3" filter="url(#glow)"/>'
            )
        else:
            circles.append(
                f'<circle cx="{cx}" cy="28" r="9" fill="none" stroke="#d0d0d0" stroke-width="2"/>'
            )
        color = "#667eea" if i <= current - 1 else "#999"
        weight = "600" if i == current - 1 else "400"
        circles.append(
            f'<text x="{cx}" y="56" text-anchor="middle" font-size="11" font-weight="{weight}" fill="{color}">{_STEP_LABELS[i]}</text>'
        )

    for i in range(total - 1):
        x1 = padding + i * spacing + 9
        x2 = padding + (i + 1) * spacing - 9
        stroke = "#667eea" if i < current - 1 else "#e0e0e0"
        lines.append(f'<line x1="{x1}" y1="28" x2="{x2}" y2="28" stroke="{stroke}" stroke-width="2"/>')

    glow = (
        '<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="3" result="blur"/>'
        '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
        '</filter></defs>'
    )

    return f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="display:block;margin:0 auto;max-width:100%">{glow}{"".join(lines)}{"".join(circles)}</svg>'


def _build_header() -> str:
    """Return compact header HTML with hamburger icon."""
    return f'''
    <div class="simple-header">
        <div class="simple-header-content">
            <div class="simple-header-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="30" height="30">
                    <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
                </svg>
            </div>
            <div class="simple-header-text">
                <h2>Quick Music Generator</h2>
                <p>Turn your ideas into music in seconds</p>
            </div>
        </div>
    </div>
    '''


def _about_overlay_html() -> str:
    """Return the About modal content."""
    return f'''
    <div class="simple-about-icon">🎛️</div>
    <h2>ACE-Step V1.5 Playground 💡</h2>
    <p class="simple-about-subtitle">Pushing the Boundaries of Open-Source Music Generation</p>
    <p class="simple-about-desc">
        Generate high-quality music from text descriptions, remix existing tracks,
        and explore the future of AI-powered music creation.
    </p>
    '''


def _build_step_describe() -> tuple[gr.Column, dict[str, Any]]:
    """Build Step 1: Describe your song."""
    with gr.Column(visible=True, elem_id="simple-step-1", elem_classes="simple-step") as col:
        simple_song_style = gr.Textbox(
            label="What kind of music would you like to create?",
            placeholder="e.g. A happy pop song with piano and drums",
            lines=3,
            elem_classes=["simple-input"],
        )
        with gr.Row(elem_classes="simple-nav-row"):
            simple_random_btn = gr.Button(
                " Surprise Me",
                variant="secondary",
                size="sm",
                elem_classes=["simple-random-btn"],
            )
            simple_step1_continue_btn = gr.Button(
                "Continue  ",
                variant="primary",
                size="sm",
                elem_classes=["simple-continue-btn"],
            )
    return col, {
        "simple_step_1": col,
        "simple_song_style": simple_song_style,
        "simple_random_btn": simple_random_btn,
        "simple_step1_continue_btn": simple_step1_continue_btn,
    }


def _build_step_lyrics() -> tuple[gr.Column, dict[str, Any]]:
    """Build Step 2: Lyrics."""
    with gr.Column(visible=False, elem_id="simple-step-2", elem_classes="simple-step") as col:
        simple_lyrics = gr.Textbox(
            label="Add your own lyrics (optional)",
            placeholder="Enter your lyrics here, or leave blank for AI-generated lyrics",
            lines=8,
            elem_classes=["simple-input", "simple-lyrics"],
        )
        simple_instrumental = gr.Checkbox(
            label="Instrumental only",
            info="Create music without vocals or lyrics",
            value=False,
            elem_classes=["simple-instrumental"],
        )
        with gr.Row(elem_classes="simple-nav-row"):
            simple_step2_back_btn = gr.Button(
                "  Back",
                variant="secondary",
                size="sm",
                elem_classes=["simple-back-btn"],
            )
            simple_step2_continue_btn = gr.Button(
                "Continue  ",
                variant="primary",
                size="sm",
                elem_classes=["simple-continue-btn"],
            )
    return col, {
        "simple_step_2": col,
        "simple_lyrics": simple_lyrics,
        "simple_instrumental": simple_instrumental,
        "simple_step2_back_btn": simple_step2_back_btn,
        "simple_step2_continue_btn": simple_step2_continue_btn,
    }


def _build_step_remix() -> tuple[gr.Column, dict[str, Any]]:
    """Build Step 3: Remix / Create."""
    with gr.Column(visible=False, elem_id="simple-step-3", elem_classes="simple-step") as col:
        gr.HTML(
            '<div class="simple-upload-label">Upload a song to remix? (optional)</div>',
            elem_classes=["simple-upload-label-wrap"],
        )
        simple_src_audio = gr.Audio(
            label="Click to upload, or drag a file here",
            type="filepath",
            sources=["upload"],
            elem_classes=["simple-upload-area"],
        )
        with gr.Row(elem_classes=["simple-nav-row", "simple-remix-nav"]):
            simple_step3_back_btn = gr.Button(
                "  Back",
                variant="secondary",
                size="sm",
                elem_classes=["simple-back-btn"],
            )
            simple_create_btn = gr.Button(
                "Loading models…",
                variant="primary",
                size="sm",
                interactive=False,
                elem_id="simple-create-btn",
                elem_classes=["simple-create-btn"],
            )
    return col, {
        "simple_step_3": col,
        "simple_src_audio": simple_src_audio,
        "simple_step3_back_btn": simple_step3_back_btn,
        "simple_create_btn": simple_create_btn,
    }


def _build_step_creating() -> tuple[gr.Column, dict[str, Any]]:
    """Build Step 4: Creating..."""
    with gr.Column(visible=False, elem_id="simple-step-4", elem_classes="simple-step") as col:
        gr.HTML(
            '<div class="simple-creating-icon">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#667eea" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="48" height="48">'
            '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>'
            '</svg></div>'
        )
        gr.HTML('<div class="simple-creating-title">Creating your music...</div>')
        gr.HTML(
            '<div class="simple-progress-track">'
            '<div class="simple-progress-bar" id="simple-progress-bar"></div>'
            '</div>'
        )
        simple_progress_text = gr.HTML(
            value='<div class="simple-progress-status">Preparing...</div>',
            elem_classes=["simple-progress-status"],
        )
    return col, {
        "simple_step_4": col,
        "simple_progress_text": simple_progress_text,
    }


def _build_step_results() -> tuple[gr.Column, dict[str, Any]]:
    """Build Step 5: Results."""
    with gr.Column(visible=False, elem_id="simple-step-5", elem_classes="simple-step") as col:
        gr.HTML(
            '<div class="simple-divider">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#667eea" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18">'
            '<path d="M12 3l1.91 5.87L20 9.73l-4.88 4.12 1.38 6.15L12 16.5l-4.5 3.5 1.38-6.15L4 9.73l6.09-.86L12 3z"/>'
            '</svg>'
            '<span>Your Music</span>'
            '</div>',
            elem_classes=["simple-divider-wrap"],
        )
        with gr.Row(elem_classes="simple-results-row"):
            with gr.Column(scale=1, elem_classes="simple-result-col") as simple_result_col_1:
                gr.HTML(
                    '<div class="simple-best-badge">'
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="none" width="12" height="12">'
                    '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'
                    '</svg> Best Pick'
                    '</div>'
                )
                simple_generated_audio_1 = gr.Audio(
                    label="",
                    type="filepath",
                    interactive=False,
                    editable=False,
                    show_label=False,
                    container=False,
                    buttons=[],
                    elem_classes=["simple-audio"],
                )
                with gr.Row(elem_classes="simple-meta-row"):
                    simple_metadata_1 = gr.HTML(
                        value="",
                        elem_classes=["simple-metadata"],
                    )
                    simple_save_btn_1 = gr.Button(
                        "",
                        size="sm",
                        elem_classes=["simple-save-btn"],
                    )
            with gr.Column(scale=1, elem_classes="simple-result-col") as simple_result_col_2:
                gr.HTML(
                    '<div class="simple-best-badge simple-best-badge-placeholder">'
                    'Best Pick</div>'
                )
                simple_generated_audio_2 = gr.Audio(
                    label="",
                    type="filepath",
                    interactive=False,
                    editable=False,
                    show_label=False,
                    container=False,
                    buttons=[],
                    elem_classes=["simple-audio"],
                )
                with gr.Row(elem_classes="simple-meta-row"):
                    simple_metadata_2 = gr.HTML(
                        value="",
                        elem_classes=["simple-metadata"],
                    )
                    simple_save_btn_2 = gr.Button(
                        "",
                        size="sm",
                        elem_classes=["simple-save-btn"],
                    )
        simple_gen_info = gr.HTML(
            value="",
            elem_classes=["simple-gen-info"],
        )
        with gr.Row(elem_classes="simple-footer-row"):
            simple_retry_btn = gr.Button(
                " Try Different Style",
                variant="secondary",
                size="sm",
                elem_classes=["simple-retry-btn"],
            )
            simple_new_btn = gr.Button(
                " Create New Song",
                variant="secondary",
                size="sm",
                elem_classes=["simple-new-btn"],
            )
    return col, {
        "simple_step_5": col,
        "simple_generated_audio_1": simple_generated_audio_1,
        "simple_generated_audio_2": simple_generated_audio_2,
        "simple_result_col_1": simple_result_col_1,
        "simple_result_col_2": simple_result_col_2,
        "simple_metadata_1": simple_metadata_1,
        "simple_metadata_2": simple_metadata_2,
        "simple_save_btn_1": simple_save_btn_1,
        "simple_save_btn_2": simple_save_btn_2,
        "simple_gen_info": simple_gen_info,
        "simple_retry_btn": simple_retry_btn,
        "simple_new_btn": simple_new_btn,
    }


def build_simple_ui() -> dict[str, Any]:
    """Build the complete stepped-flow simplified UI.

    Returns:
        A merged component map for all simple-UI controls.
    """
    with gr.Column(visible=True, elem_id="simple-ui-column") as simple_column:
        gr.HTML(_build_header())

        # ── Hamburger toggle button ──
        simple_hamburger_btn = gr.Button(
            "Menu",
            elem_classes=["simple-hamburger-btn"],
        )

        # ── Dropdown menu (hidden by default) ──
        with gr.Group(visible=False, elem_classes="simple-hamburger-menu") as simple_hamburger_menu:
            simple_about_btn = gr.Button(
                "About",
                elem_classes=["simple-menu-item", "simple-menu-about"],
            )
            simple_help_btn = gr.Button(
                "Help",
                elem_classes=["simple-menu-item", "simple-menu-help"],
            )
            simple_advanced_btn = gr.Button(
                "Advanced Mode",
                elem_classes=["simple-menu-item", "simple-menu-advanced"],
            )

        # ── About overlay (hidden by default) ──
        with gr.Group(
            visible=False,
            elem_classes=["simple-about-overlay", "simple-about-backdrop"],
        ) as simple_about_overlay:
            with gr.Column(elem_classes=["simple-about-modal"]):
                simple_about_close_btn = gr.Button(
                    "×", elem_classes=["simple-about-close"], size="sm"
                )
                gr.HTML(value=_about_overlay_html())

        simple_step_indicator = gr.HTML(
            value=_step_indicator_html(1),
            elem_classes=["simple-step-indicator"],
        )
        _, step1 = _build_step_describe()
        _, step2 = _build_step_lyrics()
        _, step3 = _build_step_remix()
        _, step4 = _build_step_creating()
        _, step5 = _build_step_results()
        simple_state_current_step = gr.State(value=1)
        simple_state_song_style = gr.State(value="")
        simple_state_lyrics = gr.State(value="")
        simple_state_audio = gr.State(value=None)
        simple_hamburger_state = gr.State(value=False)

    result: dict[str, Any] = {
        "simple_column": simple_column,
        "simple_hamburger_btn": simple_hamburger_btn,
        "simple_hamburger_menu": simple_hamburger_menu,
        "simple_hamburger_state": simple_hamburger_state,
        "simple_about_btn": simple_about_btn,
        "simple_help_btn": simple_help_btn,
        "simple_advanced_btn": simple_advanced_btn,
        "simple_about_overlay": simple_about_overlay,
        "simple_about_close_btn": simple_about_close_btn,
        "simple_step_indicator": simple_step_indicator,
        "simple_state_current_step": simple_state_current_step,
        "simple_state_song_style": simple_state_song_style,
        "simple_state_lyrics": simple_state_lyrics,
        "simple_state_audio": simple_state_audio,
    }
    for d in (step1, step2, step3, step4, step5):
        result.update(d)
    return result
