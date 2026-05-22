"""PMI-based quality scoring and per-sample score selection.

Provides handlers for computing PMI quality scores and DiT alignment
scores on generated audio samples.
"""
import traceback

import gradio as gr
import torch
from loguru import logger

from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.events.results.session_artifacts import (
    artifact_to_alignment_tensors,
    load_batch_sample_session_tensors,
)


_PMI_MIN_FREE_GB_BY_MODEL_SIZE = {
    "0.6B": 8.0,
    "1.7B": 16.0,
    "4B": 32.0,
}


def calculate_score_handler(
    llm_handler,
    audio_codes_str,
    caption,
    lyrics,
    lm_metadata,
    bpm,
    key_scale,
    time_signature,
    audio_duration,
    vocal_language,
    score_scale,
    dit_handler,
    extra_tensor_data,
    inference_steps,
):
    """Calculate PMI-based quality score for generated audio.

    PMI (Pointwise Mutual Information) removes condition bias:
    ``score = log P(condition|codes) - log P(condition)``

    Falls back to DiT alignment scoring when audio codes are unavailable
    (e.g. Cover/Repaint modes).

    Args:
        llm_handler: LLM handler instance.
        audio_codes_str: Generated audio codes string.
        caption: Caption text used for generation.
        lyrics: Lyrics text used for generation.
        lm_metadata: LM-generated metadata dictionary.
        bpm: BPM value.
        key_scale: Key scale value.
        time_signature: Time signature value.
        audio_duration: Audio duration value.
        vocal_language: Vocal language value.
        score_scale: Sensitivity scale parameter.
        dit_handler: DiT handler instance (for alignment scoring).
        extra_tensor_data: Dictionary containing tensors for the specific sample.
        inference_steps: Number of inference steps used.

    Returns:
        Score display string.
    """
    from acestep.core.scoring.lm_score import calculate_pmi_score_per_condition

    has_audio_codes = audio_codes_str and audio_codes_str.strip()
    has_dit_alignment_data = dit_handler and extra_tensor_data and lyrics and lyrics.strip()

    if not has_audio_codes and not has_dit_alignment_data:
        return t("messages.no_codes")

    try:
        scores_per_condition = {}
        global_score = 0.0
        alignment_report = ""
        pmi_skip_report = ""

        # PMI-based scoring (requires audio codes and LLM)
        if has_audio_codes:
            if not llm_handler.llm_initialized:
                if not has_dit_alignment_data:
                    return t("messages.lm_not_initialized")
            else:
                pmi_skip_reason = _pmi_vram_skip_reason(llm_handler)
                if pmi_skip_reason:
                    pmi_skip_report = f"\n⚠️ PMI Score Skipped: {pmi_skip_reason}"
                else:
                    metadata = _build_score_metadata(
                        lm_metadata=lm_metadata,
                        bpm=bpm,
                        caption=caption,
                        audio_duration=audio_duration,
                        key_scale=key_scale,
                        vocal_language=vocal_language,
                        time_signature=time_signature,
                    )
                    scores_per_condition, global_score, pmi_status = calculate_pmi_score_per_condition(
                        llm_handler=llm_handler,
                        audio_codes=audio_codes_str,
                        caption=caption or "",
                        lyrics=lyrics or "",
                        metadata=metadata,
                        temperature=1.0,
                        topk=10,
                        score_scale=score_scale,
                    )
                    if pmi_status and pmi_status.startswith("❌"):
                        pmi_skip_report = f"\n⚠️ PMI Score Failed: {pmi_status}"

        # DiT alignment scoring
        if has_dit_alignment_data:
            try:
                align_result = dit_handler.get_lyric_score(
                    pred_latent=extra_tensor_data.get('pred_latent'),
                    encoder_hidden_states=extra_tensor_data.get('encoder_hidden_states'),
                    encoder_attention_mask=extra_tensor_data.get('encoder_attention_mask'),
                    context_latents=extra_tensor_data.get('context_latents'),
                    lyric_token_ids=extra_tensor_data.get('lyric_token_ids'),
                    vocal_language=vocal_language or "en",
                    inference_steps=int(inference_steps),
                    seed=42,
                )
                if align_result.get("success"):
                    lm_align = align_result.get("lm_score", 0.0)
                    dit_align = align_result.get("dit_score", 0.0)
                    alignment_report = (
                        f"  • llm lyrics alignment score: {lm_align:.4f}\n"
                        f"  • dit lyrics alignment score: {dit_align:.4f}\n"
                        "\n(Measures how well lyrics timestamps match audio energy using Cross-Attention)"
                    )
                else:
                    alignment_report = f"\n⚠️ Alignment Score Failed: {align_result.get('error', 'Unknown error')}"
            except Exception as e:
                alignment_report = f"\n⚠️ Alignment Score Error: {str(e)}"

        # Format display string
        if has_audio_codes and llm_handler.llm_initialized:
            if not scores_per_condition:
                if alignment_report and not alignment_report.startswith("\n⚠️"):
                    return "📊 DiT Alignment Scores (PMI unavailable):\n" + alignment_report + pmi_skip_report
                if pmi_skip_report:
                    return pmi_skip_report.strip()
                return t("messages.score_failed", error="PMI scoring returned no results")

            condition_lines = [
                f"  • {name}: {val:.4f}"
                for name, val in sorted(scores_per_condition.items())
            ]
            conditions_display = "\n".join(condition_lines) if condition_lines else "  (no conditions)"
            final_output = (
                f"✅ Global Quality Score: {global_score:.4f} (0-1, higher=better)\n\n"
                f"📊 Per-Condition Scores (0-1):\n{conditions_display}\n"
            )
            if alignment_report:
                final_output += alignment_report + "\n"
            if pmi_skip_report:
                final_output += pmi_skip_report + "\n"
            final_output += "Note: Metadata uses Top-k Recall, Caption/Lyrics use PMI"
            return final_output
        else:
            if alignment_report and not alignment_report.startswith("\n⚠️"):
                return "📊 DiT Alignment Scores (LM codes not available for Cover/Repaint mode):\n" + alignment_report
            elif alignment_report:
                return alignment_report
            return "⚠️ No scoring data available"

    except Exception as e:
        return t("messages.score_error", error=str(e)) + f"\n{traceback.format_exc()}"


