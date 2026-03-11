"""Audio-code analysis and transcription actions for generation handlers.

This module contains source-audio analysis and audio-code transcription
entry points used by the Gradio generation UI.
"""

import gradio as gr

from acestep.inference import understand_music
from acestep.ui.gradio.i18n import t

from .validation import _contains_audio_code_tokens, clamp_duration_to_gpu_limit


def analyze_src_audio(
    dit_handler,
    llm_handler,
    src_audio,
    constrained_decoding_debug: bool = False,
):
    """Analyze source audio and optionally transcribe generated audio codes.

    Args:
        dit_handler: DiT handler instance.
        llm_handler: LLM handler instance.
        src_audio: Path to source audio file.
        constrained_decoding_debug: Whether constrained-decoding debug logs are enabled.

    Returns:
        Tuple of ``(audio_codes, status, caption, lyrics, bpm, duration,
        keyscale, language, timesignature, is_format_caption)``.
    """
    error_tuple = ("", "", "", "", None, None, "", "", "", False)

    if not src_audio:
        gr.Warning(t("messages.no_source_audio"))
        return error_tuple

    if dit_handler.model is None:
        gr.Warning(t("messages.model_not_initialized"))
        return error_tuple

    try:
        codes_string = dit_handler.convert_src_audio_to_codes(src_audio)
    except Exception as exc:
        gr.Warning(t("messages.audio_conversion_failed", error=str(exc)))
        return error_tuple

    if not codes_string or not _contains_audio_code_tokens(codes_string):
        gr.Warning(t("messages.no_audio_codes_generated"))
        return (
            codes_string or "",
            t("messages.no_audio_codes_generated"),
            "",
            "",
            None,
            None,
            "",
            "",
            "",
            False,
        )

    if not llm_handler.llm_initialized:
        return (
            codes_string,
            t("messages.codes_ready_no_lm"),
            "",
            "",
            None,
            None,
            "",
            "",
            "",
            False,
        )

    result = understand_music(
        llm_handler=llm_handler,
        audio_codes=codes_string,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        return (
            codes_string,
            result.status_message,
            "",
            "",
            None,
            None,
            "",
            "",
            "",
            False,
        )

    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    return (
        codes_string,
        result.status_message,
        result.caption,
        result.lyrics,
        result.bpm,
        clamped_duration,
        result.keyscale,
        result.language,
        result.timesignature,
        True,
    )


def transcribe_audio_codes(llm_handler, audio_code_string, constrained_decoding_debug: bool):
    """Transcribe serialized audio codes into metadata fields via the LLM.

    Args:
        llm_handler: LLM handler instance.
        audio_code_string: Serialized audio-code tokens.
        constrained_decoding_debug: Whether constrained-decoding debug logs are enabled.

    Returns:
        Tuple of ``(status, caption, lyrics, bpm, duration, keyscale,
        language, timesignature, is_format_caption)``.
    """
    result = understand_music(
        llm_handler=llm_handler,
        audio_codes=audio_code_string,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        if result.error == "LLM not initialized":
            return t("messages.lm_not_initialized"), "", "", None, None, "", "", "", False
        return result.status_message, "", "", None, None, "", "", "", False

    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    return (
        result.status_message,
        result.caption,
        result.lyrics,
        result.bpm,
        clamped_duration,
        result.keyscale,
        result.language,
        result.timesignature,
        True,
    )
