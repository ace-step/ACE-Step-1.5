"""Response payload helpers for successful music generation jobs."""

from __future__ import annotations

from typing import Any, Callable, Optional


def normalize_metas(meta: dict[str, Any]) -> dict[str, Any]:
    """Normalize LM metadata and ensure expected response keys exist.

    Also scrubs negative sentinel values (e.g. ``-1`` for auto-detect)
    from numeric fields so they never leak into API responses.
    """

    meta = meta or {}
    out: dict[str, Any] = dict(meta)

    if "keyscale" not in out and "key_scale" in out:
        out["keyscale"] = out.get("key_scale")
    if "timesignature" not in out and "time_signature" in out:
        out["timesignature"] = out.get("time_signature")

    # Scrub negative sentinel values from numeric metadata fields.
    for numeric_key in ("bpm", "duration"):
        val = out.get(numeric_key)
        if isinstance(val, (int, float)) and val <= 0:
            out[numeric_key] = "N/A"

    for key in ["bpm", "duration", "genres", "keyscale", "timesignature"]:
        if out.get(key) in (None, ""):
            out[key] = "N/A"
    return out


def _none_if_na_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "N/A"}:
        return None
    return text


def _extract_seed_value(audios: list[dict[str, Any]]) -> str:
    seed_values: list[str] = []
    for audio in audios:
        audio_params = audio.get("params", {})
        seed = audio_params.get("seed")
        if seed is not None:
            seed_values.append(str(seed))
    return ",".join(seed_values) if seed_values else ""


def build_generation_success_response(
    *,
    result: Any,
    params: Any,
    bpm: Any,
    audio_duration: Any,
    key_scale: Any,
    time_signature: Any,
    original_prompt: str,
    original_lyrics: str,
    inference_steps: int,
    path_to_audio_url: Callable[[str], str],
    build_generation_info: Callable[..., Any],
    lm_model_name: str,
    dit_model_name: str,
) -> dict[str, Any]:
    """Build API success payload from final generation outputs."""

    audios: list[dict[str, Any]] = list(result.audios)
    audio_paths = [audio["path"] for audio in audios if audio.get("path")]
    first_audio = audio_paths[0] if len(audio_paths) > 0 else None
    second_audio = audio_paths[1] if len(audio_paths) > 1 else None

    lm_metadata = result.extra_outputs.get("lm_metadata", {})
    metas_out = normalize_metas(lm_metadata)

    if params.cot_bpm and (not isinstance(params.cot_bpm, (int, float)) or params.cot_bpm > 0):
        metas_out["bpm"] = params.cot_bpm
    elif bpm and (not isinstance(bpm, (int, float)) or bpm > 0):
        metas_out["bpm"] = bpm

    if params.cot_duration and (not isinstance(params.cot_duration, (int, float)) or params.cot_duration > 0):
        metas_out["duration"] = params.cot_duration
    elif audio_duration and (not isinstance(audio_duration, (int, float)) or audio_duration > 0):
        metas_out["duration"] = audio_duration

    if params.cot_keyscale:
        metas_out["keyscale"] = params.cot_keyscale
    elif key_scale:
        metas_out["keyscale"] = key_scale

    if params.cot_timesignature:
        metas_out["timesignature"] = params.cot_timesignature
    elif time_signature:
        metas_out["timesignature"] = time_signature

    metas_out["prompt"] = original_prompt
    metas_out["lyrics"] = original_lyrics

    seed_value = _extract_seed_value(audios)
    time_costs = result.extra_outputs.get("time_costs", {})
    generation_info = build_generation_info(
        lm_metadata=lm_metadata,
        time_costs=time_costs,
        seed_value=seed_value,
        inference_steps=inference_steps,
        num_audios=len(audios),
    )

    return {
        "first_audio_path": path_to_audio_url(first_audio) if first_audio else None,
        "second_audio_path": path_to_audio_url(second_audio) if second_audio else None,
        "audio_paths": [path_to_audio_url(path) for path in audio_paths],
        "raw_audio_paths": list(audio_paths),
        "generation_info": generation_info,
        "status_message": result.status_message,
        "seed_value": seed_value,
        "prompt": params.caption or "",
        "lyrics": params.lyrics or "",
        "metas": metas_out,
        "bpm": metas_out.get("bpm") if isinstance(metas_out.get("bpm"), int) else None,
        "duration": (
            metas_out.get("duration")
            if isinstance(metas_out.get("duration"), (int, float))
            else None
        ),
        "genres": _none_if_na_str(metas_out.get("genres")),
        "keyscale": _none_if_na_str(metas_out.get("keyscale")),
        "timesignature": _none_if_na_str(metas_out.get("timesignature")),
        "lm_model": lm_model_name,
        "dit_model": dit_model_name,
        "cot_caption": getattr(params, "cot_caption", "") or "",
        "cot_lyrics": getattr(params, "cot_lyrics", "") or "",
    }
