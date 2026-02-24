"""Small UI toggle/helper functions for generation handlers.

Contains functions for visibility toggles, auto-checkbox management,
instrumental handling, and other lightweight UI helpers.
"""

import gradio as gr
from typing import Optional

from acestep.ui.gradio.i18n import t
from .validation import _has_reference_audio


def update_negative_prompt_visibility(init_llm_checked):
    """Update negative prompt visibility: show if Initialize 5Hz LM checkbox is checked."""
    return gr.update(visible=init_llm_checked)


# Default "auto" values per field — these cause the model to auto-infer.
_AUTO_DEFAULTS = {
    "bpm": None,
    "key_scale": "",
    "time_signature": "",
    "vocal_language": "unknown",
    "audio_duration": -1,
}


def on_auto_checkbox_change(auto_checked: bool, field_name: str):
    """Toggle a field between auto (non-interactive, reset to default) and manual.

    Args:
        auto_checked: Whether the Auto checkbox is now checked.
        field_name: One of the keys in _AUTO_DEFAULTS.

    Returns:
        gr.update for the corresponding input component.
    """
    if auto_checked:
        return gr.update(value=_AUTO_DEFAULTS[field_name], interactive=False)
    return gr.update(interactive=True)


def reset_all_auto():
    """Reset all optional-parameter Auto checkboxes to checked.

    Returns:
        Tuple of 10 gr.update objects.
    """
    return (
        gr.update(value=True),
        gr.update(value=True),
        gr.update(value=True),
        gr.update(value=True),
        gr.update(value=True),
        gr.update(value=_AUTO_DEFAULTS["bpm"], interactive=False),
        gr.update(value=_AUTO_DEFAULTS["key_scale"], interactive=False),
        gr.update(value=_AUTO_DEFAULTS["time_signature"], interactive=False),
        gr.update(value=_AUTO_DEFAULTS["vocal_language"], interactive=False),
        gr.update(value=_AUTO_DEFAULTS["audio_duration"], interactive=False),
    )


def uncheck_auto_for_populated_fields(bpm, key_scale, time_signature, vocal_language, audio_duration):
    """Uncheck Auto checkboxes for fields that were populated by external events.

    Args:
        bpm: Current BPM value.
        key_scale: Current key scale value.
        time_signature: Current time signature value.
        vocal_language: Current vocal language value.
        audio_duration: Current audio duration value.

    Returns:
        Tuple of 10 gr.update objects.
    """
    bpm_has_value = bpm is not None and bpm != _AUTO_DEFAULTS["bpm"]
    key_has_value = bool(key_scale and key_scale != _AUTO_DEFAULTS["key_scale"])
    ts_has_value = bool(time_signature and time_signature != _AUTO_DEFAULTS["time_signature"])
    vl_has_value = vocal_language not in (None, "", _AUTO_DEFAULTS["vocal_language"])
    dur_has_value = (
        audio_duration is not None
        and audio_duration != _AUTO_DEFAULTS["audio_duration"]
        and audio_duration > 0
    )

    return (
        gr.update(value=not bpm_has_value),
        gr.update(value=not key_has_value),
        gr.update(value=not ts_has_value),
        gr.update(value=not vl_has_value),
        gr.update(value=not dur_has_value),
        gr.update(interactive=bpm_has_value),
        gr.update(interactive=key_has_value),
        gr.update(interactive=ts_has_value),
        gr.update(interactive=vl_has_value),
        gr.update(interactive=dur_has_value),
    )


def update_audio_cover_strength_visibility(task_type_value, init_llm_checked, reference_audio=None):
    """Update audio_cover_strength visibility and label."""
    has_reference = _has_reference_audio(reference_audio)
    is_visible = (task_type_value == "cover") or init_llm_checked or has_reference
    if task_type_value == "cover":
        label = t("generation.cover_strength_label")
        help_text = t("generation.cover_strength_info")
    elif init_llm_checked:
        label = t("generation.codes_strength_label")
        help_text = t("generation.codes_strength_info")
    elif has_reference:
        label = t("generation.similarity_denoise_label")
        help_text = t("generation.similarity_denoise_info")
    else:
        label = t("generation.cover_strength_label")
        help_text = t("generation.cover_strength_info")
    return gr.update(visible=is_visible, label=label, info=help_text, elem_classes=["has-info-container"])


def convert_src_audio_to_codes_wrapper(dit_handler, src_audio):
    """Wrapper for converting src audio to codes."""
    codes_string = dit_handler.convert_src_audio_to_codes(src_audio)
    return codes_string


def update_instruction_ui(
    dit_handler,
    task_type_value: str,
    track_name_value: Optional[str],
    complete_track_classes_value: list,
    init_llm_checked: bool = False,
    reference_audio=None,
) -> tuple:
    """Update instruction text based on task type.

    Visibility of track_name, complete_track_classes, and repainting_group
    is managed by compute_mode_ui_updates (via generation_mode.change).
    This function only regenerates the instruction string.
    """
    instruction = dit_handler.generate_instruction(
        task_type=task_type_value,
        track_name=track_name_value,
        complete_track_classes=complete_track_classes_value,
    )
    return instruction


def update_transcribe_button_text(audio_code_string):
    """Update the transcribe button text based on input content."""
    if not audio_code_string or not audio_code_string.strip():
        return gr.update(value="Generate Example")
    else:
        return gr.update(value="Transcribe")


def reset_format_caption_flag():
    """Reset is_format_caption to False when user manually edits caption/metadata."""
    return False


def update_audio_uploads_accordion(reference_audio, src_audio):
    """Update Audio Uploads accordion open state based on whether audio files are present."""
    has_audio = (reference_audio is not None) or (src_audio is not None)
    return gr.Accordion(open=has_audio)


def handle_instrumental_checkbox(instrumental_checked, current_lyrics, saved_lyrics):
    """Handle instrumental checkbox changes.

    When checked: save current lyrics to state, replace with [Instrumental].
    When unchecked: restore saved lyrics from state.

    Returns:
        Tuple of (lyrics, lyrics_before_instrumental_state).
    """
    if instrumental_checked:
        return "[Instrumental]", current_lyrics
    else:
        restored = saved_lyrics if saved_lyrics else ""
        return restored, ""


def handle_simple_instrumental_change(is_instrumental: bool):
    """Handle simple mode instrumental checkbox changes.

    Args:
        is_instrumental: Whether instrumental checkbox is checked.

    Returns:
        gr.update for simple_vocal_language dropdown.
    """
    if is_instrumental:
        return gr.update(value="unknown", interactive=False)
    else:
        return gr.update(interactive=True)


def update_audio_components_visibility(batch_size):
    """Show/hide individual audio components based on batch size (1-8).

    Row 1: Components 1-4 (batch_size 1-4)
    Row 2: Components 5-8 (batch_size 5-8)
    """
    if batch_size is None:
        batch_size = 1
    else:
        try:
            batch_size = min(max(int(batch_size), 1), 8)
        except (TypeError, ValueError):
            batch_size = 1

    updates_row1 = (
        gr.update(visible=True),
        gr.update(visible=batch_size >= 2),
        gr.update(visible=batch_size >= 3),
        gr.update(visible=batch_size >= 4),
    )

    show_row_5_8 = batch_size >= 5
    updates_row2 = (
        gr.update(visible=show_row_5_8),
        gr.update(visible=batch_size >= 5),
        gr.update(visible=batch_size >= 6),
        gr.update(visible=batch_size >= 7),
        gr.update(visible=batch_size >= 8),
    )

    return updates_row1 + updates_row2
