"""LLM-powered actions for generation handlers.

Contains functions that interact with the LLM handler: creating samples,
formatting captions/lyrics, transcribing audio codes, and analyzing
source audio.
"""

import re
import gradio as gr

from acestep.ui.gradio.i18n import t
from acestep.inference import understand_music, create_sample, format_sample
from .validation import clamp_duration_to_gpu_limit, _contains_audio_code_tokens


def analyze_src_audio(dit_handler, llm_handler, src_audio, constrained_decoding_debug=False):
    """Analyze source audio: convert to codes, then transcribe to caption/lyrics/metas.

    Args:
        dit_handler: DiT handler instance.
        llm_handler: LLM handler instance.
        src_audio: Path to source audio file.
        constrained_decoding_debug: Whether to enable debug logging.

    Returns:
        Tuple of (audio_codes, status, caption, lyrics, bpm, duration,
        keyscale, language, timesignature, is_format_caption).
    """
    error_tuple = ("", "", "", "", None, None, "", "", "", False)

    if not src_audio:
        gr.Warning(t("messages.no_source_audio"))
        return error_tuple

    if dit_handler.model is None:
        gr.Warning(t("messages.model_not_initialized"))
        return error_tuple

    # Step 1: Convert audio to codes
    try:
        codes_string = dit_handler.convert_src_audio_to_codes(src_audio)
    except Exception as e:
        gr.Warning(t("messages.audio_conversion_failed", error=str(e)))
        return error_tuple

    if not codes_string or not _contains_audio_code_tokens(codes_string):
        gr.Warning(t("messages.no_audio_codes_generated"))
        return (codes_string or "", t("messages.no_audio_codes_generated"),
                "", "", None, None, "", "", "", False)

    # Step 2: Transcribe codes to metadata (if LLM available)
    if not llm_handler.llm_initialized:
        return (codes_string, t("messages.codes_ready_no_lm"),
                "", "", None, None, "", "", "", False)

    result = understand_music(
        llm_handler=llm_handler,
        audio_codes=codes_string,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        return (codes_string, result.status_message,
                "", "", None, None, "", "", "", False)

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


def transcribe_audio_codes(llm_handler, audio_code_string, constrained_decoding_debug):
    """Transcribe audio codes to metadata using LLM understanding.

    If audio_code_string is empty, generate a sample example instead.

    Args:
        llm_handler: LLM handler instance.
        audio_code_string: String containing audio codes.
        constrained_decoding_debug: Whether to enable debug logging.

    Returns:
        Tuple of (status, caption, lyrics, bpm, duration, keyscale,
        language, timesignature, is_format_caption).
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


def handle_create_sample(
    llm_handler,
    query: str,
    instrumental: bool,
    vocal_language: str,
    lm_temperature: float,
    lm_top_k: int,
    lm_top_p: float,
    constrained_decoding_debug: bool = False,
):
    """Handle the Create Sample button click in Simple mode.

    Args:
        llm_handler: LLM handler instance.
        query: User's natural language music description.
        instrumental: Whether to generate instrumental music.
        vocal_language: Preferred vocal language.
        lm_temperature: LLM temperature.
        lm_top_k: LLM top-k sampling.
        lm_top_p: LLM top-p sampling.
        constrained_decoding_debug: Whether to enable debug logging.

    Returns:
        Tuple of 15 updates for UI components.
    """
    if not llm_handler.llm_initialized:
        gr.Warning(t("messages.lm_not_initialized"))
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(interactive=False), False,
            gr.update(), gr.update(),
            t("messages.lm_not_initialized"), gr.update(),
        )

    top_k_value = None if not lm_top_k or lm_top_k == 0 else int(lm_top_k)
    top_p_value = None if not lm_top_p or lm_top_p >= 1.0 else lm_top_p

    result = create_sample(
        llm_handler=llm_handler,
        query=query,
        instrumental=instrumental,
        vocal_language=vocal_language,
        temperature=lm_temperature,
        top_k=top_k_value,
        top_p=top_p_value,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        gr.Warning(result.status_message or t("messages.sample_creation_failed"))
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(interactive=False), False,
            gr.update(), gr.update(),
            result.status_message or t("messages.sample_creation_failed"), gr.update(),
        )

    gr.Info(t("messages.sample_created"))
    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    audio_duration_value = clamped_duration if clamped_duration and clamped_duration > 0 else -1

    return (
        result.caption,
        result.lyrics,
        result.bpm,
        audio_duration_value,
        result.keyscale,
        result.language,
        result.language,
        result.timesignature,
        result.instrumental,
        gr.update(interactive=True),
        True,
        True,
        True,
        result.status_message,
        gr.update(value="Custom"),
    )


def _build_user_metadata(bpm, audio_duration, key_scale, time_signature):
    """Build user_metadata dict from provided values for constrained decoding."""
    user_metadata = {}
    if bpm is not None and bpm > 0:
        user_metadata['bpm'] = int(bpm)
    if audio_duration is not None and float(audio_duration) > 0:
        user_metadata['duration'] = int(audio_duration)
    if key_scale and key_scale.strip():
        user_metadata['keyscale'] = key_scale.strip()
    if time_signature and time_signature.strip():
        user_metadata['timesignature'] = time_signature.strip()
    return user_metadata if user_metadata else None


def _convert_lm_params(lm_top_k, lm_top_p):
    """Convert LM parameters to API-compatible values."""
    top_k_value = None if not lm_top_k or lm_top_k == 0 else int(lm_top_k)
    top_p_value = None if not lm_top_p or lm_top_p >= 1.0 else lm_top_p
    return top_k_value, top_p_value


def handle_format_sample(
    llm_handler,
    caption: str,
    lyrics: str,
    bpm,
    audio_duration,
    key_scale: str,
    time_signature: str,
    lm_temperature: float,
    lm_top_k: int,
    lm_top_p: float,
    constrained_decoding_debug: bool = False,
):
    """Handle the Format button click to format caption and lyrics.

    Args:
        llm_handler: LLM handler instance.
        caption: User's caption/description.
        lyrics: User's lyrics.
        bpm: User-provided BPM.
        audio_duration: User-provided duration.
        key_scale: User-provided key scale.
        time_signature: User-provided time signature.
        lm_temperature: LLM temperature.
        lm_top_k: LLM top-k sampling.
        lm_top_p: LLM top-p sampling.
        constrained_decoding_debug: Whether to enable debug logging.

    Returns:
        Tuple of updates for captions, lyrics, bpm, audio_duration,
        key_scale, vocal_language, time_signature, is_format_caption_state,
        status_output.
    """
    if not llm_handler.llm_initialized:
        gr.Warning(t("messages.lm_not_initialized"))
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(), gr.update(),
            t("messages.lm_not_initialized"),
        )

    user_metadata = _build_user_metadata(bpm, audio_duration, key_scale, time_signature)
    top_k_value, top_p_value = _convert_lm_params(lm_top_k, lm_top_p)

    result = format_sample(
        llm_handler=llm_handler,
        caption=caption,
        lyrics=lyrics,
        user_metadata=user_metadata,
        temperature=lm_temperature,
        top_k=top_k_value,
        top_p=top_p_value,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        gr.Warning(result.status_message or t("messages.format_failed"))
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(), gr.update(),
            result.status_message or t("messages.format_failed"),
        )

    gr.Info(t("messages.format_success"))
    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    audio_duration_value = clamped_duration if clamped_duration and clamped_duration > 0 else -1

    return (
        result.caption,
        result.lyrics,
        result.bpm,
        audio_duration_value,
        result.keyscale,
        result.language,
        result.timesignature,
        True,
        result.status_message,
    )


def handle_format_caption(
    llm_handler,
    caption: str,
    lyrics: str,
    bpm,
    audio_duration,
    key_scale: str,
    time_signature: str,
    lm_temperature: float,
    lm_top_k: int,
    lm_top_p: float,
    constrained_decoding_debug: bool = False,
):
    """Format only the caption using the LLM. Lyrics are passed through unchanged.

    Returns:
        Tuple of updates for captions, bpm, audio_duration, key_scale,
        vocal_language, time_signature, is_format_caption_state, status_output.
    """
    if not llm_handler.llm_initialized:
        gr.Warning(t("messages.lm_not_initialized"))
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(),
            t("messages.lm_not_initialized"),
        )

    user_metadata = _build_user_metadata(bpm, audio_duration, key_scale, time_signature)
    top_k_value, top_p_value = _convert_lm_params(lm_top_k, lm_top_p)

    result = format_sample(
        llm_handler=llm_handler,
        caption=caption,
        lyrics=lyrics,
        user_metadata=user_metadata,
        temperature=lm_temperature,
        top_k=top_k_value,
        top_p=top_p_value,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        gr.Warning(result.status_message or t("messages.format_failed"))
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(),
            result.status_message or t("messages.format_failed"),
        )

    gr.Info(t("messages.format_success"))
    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    audio_duration_value = clamped_duration if clamped_duration and clamped_duration > 0 else -1
    cleaned_caption = result.caption.strip("'\"") if result.caption else result.caption

    return (
        cleaned_caption,
        result.bpm,
        audio_duration_value,
        result.keyscale,
        result.language,
        result.timesignature,
        True,
        result.status_message,
    )


def handle_format_lyrics(
    llm_handler,
    caption: str,
    lyrics: str,
    bpm,
    audio_duration,
    key_scale: str,
    time_signature: str,
    lm_temperature: float,
    lm_top_k: int,
    lm_top_p: float,
    constrained_decoding_debug: bool = False,
):
    """Format only the lyrics using the LLM. Caption is passed through unchanged.

    Returns:
        Tuple of updates for lyrics, bpm, audio_duration, key_scale,
        vocal_language, time_signature, is_format_caption_state, status_output.
    """
    if not llm_handler.llm_initialized:
        gr.Warning(t("messages.lm_not_initialized"))
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(),
            t("messages.lm_not_initialized"),
        )

    user_metadata = _build_user_metadata(bpm, audio_duration, key_scale, time_signature)
    top_k_value, top_p_value = _convert_lm_params(lm_top_k, lm_top_p)

    result = format_sample(
        llm_handler=llm_handler,
        caption=caption,
        lyrics=lyrics,
        user_metadata=user_metadata,
        temperature=lm_temperature,
        top_k=top_k_value,
        top_p=top_p_value,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        gr.Warning(result.status_message or t("messages.format_failed"))
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(),
            result.status_message or t("messages.format_failed"),
        )

    gr.Info(t("messages.format_success"))
    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    audio_duration_value = clamped_duration if clamped_duration and clamped_duration > 0 else -1
    cleaned_lyrics = result.lyrics.strip("'\"") if result.lyrics else result.lyrics

    return (
        cleaned_lyrics,
        result.bpm,
        audio_duration_value,
        result.keyscale,
        result.language,
        result.timesignature,
        True,
        result.status_message,
    )
