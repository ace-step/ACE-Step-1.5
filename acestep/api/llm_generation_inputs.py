"""LLM-driven request input preparation helpers for generation jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class PreparedLlmInputs:
    """Resolved LLM flags and generation input values."""

    lm_top_k: int
    lm_top_p: float
    thinking: bool
    sample_mode: bool
    use_cot_caption: bool
    use_cot_language: bool
    full_analysis_only: bool
    caption: str
    lyrics: str
    bpm: Any
    key_scale: Any
    time_signature: Any
    audio_duration: Any
    original_prompt: str
    original_lyrics: str
    format_has_duration: bool
    global_caption: str = ""


def prepare_llm_generation_inputs(
    *,
    app_state: Any,
    llm_handler: Any,
    req: Any,
    selected_handler_device: str,
    parse_description_hints: Callable[[str], tuple[Optional[str], bool]],
    create_sample_fn: Callable[..., Any],
    format_sample_fn: Callable[..., Any],
    ensure_llm_ready_fn: Callable[[], None],
    log_fn: Callable[[str], None] = print,
) -> PreparedLlmInputs:
    """Resolve LLM flags and prepare caption/lyrics/metadata inputs for generation.

    Args:
        app_state: FastAPI app state with LLM initialization flags.
        llm_handler: LLM handler instance.
        req: Generation request object.
        selected_handler_device: Device of the active diffusion handler.
        parse_description_hints: Helper to infer language/instrumental hints.
        create_sample_fn: Function that generates sample caption/lyrics metadata.
        format_sample_fn: Function that formats sample metadata from caption/lyrics.
        ensure_llm_ready_fn: Callback that lazily initializes the LLM.
        log_fn: Logging callback for status output.

    Returns:
        PreparedLlmInputs: Normalized generation inputs and LLM flags.

    Raises:
        RuntimeError: If required LLM functionality is unavailable or sampling fails.
    """

    lm_top_k = req.lm_top_k if req.lm_top_k and req.lm_top_k > 0 else 0
    lm_top_p = req.lm_top_p if req.lm_top_p and req.lm_top_p < 1.0 else 0.9

    thinking = bool(req.thinking)
    sample_mode = bool(req.sample_mode)
    has_sample_query = bool(req.sample_query and req.sample_query.strip())
    use_format = bool(req.use_format)
    use_cot_caption = bool(req.use_cot_caption)
    use_cot_language = bool(req.use_cot_language)
    full_analysis_only = bool(req.full_analysis_only)

    if req.task_type == "cover" and selected_handler_device == "mps":
        if getattr(app_state, "_llm_initialized", False) and getattr(
            llm_handler, "llm_initialized", False
        ):
            try:
                log_fn("[API Server] unloading.")
                llm_handler.unload()
                app_state._llm_initialized = False
                app_state._llm_init_error = None
            except Exception as exc:
                log_fn(f"[API Server] Failed to unload LM: {exc}")

    require_llm = thinking or sample_mode or has_sample_query or use_format or full_analysis_only
    want_llm = use_cot_caption or use_cot_language

    llm_available = True
    if require_llm or want_llm:
        ensure_llm_ready_fn()
        if getattr(app_state, "_llm_init_error", None):
            llm_available = False

    if require_llm and not llm_available:
        raise RuntimeError(f"5Hz LM init failed: {app_state._llm_init_error}")

    if want_llm and not llm_available:
        if use_cot_caption or use_cot_language:
            log_fn(
                "[API Server] LLM unavailable, auto-disabling: "
                f"use_cot_caption={use_cot_caption}->False, use_cot_language={use_cot_language}->False"
            )
        use_cot_caption = False
        use_cot_language = False

    caption = req.prompt
    lyrics = req.lyrics
    bpm = req.bpm
    key_scale = req.key_scale
    time_signature = req.time_signature
    audio_duration = req.audio_duration

    original_prompt = req.prompt or ""
    original_lyrics = req.lyrics or ""

    if sample_mode or has_sample_query:
        sample_query = req.sample_query if has_sample_query else "NO USER INPUT"
        parsed_language, parsed_instrumental = parse_description_hints(sample_query)

        if req.vocal_language and req.vocal_language not in ("en", "unknown", ""):
            sample_language = req.vocal_language
        else:
            sample_language = parsed_language

        sample_result = create_sample_fn(
            llm_handler=llm_handler,
            query=sample_query,
            instrumental=parsed_instrumental,
            vocal_language=sample_language,
            temperature=req.lm_temperature,
            top_k=lm_top_k if lm_top_k > 0 else None,
            top_p=lm_top_p if lm_top_p < 1.0 else None,
            use_constrained_decoding=True,
        )

        if not sample_result.success:
            raise RuntimeError(f"create_sample failed: {sample_result.error or sample_result.status_message}")

        caption = sample_result.caption
        lyrics = sample_result.lyrics
        bpm = sample_result.bpm
        key_scale = sample_result.keyscale
        time_signature = sample_result.timesignature
        audio_duration = sample_result.duration

    format_has_duration = False
    if req.use_format and (caption or lyrics):
        ensure_llm_ready_fn()
        if getattr(app_state, "_llm_init_error", None):
            raise RuntimeError(f"5Hz LM init failed (needed for format): {app_state._llm_init_error}")

        user_metadata_for_format = {}
        if bpm is not None:
            user_metadata_for_format["bpm"] = bpm
        if audio_duration is not None and float(audio_duration) > 0:
            user_metadata_for_format["duration"] = float(audio_duration)
        if key_scale:
            user_metadata_for_format["keyscale"] = key_scale
        if time_signature:
            user_metadata_for_format["timesignature"] = time_signature
        if req.vocal_language and req.vocal_language != "unknown":
            user_metadata_for_format["language"] = req.vocal_language

        format_result = format_sample_fn(
            llm_handler=llm_handler,
            caption=caption,
            lyrics=lyrics,
            user_metadata=user_metadata_for_format if user_metadata_for_format else None,
            temperature=req.lm_temperature,
            top_k=lm_top_k if lm_top_k > 0 else None,
            top_p=lm_top_p if lm_top_p < 1.0 else None,
            use_constrained_decoding=True,
        )
        if format_result.success:
            caption = format_result.caption or caption
            lyrics = format_result.lyrics or lyrics
            if format_result.duration:
                audio_duration = format_result.duration
                format_has_duration = True
            if format_result.bpm:
                bpm = format_result.bpm
            if format_result.keyscale:
                key_scale = format_result.keyscale
            if format_result.timesignature:
                time_signature = format_result.timesignature

    return PreparedLlmInputs(
        lm_top_k=lm_top_k,
        lm_top_p=lm_top_p,
        thinking=thinking,
        sample_mode=sample_mode,
        use_cot_caption=use_cot_caption,
        use_cot_language=use_cot_language,
        full_analysis_only=full_analysis_only,
        caption=caption,
        lyrics=lyrics,
        bpm=bpm,
        key_scale=key_scale,
        time_signature=time_signature,
        audio_duration=audio_duration,
        original_prompt=original_prompt,
        original_lyrics=original_lyrics,
        format_has_duration=format_has_duration,
        global_caption=getattr(req, "global_caption", "") or "",
    )
