"""Analysis-mode runtime helpers for API job generation."""

from __future__ import annotations

import os
from typing import Any, Optional


def maybe_handle_analysis_only_modes(
    *,
    req: Any,
    params: Any,
    config: Any,
    llm_handler: Any,
    dit_handler: Any,
    store: Any,
    job_id: str,
) -> Optional[dict[str, Any]]:
    """Run analysis-only branches and return response payload when handled.

    Args:
        req: Generation request object.
        params: Prepared generation params object.
        config: Prepared generation config object.
        llm_handler: Initialized LLM handler (or None if unavailable).
        dit_handler: Selected DiT handler.
        store: Job store used for progress text updates.
        job_id: Current job identifier.

    Returns:
        Optional[dict[str, Any]]: Analysis response when an analysis mode is active,
            otherwise None.

    Raises:
        RuntimeError: If analysis execution fails.
    """

    if req.full_analysis_only:
        store.update_progress_text(job_id, "Starting Deep Analysis...")
        audio_codes = dit_handler.convert_src_audio_to_codes(params.src_audio)
        if not audio_codes or audio_codes.startswith("❌"):
            raise RuntimeError(f"Audio encoding failed: {audio_codes}")

        metadata_dict, status_string = llm_handler.understand_audio_from_codes(
            audio_codes=audio_codes,
            temperature=0.3,
            use_constrained_decoding=True,
            constrained_decoding_debug=config.constrained_decoding_debug,
        )
        if not metadata_dict:
            raise RuntimeError(f"LLM Understanding failed: {status_string}")

        return {
            "status_message": "Full Hardware Analysis Success",
            "bpm": metadata_dict.get("bpm"),
            "keyscale": metadata_dict.get("keyscale"),
            "timesignature": metadata_dict.get("timesignature"),
            "duration": metadata_dict.get("duration"),
            "genre": metadata_dict.get("genres") or metadata_dict.get("genre"),
            "prompt": metadata_dict.get("caption", ""),
            "lyrics": metadata_dict.get("lyrics", ""),
            "language": metadata_dict.get("language", "unknown"),
            "metas": metadata_dict,
            "audio_paths": [],
        }

    if req.analysis_only:
        lm_res = llm_handler.generate_with_stop_condition(
            caption=params.caption,
            lyrics=params.lyrics,
            infer_type="dit",
            temperature=req.lm_temperature,
            top_p=req.lm_top_p,
            use_cot_metas=True,
            use_cot_caption=req.use_cot_caption,
            use_cot_language=req.use_cot_language,
            use_constrained_decoding=True,
        )
        if not lm_res.get("success"):
            raise RuntimeError(f"Analysis Failed: {lm_res.get('error')}")

        metas_found = lm_res.get("metadata", {})
        return {
            "first_audio_path": None,
            "audio_paths": [],
            "raw_audio_paths": [],
            "generation_info": "Analysis Only Mode Complete",
            "status_message": "Success",
            "metas": metas_found,
            "bpm": metas_found.get("bpm"),
            "keyscale": metas_found.get("keyscale"),
            "duration": metas_found.get("duration"),
            "prompt": metas_found.get("caption", params.caption),
            "lyrics": params.lyrics,
            "lm_model": os.getenv("ACESTEP_LM_MODEL_PATH", ""),
            "dit_model": "None (Analysis Only)",
        }

    return None
