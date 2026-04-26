"""Canonical parameter aliasing and parsing helpers for release-task requests."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


PARAM_ALIASES: Dict[str, list[str]] = {
    "prompt": ["prompt", "caption"],
    "lyrics": ["lyrics"],
    "thinking": ["thinking"],
    "analysis_only": ["analysis_only", "analysisOnly"],
    "full_analysis_only": ["full_analysis_only", "fullAnalysisOnly"],
    "extract_codes_only": ["extract_codes_only", "extractCodesOnly"],
    "sample_mode": ["sample_mode", "sampleMode"],
    "sample_query": ["sample_query", "sampleQuery", "description", "desc"],
    "use_format": ["use_format", "useFormat", "format"],
    "model": ["model", "model_name", "modelName", "dit_model", "ditModel"],
    "key_scale": ["key_scale", "keyscale", "keyScale", "key"],
    "time_signature": ["time_signature", "timesignature", "timeSignature"],
    "audio_duration": ["audio_duration", "duration", "audioDuration", "target_duration", "targetDuration"],
    "vocal_language": ["vocal_language", "vocalLanguage", "language"],
    "bpm": ["bpm"],
    "inference_steps": ["inference_steps", "inferenceSteps"],
    "guidance_scale": ["guidance_scale", "guidanceScale"],
    "use_random_seed": ["use_random_seed", "useRandomSeed"],
    "seed": ["seed"],
    "audio_cover_strength": ["audio_cover_strength", "audioCoverStrength", "cover_strength", "coverStrength"],
    "cover_noise_strength": ["cover_noise_strength", "coverNoiseStrength"],
    "audio_code_string": ["audio_code_string", "audioCodeString", "audio_codes"],
    "reference_audio_path": ["reference_audio_path", "ref_audio_path", "referenceAudioPath", "refAudioPath"],
    "src_audio_path": ["src_audio_path", "ctx_audio_path", "sourceAudioPath", "srcAudioPath", "ctxAudioPath"],
    "task_type": ["task_type", "taskType"],
    "infer_method": ["infer_method", "inferMethod"],
    "use_tiled_decode": ["use_tiled_decode", "useTiledDecode"],
    "constrained_decoding": ["constrained_decoding", "constrainedDecoding", "constrained"],
    "constrained_decoding_debug": ["constrained_decoding_debug", "constrainedDecodingDebug"],
    "use_cot_caption": ["use_cot_caption", "cot_caption", "cot-caption"],
    "use_cot_language": ["use_cot_language", "cot_language", "cot-language"],
    "is_format_caption": ["is_format_caption", "isFormatCaption"],
    "allow_lm_batch": ["allow_lm_batch", "allowLmBatch", "parallel_thinking"],
    "instruction": ["instruction"],
    "track_name": ["track_name", "trackName"],
    "track_classes": ["track_classes", "trackClasses", "instruments"],
}


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Parse int-like values and return fallback on conversion failure."""

    if value is None:
        return default
    if isinstance(value, int):
        return value
    as_text = str(value).strip()
    if as_text == "":
        return default
    try:
        return int(as_text)
    except Exception:
        return default


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Parse float-like values and return fallback on conversion failure."""

    if value is None:
        return default
    if isinstance(value, float):
        return value
    as_text = str(value).strip()
    if as_text == "":
        return default
    try:
        return float(as_text)
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    """Parse boolean-like values from common textual representations."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    as_text = str(value).strip().lower()
    if as_text == "":
        return default
    return as_text in {"1", "true", "yes", "y", "on"}


class RequestParser:
    """Parse request parameters from multiple sources with alias support."""

    def __init__(self, raw: dict):
        """Initialize parser and precompute nested metadata sources.

        Args:
            raw: Flat request body/form dictionary from client.
        """

        self._raw = dict(raw) if raw else {}
        self._param_obj = self._parse_json(self._raw.get("param_obj"))
        self._metas = self._find_metas()

    def _parse_json(self, value: Any) -> dict:
        """Parse dict-or-JSON-string values into dictionaries."""

        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
                return {}
            except Exception:
                pass
        return {}

    def _find_metas(self) -> dict:
        """Locate and parse first metadata field from known alias keys."""

        for key in ("metas", "meta", "metadata", "user_metadata", "userMetadata"):
            raw_value = self._raw.get(key)
            if raw_value:
                return self._parse_json(raw_value)
        return {}

    def get(self, name: str, default: Any = None):
        """Get parameter by canonical name from all known request sources."""

        aliases = PARAM_ALIASES.get(name, [name])
        for source in (self._raw, self._param_obj, self._metas):
            for alias in aliases:
                value = source.get(alias)
                if value is not None:
                    return value
        return default

    def str(self, name: str, default: str = "") -> str:
        """Get parameter as string with fallback default."""

        value = self.get(name)
        return str(value) if value is not None else default

    def int(self, name: str, default: Optional[int] = None) -> Optional[int]:
        """Get parameter as integer with fallback default."""

        return _to_int(self.get(name), default)

    def float(self, name: str, default: Optional[float] = None) -> Optional[float]:
        """Get parameter as float with fallback default."""

        return _to_float(self.get(name), default)

    def bool(self, name: str, default: bool = False) -> bool:
        """Get parameter as bool with fallback default."""

        return _to_bool(self.get(name), default)
