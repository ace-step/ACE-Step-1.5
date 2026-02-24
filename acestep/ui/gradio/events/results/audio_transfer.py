"""Audio transfer helpers: send-to-Remix/Repaint and audio-to-codes conversion.

Provides handlers that wire generated audio outputs back into the
generation UI for remix, repaint, and code extraction workflows.
"""
import gradio as gr

from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.events.generation_handlers import compute_mode_ui_updates


def send_audio_to_src_with_metadata(audio_file, lm_metadata):
    """Send generated audio file to ``src_audio`` input.

    Only sets the audio field; all other metadata fields are preserved via
    ``gr.skip()``.

    Args:
        audio_file: Audio file path.
        lm_metadata: LM metadata dict (unused, kept for API compat).

    Returns:
        10-tuple of Gradio updates.
    """
    if audio_file is None:
        return (gr.skip(),) * 10
    return (
        audio_file,
        gr.skip(),  # bpm
        gr.skip(),  # caption
        gr.skip(),  # lyrics
        gr.skip(),  # duration
        gr.skip(),  # key_scale
        gr.skip(),  # language
        gr.skip(),  # time_signature
        gr.skip(),  # is_format_caption
        gr.Accordion(open=True),  # audio_uploads_accordion
    )


def _extract_metadata_for_editing(lm_metadata, current_lyrics="", current_caption=""):
    """Extract lyrics and caption from *lm_metadata* with UI fallbacks.

    Args:
        lm_metadata: Metadata dictionary from LM generation (or ``None``).
        current_lyrics: Current lyrics value from the UI.
        current_caption: Current caption value from the UI.

    Returns:
        Tuple of ``(lyrics, caption)`` strings.
    """
    lyrics = current_lyrics or ""
    caption = current_caption or ""
    if lm_metadata and isinstance(lm_metadata, dict):
        lyrics = lm_metadata.get("lyrics", lyrics)
        caption = lm_metadata.get("caption", caption)
    return lyrics, caption


def send_audio_to_remix(audio_file, lm_metadata, current_lyrics, current_caption,
                        current_mode, llm_handler=None):
    """Send generated audio to ``src_audio`` and switch mode to Remix.

    Populates lyrics/caption from the generated audio and applies all
    Remix-mode UI updates atomically.

    Args:
        audio_file: Generated audio file path.
        lm_metadata: LM metadata dict (may be ``None``).
        current_lyrics: Current lyrics text in the UI.
        current_caption: Current caption text in the UI.
        current_mode: Currently active mode string.
        llm_handler: Optional LLM handler.

    Returns:
        48-tuple of Gradio updates (4 data + 44 mode-UI).
    """
    n_outputs = 48
    if audio_file is None:
        return (gr.skip(),) * n_outputs

    lyrics, caption = _extract_metadata_for_editing(lm_metadata, current_lyrics, current_caption)
    mode_updates = list(compute_mode_ui_updates("Remix", llm_handler, previous_mode=current_mode))
    mode_updates[19] = gr.update(value=caption, visible=True, interactive=True)
    mode_updates[20] = gr.update(value=lyrics, visible=True, interactive=True)

    return (audio_file, gr.update(value="Remix"), lyrics, caption, *mode_updates)


def send_audio_to_repaint(audio_file, lm_metadata, current_lyrics, current_caption,
                          current_mode, llm_handler=None):
    """Send generated audio to ``src_audio`` and switch mode to Repaint.

    Populates lyrics/caption from the generated audio and applies all
    Repaint-mode UI updates atomically.

    Args:
        audio_file: Generated audio file path.
        lm_metadata: LM metadata dict (may be ``None``).
        current_lyrics: Current lyrics text in the UI.
        current_caption: Current caption text in the UI.
        current_mode: Currently active mode string.
        llm_handler: Optional LLM handler.

    Returns:
        48-tuple of Gradio updates (4 data + 44 mode-UI).
    """
    n_outputs = 48
    if audio_file is None:
        return (gr.skip(),) * n_outputs

    lyrics, caption = _extract_metadata_for_editing(lm_metadata, current_lyrics, current_caption)
    mode_updates = list(compute_mode_ui_updates("Repaint", llm_handler, previous_mode=current_mode))
    mode_updates[19] = gr.update(value=caption, visible=True, interactive=True)
    mode_updates[20] = gr.update(value=lyrics, visible=True, interactive=True)

    return (audio_file, gr.update(value="Repaint"), lyrics, caption, *mode_updates)


def convert_result_audio_to_codes(dit_handler, generated_audio):
    """Convert a generated audio sample to LM audio codes.

    Args:
        dit_handler: DiT handler instance.
        generated_audio: File path to the generated audio.

    Returns:
        Tuple of ``(codes_display_update, details_accordion_update)``.
    """
    if not generated_audio:
        gr.Warning("No audio to convert.")
        return gr.skip(), gr.skip()
    if not dit_handler or dit_handler.model is None:
        gr.Warning(t("messages.service_not_initialized"))
        return gr.skip(), gr.skip()
    try:
        codes_string = dit_handler.convert_src_audio_to_codes(generated_audio)
        if not codes_string or codes_string.startswith("❌"):
            gr.Warning(f"Failed to convert audio to codes: {codes_string}")
            return gr.skip(), gr.skip()
        gr.Info("Audio converted to codes successfully.")
        return gr.update(value=codes_string), gr.update(open=True)
    except Exception as e:
        gr.Warning(f"Error converting audio to codes: {e}")
        return gr.skip(), gr.skip()