def _build_score_metadata(
    lm_metadata,
    bpm,
    caption,
    audio_duration,
    key_scale,
    vocal_language,
    time_signature,
):
    """Build the metadata payload used by PMI score calculation."""
    metadata = {}
    if lm_metadata and isinstance(lm_metadata, dict):
        metadata.update(lm_metadata)
    if bpm is not None and "bpm" not in metadata:
        try:
            metadata["bpm"] = int(bpm)
        except (TypeError, ValueError):
            pass
    if caption and "caption" not in metadata:
        metadata["caption"] = caption
    if audio_duration is not None and "duration" not in metadata:
        try:
            duration = float(audio_duration)
            if duration > 0:
                metadata["duration"] = int(duration)
        except (TypeError, ValueError):
            pass
    if key_scale and key_scale.strip() and "keyscale" not in metadata:
        metadata["keyscale"] = key_scale.strip()
    if vocal_language and vocal_language.strip() and "language" not in metadata:
        metadata["language"] = vocal_language.strip()
    if time_signature and time_signature.strip() and "timesignature" not in metadata:
        metadata["timesignature"] = time_signature.strip()
    return metadata


def _pmi_vram_skip_reason(llm_handler) -> str | None:
    """Return a user-facing reason to skip PMI when free VRAM is too low."""
    backend = getattr(llm_handler, "llm_backend", "pt")
    if backend not in ("vllm", "mlx"):
        return None
    if backend == "vllm" and getattr(llm_handler, "_last_initialize_config", None):
        return None
    if not torch.cuda.is_available():
        return None
    try:
        free_bytes, _total_bytes = torch.cuda.mem_get_info()
    except (RuntimeError, AttributeError):
        return None

    free_gb = free_bytes / (1024 ** 3)
    required_gb = _estimate_pmi_min_free_gb(llm_handler)
    if free_gb >= required_gb:
        return None
    reason = (
        f"only {free_gb:.1f}GB free VRAM is available, but PMI scoring with "
        f"the {backend} backend may need about {required_gb:.0f}GB free. "
        "Using DiT alignment score when available."
    )
    logger.warning("[score] Skipping PMI score: {}", reason)
    return reason


def _estimate_pmi_min_free_gb(llm_handler) -> float:
    """Estimate free VRAM needed before loading the auxiliary HF scorer."""
    model_path = _llm_model_path_for_score(llm_handler)
    model_size = _lm_model_size_label(model_path)
    return _PMI_MIN_FREE_GB_BY_MODEL_SIZE.get(model_size, 16.0)


