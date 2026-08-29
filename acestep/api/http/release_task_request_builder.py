"""Helpers for building release-task request models from parsed inputs."""

from __future__ import annotations

import re
from typing import Any, Optional

DEFAULT_STEPS_TURBO = 8
DEFAULT_STEPS_SFT = 50
DEFAULT_STEPS_BASE = 32
DEFAULT_STEPS_LEGACY = 8


def _has_model_token(token: str, model_name: str) -> bool:
    """Return whether *token* appears as a delimited segment in model name.

    Matching is case-sensitive; callers should normalize case when needed.
    """

    return re.search(rf"(^|[\\/._-]){token}($|[\\/._-])", model_name) is not None


def _default_inference_steps_for_model(model_name: Optional[str]) -> int:
    """Infer default diffusion steps from selected model name.

    Defaults are aligned with Gradio behavior:
    - turbo variants: 8
    - sft variants: 50
    - explicit non-turbo/non-sft model names (for example base): 32
    - unspecified model: 8 (legacy API default)
    """

    normalized = (model_name or "").strip().lower()
    if not normalized:
        return DEFAULT_STEPS_LEGACY
    if _has_model_token("turbo", normalized):
        return DEFAULT_STEPS_TURBO
    if _has_model_token("sft", normalized):
        return DEFAULT_STEPS_SFT
    return DEFAULT_STEPS_BASE


def build_generate_music_request(
    parser: Any,
    request_model_cls: Any,
    default_dit_instruction: str,
    lm_default_temperature: float,
    lm_default_cfg_scale: float,
    lm_default_top_p: float,
    **overrides: Any,
) -> Any:
    """Build request-model payload for ``/release_task``.

    Args:
        parser: Request parser exposing ``str``, ``bool``, ``int``, ``float``, and ``get``.
        request_model_cls: Request model class (for example ``GenerateMusicRequest``).
        default_dit_instruction: Default DiT instruction string.
        lm_default_temperature: Default LM temperature value.
        lm_default_cfg_scale: Default LM CFG scale value.
        lm_default_top_p: Default LM top-p value.
        **overrides: Optional explicit field overrides for parsed values.

    Returns:
        Instantiated request model object.
    """

    reference_audio = overrides.pop("reference_audio_path", None) or parser.str("reference_audio_path") or None
    src_audio = overrides.pop("src_audio_path", None) or parser.str("src_audio_path") or None

    track_classes = parser.get("track_classes")
    if track_classes is not None and isinstance(track_classes, str):
        track_classes = [track_classes]

    requested_model = parser.str("model") or None
    raw_seed = parser.get("seed")
    seed_value = raw_seed if raw_seed is not None else -1

    payload = dict(
        prompt=parser.str("prompt"),
        global_caption=parser.str("global_caption"),
        lyrics=parser.str("lyrics"),
        thinking=parser.bool("thinking"),
        analysis_only=parser.bool("analysis_only"),
        full_analysis_only=parser.bool("full_analysis_only"),
        extract_codes_only=parser.bool("extract_codes_only"),
        sample_mode=parser.bool("sample_mode"),
        sample_query=parser.str("sample_query"),
        use_format=parser.bool("use_format"),
        model=requested_model,
        bpm=parser.int("bpm"),
        key_scale=parser.str("key_scale"),
        time_signature=parser.str("time_signature"),
        audio_duration=parser.float("audio_duration"),
        vocal_language=parser.str("vocal_language", "en"),
        inference_steps=parser.int(
            "inference_steps",
            _default_inference_steps_for_model(requested_model),
        ),
        guidance_scale=parser.float("guidance_scale", 7.0),
        use_random_seed=parser.bool("use_random_seed", True),
        seed=seed_value,
        batch_size=parser.int("batch_size"),
        repainting_start=parser.float("repainting_start", 0.0),
        repainting_end=parser.float("repainting_end"),
        instruction=parser.str("instruction", default_dit_instruction),
        audio_cover_strength=parser.float("audio_cover_strength", 1.0),
        cover_noise_strength=parser.float("cover_noise_strength", 0.0),
        audio_code_string=parser.str("audio_code_string"),
        reference_audio_path=reference_audio,
        src_audio_path=src_audio,
        task_type=parser.str("task_type", "text2music"),
        chunk_mask_mode=parser.str("chunk_mask_mode", "auto"),
        repaint_latent_crossfade_frames=parser.int(
            "repaint_latent_crossfade_frames", 10,
        ),
        repaint_wav_crossfade_sec=parser.float(
            "repaint_wav_crossfade_sec", 0.0,
        ),
        repaint_mode=parser.str("repaint_mode", "balanced"),
        repaint_strength=parser.float("repaint_strength", 0.5),
        use_adg=parser.bool("use_adg"),
        cfg_interval_start=parser.float("cfg_interval_start", 0.0),
        cfg_interval_end=parser.float("cfg_interval_end", 1.0),
        infer_method=parser.str("infer_method", "ode"),
        shift=parser.float("shift", 3.0),
        audio_format=parser.str("audio_format", "mp3"),
        use_tiled_decode=parser.bool("use_tiled_decode", True),
        lm_model_path=parser.str("lm_model_path") or None,
        lm_backend=parser.str("lm_backend", "vllm"),
        lm_temperature=parser.float("lm_temperature", lm_default_temperature),
        lm_cfg_scale=parser.float("lm_cfg_scale", lm_default_cfg_scale),
        lm_top_k=parser.int("lm_top_k"),
        lm_top_p=parser.float("lm_top_p", lm_default_top_p),
        lm_repetition_penalty=parser.float("lm_repetition_penalty", 1.0),
        lm_negative_prompt=parser.str("lm_negative_prompt", "NO USER INPUT"),
        constrained_decoding=parser.bool("constrained_decoding", True),
        constrained_decoding_debug=parser.bool("constrained_decoding_debug"),
        use_cot_caption=parser.bool("use_cot_caption", True),
        use_cot_language=parser.bool("use_cot_language", True),
        is_format_caption=parser.bool("is_format_caption"),
        allow_lm_batch=parser.bool("allow_lm_batch", True),
        track_name=parser.str("track_name"),
        track_classes=track_classes,
    )
    payload.update(overrides)
    return request_model_cls(**payload)
