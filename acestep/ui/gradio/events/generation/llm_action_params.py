"""Shared parameter-normalization helpers for generation LLM actions."""


def build_user_metadata(bpm, audio_duration, key_scale, time_signature):
    """Build constrained-decoding metadata from optional manual inputs."""
    user_metadata = {}
    if bpm is not None and bpm > 0:
        user_metadata["bpm"] = int(bpm)
    if audio_duration is not None and float(audio_duration) > 0:
        user_metadata["duration"] = int(audio_duration)
    if key_scale and key_scale.strip():
        user_metadata["keyscale"] = key_scale.strip()
    if time_signature and time_signature.strip():
        user_metadata["timesignature"] = time_signature.strip()
    return user_metadata if user_metadata else None


def convert_lm_params(lm_top_k, lm_top_p):
    """Convert UI LM controls to inference-compatible top-k/top-p values."""
    top_k_value = None if not lm_top_k or lm_top_k == 0 else int(lm_top_k)
    top_p_value = None if not lm_top_p or lm_top_p >= 1.0 else lm_top_p
    return top_k_value, top_p_value
