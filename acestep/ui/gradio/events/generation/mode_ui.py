"""Generation-mode UI update orchestration for Gradio handlers."""

import gradio as gr
from loguru import logger

from acestep.constants import MODE_TO_TASK_TYPE
from acestep.ui.gradio.i18n import t
from .mode_ui_helpers import (
    _compute_automation_updates,
    _compute_field_updates_for_mode,
    _compute_meta_updates_for_mode,
    _compute_repainting_labels,
)


def compute_mode_ui_updates(mode: str, llm_handler=None, previous_mode: str = "Custom"):
    """Return the 44-output mode-switch update tuple for generation UI."""
    task_type = MODE_TO_TASK_TYPE.get(mode, "text2music")

    is_simple = (mode == "Simple")
    is_custom = (mode == "Custom")
    is_cover = (mode == "Remix")
    is_repaint = (mode == "Repaint")
    is_extract = (mode == "Extract")
    is_lego = (mode == "Lego")
    is_complete = (mode == "Complete")
    leaving_extract_or_lego = previous_mode in ("Extract", "Lego")
    not_simple = not is_simple

    # --- Visibility rules ---
    show_simple = is_simple
    show_custom_group = not_simple and not is_extract
    show_generate_row = not_simple
    generate_interactive = not_simple
    show_src_audio = is_cover or is_repaint or is_extract or is_lego or is_complete
    show_optional = not_simple and not is_extract and not is_lego
    show_repainting = is_repaint or is_lego
    show_audio_codes = is_custom
    show_track_name = is_lego or is_extract
    show_complete_classes = is_complete

    # Audio cover strength
    show_strength = not is_simple and not is_repaint and not is_extract and not is_lego
    if is_cover:
        strength_label = t("generation.remix_strength_label")
        strength_info = t("generation.remix_strength_info")
    elif is_custom:
        strength_label = t("generation.codes_strength_label")
        strength_info = t("generation.codes_strength_info")
    else:
        strength_label = t("generation.cover_strength_label")
        strength_info = t("generation.cover_strength_info")
    strength_update = gr.update(visible=show_strength, label=strength_label, info=strength_info)
    cover_noise_update = gr.update(visible=is_cover)

    # Think checkbox
    lm_initialized = llm_handler.llm_initialized if llm_handler else False
    if is_extract or is_lego or is_cover or is_repaint:
        think_update = gr.update(interactive=False, value=False, visible=not (is_extract or is_lego))
    elif not lm_initialized:
        think_update = gr.update(interactive=False, value=False, visible=True)
    else:
        # Restore thinking to True when entering a mode where it is supported
        # (e.g. Custom after returning from Remix/Repaint where it was forced off).
        think_update = gr.update(interactive=True, visible=True, value=True)

    mode_descriptions = {
        "Simple": t("generation.mode_info_simple"),
        "Custom": t("generation.mode_info_custom"),
        "Remix": t("generation.mode_info_remix"),
        "Repaint": t("generation.mode_info_repaint"),
        "Extract": t("generation.mode_info_extract"),
        "Lego": t("generation.mode_info_lego"),
        "Complete": t("generation.mode_info_complete"),
    }
    mode_help_text = mode_descriptions.get(mode, "")
    show_results = not_simple

    # Generate button label
    if is_extract:
        generate_btn_update = gr.update(interactive=generate_interactive, value=t("generation.extract_stem_btn"))
    elif is_lego:
        generate_btn_update = gr.update(interactive=generate_interactive, value=t("generation.add_stem_btn"))
    else:
        generate_btn_update = gr.update(interactive=generate_interactive, value=t("generation.generate_btn"))

    # --- Extract/Lego-mode outputs (indices 19-29) ---
    captions_update, lyrics_update, bpm_update, key_scale_update = _compute_field_updates_for_mode(
        is_extract, is_lego, not_simple, leaving_extract_or_lego,
    )
    time_signature_update, vocal_language_update, audio_duration_update = _compute_meta_updates_for_mode(
        is_extract, is_lego, not_simple, leaving_extract_or_lego,
    )
    auto_score_update, autogen_update, auto_lrc_update, analyze_btn_update = _compute_automation_updates(
        is_extract, is_lego, not_simple,
    )

    # --- Dynamic repainting / stem area labels (indices 30-32) ---
    repainting_header_update, repainting_start_update, repainting_end_update = _compute_repainting_labels(
        is_lego, is_repaint,
    )

    # --- Auto checkbox updates (indices 37-41) ---
    if is_extract or is_lego or leaving_extract_or_lego:
        auto_bpm_update = gr.update(value=True)
        auto_key_update = gr.update(value=True)
        auto_timesig_update = gr.update(value=True)
        auto_vocal_lang_update = gr.update(value=True)
        auto_duration_update = gr.update(value=True)
    else:
        auto_bpm_update = gr.update()
        auto_key_update = gr.update()
        auto_timesig_update = gr.update()
        auto_vocal_lang_update = gr.update()
        auto_duration_update = gr.update()

    # Clear stale audio codes when leaving/returning from source-audio modes.
    _prev_has_src_audio = previous_mode in ("Remix", "Repaint", "Extract", "Lego", "Complete")
    if is_custom:
        if _prev_has_src_audio:
            audio_codes_update = gr.update(value="", visible=True)
        else:
            audio_codes_update = gr.update(visible=True)
    else:
        audio_codes_update = gr.update(value="", visible=False)

    # Clear src_audio when entering a mode that doesn't use it
    # (Custom, Simple) to prevent stale audio from leaking.
    if show_src_audio:
        src_audio_update = gr.update()
    else:
        src_audio_update = gr.update(value=None)

    return (
        gr.update(visible=show_simple),                    # 0: simple_mode_group
        gr.update(visible=show_custom_group),              # 1: custom_mode_group
        generate_btn_update,                               # 2: generate_btn
        False,                                             # 3: simple_sample_created
        gr.Accordion(visible=show_optional, open=False),   # 4: optional_params_accordion
        gr.update(value=task_type, elem_classes=["has-info-container"]),  # 5: task_type
        gr.update(visible=show_src_audio),                 # 6: src_audio_row
        gr.update(visible=show_repainting),                # 7: repainting_group
        gr.update(visible=show_audio_codes),               # 8: text2music_audio_codes_group
        gr.update(visible=show_track_name),                # 9: track_name
        gr.update(visible=show_complete_classes),           # 10: complete_track_classes
        gr.update(visible=show_generate_row),              # 11: generate_btn_row
        gr.update(info=mode_help_text, elem_classes=["has-info-container"]),  # 12: generation_mode
        gr.update(visible=show_results),                   # 13: results_wrapper
        think_update,                                      # 14: think_checkbox
        gr.update(visible=not_simple),                     # 15: load_file_col
        gr.update(visible=not_simple),                     # 16: load_file
        strength_update,                                   # 17: audio_cover_strength
        cover_noise_update,                                # 18: cover_noise_strength
        captions_update,                                   # 19: captions
        lyrics_update,                                     # 20: lyrics
        bpm_update,                                        # 21: bpm
        key_scale_update,                                  # 22: key_scale
        time_signature_update,                             # 23: time_signature
        vocal_language_update,                             # 24: vocal_language
        audio_duration_update,                             # 25: audio_duration
        auto_score_update,                                 # 26: auto_score
        autogen_update,                                    # 27: autogen_checkbox
        auto_lrc_update,                                   # 28: auto_lrc
        analyze_btn_update,                                # 29: analyze_btn
        repainting_header_update,                          # 30: repainting_header_html
        repainting_start_update,                           # 31: repainting_start
        repainting_end_update,                             # 32: repainting_end
        mode,                                              # 33: previous_generation_mode
        gr.update(visible=is_cover),                       # 34: remix_help_group
        gr.update(visible=(is_extract or is_lego)),        # 35: extract_help_group
        gr.update(visible=is_complete),                    # 36: complete_help_group
        auto_bpm_update,                                   # 37: bpm_auto
        auto_key_update,                                   # 38: key_auto
        auto_timesig_update,                               # 39: timesig_auto
        auto_vocal_lang_update,                            # 40: vocal_lang_auto
        auto_duration_update,                              # 41: duration_auto
        audio_codes_update,                                # 42: text2music_audio_code_string
        src_audio_update,                                  # 43: src_audio
    )


def handle_generation_mode_change(mode: str, previous_mode: str, llm_handler=None):
    """Delegate generation-mode change handling to compute_mode_ui_updates."""
    return compute_mode_ui_updates(mode, llm_handler, previous_mode=previous_mode)


def handle_extract_track_name_change(track_name_value: str, mode: str):
    """Auto-fill caption with the selected track name in Extract mode."""
    if mode == "Extract" and track_name_value:
        return gr.update(value=track_name_value)
    return gr.update()


def handle_extract_src_audio_change(src_audio_path, mode: str):
    """Auto-fill audio duration from source audio in Extract/Lego mode."""
    if mode not in ("Extract", "Lego") or not src_audio_path:
        return gr.update()
    try:
        # Late import avoids loading training audio helpers unless this path is used.
        from acestep.training.dataset_builder_modules.audio_io import get_audio_duration
        duration = get_audio_duration(src_audio_path)
        if duration and duration > 0:
            return gr.update(value=float(duration))
    except Exception as e:
        logger.warning(f"Failed to get audio duration for {mode} mode: {e}")
    return gr.update()
