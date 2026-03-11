"""Shared parameter-normalization helpers for generation LLM actions."""
from typing import Any, Dict, Optional, Tuple, Union


def _parse_positive_duration_seconds(value: Optional[Union[float, int, str]]) -> Optional[int]:
    """Parse optional duration input and return positive whole seconds."""
    if value is None:
        return None
    try:
        duration_value = float(value)
    except (TypeError, ValueError):
        return None
    if duration_value <= 0:
        return None
    return int(duration_value)


def build_user_metadata(
    bpm: Optional[Union[int, float]],
    audio_duration: Optional[Union[float, int, str]],
    key_scale: Optional[str],
    time_signature: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Build constrained-decoding metadata from optional manual inputs."""
    user_metadata: Dict[str, Any] = {}
    if bpm is not None and bpm > 0:
        user_metadata["bpm"] = int(bpm)
    parsed_duration = _parse_positive_duration_seconds(audio_duration)
    if parsed_duration is not None:
        user_metadata["duration"] = parsed_duration
    if key_scale and key_scale.strip():
        user_metadata["keyscale"] = key_scale.strip()
    if time_signature and time_signature.strip():
        user_metadata["timesignature"] = time_signature.strip()
    return user_metadata if user_metadata else None


def convert_lm_params(
    lm_top_k: Optional[Union[int, float]],
    lm_top_p: Optional[float],
) -> Tuple[Optional[int], Optional[float]]:
    """Convert UI LM controls to inference-compatible top-k/top-p values."""
    top_k_value = None if lm_top_k is None or lm_top_k == 0 else int(lm_top_k)
    top_p_value = None if lm_top_p is None or lm_top_p >= 1.0 else float(lm_top_p)
    return top_k_value, top_p_value