def _llm_model_path_for_score(llm_handler) -> str:
    """Best-effort model path lookup for the active LLM backend."""
    if getattr(llm_handler, "llm_backend", None) == "vllm":
        try:
            return str(llm_handler.llm.model_runner.config.model)
        except AttributeError:
            return ""
    return str(getattr(llm_handler, "_mlx_model_path", "") or "")


def _lm_model_size_label(model_path: str) -> str:
    """Return a coarse LM size label from a checkpoint path."""
    lowered = model_path.lower()
    if "0.6b" in lowered:
        return "0.6B"
    if "1.7b" in lowered:
        return "1.7B"
    if "4b" in lowered:
        return "4B"
    return ""


def calculate_score_handler_with_selection(
    dit_handler,
    llm_handler,
    sample_idx,
    score_scale,
    current_batch_index,
    batch_queue,
):
    """Calculate quality score for a specific sample from batch queue data.

    Reads all parameters from the historical batch rather than current UI
    values, ensuring scores reflect the actual generation settings.

    Args:
        dit_handler: DiT handler instance.
        llm_handler: LLM handler instance.
        sample_idx: 1-based sample index (1-8).
        score_scale: Sensitivity scale parameter.
        current_batch_index: Current batch index.
        batch_queue: Batch queue dict.

    Returns:
        Tuple of ``(score_display_update, accordion_update, batch_queue)``.
    """
    if current_batch_index not in batch_queue:
        return gr.skip(), gr.skip(), batch_queue

    batch_data = batch_queue[current_batch_index]
    params = batch_data.get("generation_params", {})

    caption = params.get("captions", "")
    lyrics = params.get("lyrics", "")
    bpm = params.get("bpm")
    key_scale = params.get("key_scale", "")
    time_signature = params.get("time_signature", "")
    audio_duration = params.get("audio_duration", -1)
    vocal_language = params.get("vocal_language", "")
    inference_steps = params.get("inference_steps", 8)
    lm_metadata = batch_data.get("lm_generated_metadata", None)

    stored_codes = batch_data.get("codes", "")
    stored_allow_lm_batch = batch_data.get("allow_lm_batch", False)

    audio_codes_str = ""
    if stored_allow_lm_batch and isinstance(stored_codes, list):
        if 0 <= sample_idx - 1 < len(stored_codes):
            code_item = stored_codes[sample_idx - 1]
            audio_codes_str = code_item if isinstance(code_item, str) else ""
    else:
        audio_codes_str = stored_codes if isinstance(stored_codes, str) else ""

    # Extract tensor data for alignment scoring
    extra_tensor_data = None
    extra_outputs = batch_data.get("extra_outputs", {})
    if extra_outputs and dit_handler:
        pred_latents = extra_outputs.get("pred_latents")
        if pred_latents is not None:
            idx0 = sample_idx - 1
            if 0 <= idx0 < pred_latents.shape[0]:
                try:
                    extra_tensor_data = {
                        "pred_latent": pred_latents[idx0:idx0 + 1],
                        "encoder_hidden_states": extra_outputs.get("encoder_hidden_states")[idx0:idx0 + 1],
                        "encoder_attention_mask": extra_outputs.get("encoder_attention_mask")[idx0:idx0 + 1],
                        "context_latents": extra_outputs.get("context_latents")[idx0:idx0 + 1],
                        "lyric_token_ids": extra_outputs.get("lyric_token_idss")[idx0:idx0 + 1],
                    }
                    if any(v is None for v in extra_tensor_data.values()):
                        extra_tensor_data = None
                except Exception as e:
                    logger.warning(
                        "[score] Failed to slice in-memory tensor data for sample {}: {}",
                        sample_idx,
                        e,
                    )
                    extra_tensor_data = None
    if extra_tensor_data is None and dit_handler:
        artifact = load_batch_sample_session_tensors(batch_data, sample_idx)
        extra_tensor_data = artifact_to_alignment_tensors(artifact)

    score_display = calculate_score_handler(
        llm_handler, audio_codes_str, caption, lyrics, lm_metadata,
        bpm, key_scale, time_signature, audio_duration, vocal_language,
        score_scale, dit_handler, extra_tensor_data, inference_steps,
    )

    if current_batch_index in batch_queue:
        if "scores" not in batch_queue[current_batch_index]:
            batch_queue[current_batch_index]["scores"] = [""] * 8
        batch_queue[current_batch_index]["scores"][sample_idx - 1] = score_display

    return (
        gr.update(value=score_display, visible=True),
        gr.skip(),
        batch_queue,
    )
