"""Persist generated-session artifacts for later result actions."""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
from loguru import logger


ARTIFACT_KIND = "generation_intermediates_v1"
ARTIFACT_FIELD_MAP = {
    "pred_latents": "pred_latents",
    "encoder_hidden_states": "encoder_hidden_states",
    "encoder_attention_mask": "encoder_attention_mask",
    "context_latents": "context_latents",
    "lyric_token_idss": "lyric_token_ids",
}
REQUIRED_ARTIFACT_KEYS = tuple(ARTIFACT_FIELD_MAP.values())


def persist_sample_session_artifacts(
    extra_outputs: dict[str, Any],
    sample_idx: int,
    json_path: str,
    audio_params: dict[str, Any],
) -> None:
    """Persist per-sample intermediate tensors beside an audio JSON sidecar.

    Args:
        extra_outputs: Generation result extra outputs containing batch tensors.
        sample_idx: Zero-based sample index in the current generation batch.
        json_path: Path to the JSON sidecar that will reference the artifact.
        audio_params: Audio metadata dict updated in-place with artifact fields.
    """
    if not extra_outputs:
        return

    arrays: dict[str, np.ndarray] = {}
    for source_key, artifact_key in ARTIFACT_FIELD_MAP.items():
        array = _sample_tensor_to_numpy(extra_outputs.get(source_key), sample_idx)
        if array is not None:
            arrays[artifact_key] = array

    if not all(key in arrays for key in REQUIRED_ARTIFACT_KEYS):
        return

    artifact_path = Path(json_path).with_suffix(".session.npz")
    try:
        np.savez(artifact_path, **arrays)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("[session_artifacts] Could not persist session artifact: {}", exc)
        return

    audio_params["session_artifact_file"] = artifact_path.name
    audio_params["session_artifact_kind"] = ARTIFACT_KIND


def load_session_artifacts(path: str | os.PathLike[str] | None) -> dict[str, torch.Tensor] | None:
    """Load per-sample artifact tensors for an audio or JSON sidecar path.

    Args:
        path: Generated audio file path or its JSON sidecar path.

    Returns:
        Mapping of artifact keys to CPU tensors, or ``None`` if no complete
        artifact exists.
    """
    json_path = _find_json_sidecar(path)
    if json_path is None:
        return None

    params = _load_json(json_path)
    if params.get("session_artifact_kind") != ARTIFACT_KIND:
        return None

    artifact_name = params.get("session_artifact_file")
    if not isinstance(artifact_name, str) or not artifact_name:
        return None

    artifact_path = Path(artifact_name)
    if not artifact_path.is_absolute():
        artifact_path = json_path.parent / artifact_path
    if not artifact_path.exists():
        return None

    try:
        with np.load(artifact_path, allow_pickle=False) as data:
            if not all(key in data.files for key in REQUIRED_ARTIFACT_KEYS):
                return None
            return {key: torch.from_numpy(np.array(data[key])) for key in REQUIRED_ARTIFACT_KEYS}
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("[session_artifacts] Could not load session artifact: {}", exc)
        return None


def load_batch_sample_session_tensors(
    batch_data: dict[str, Any],
    sample_idx: int,
) -> dict[str, torch.Tensor] | None:
    """Load artifact tensors for a one-based sample index in a batch queue entry."""
    audio_path = _batch_audio_path(batch_data, sample_idx)
    return load_session_artifacts(audio_path)


def artifact_to_alignment_tensors(
    artifact: dict[str, torch.Tensor] | None,
) -> dict[str, torch.Tensor] | None:
    """Convert loaded artifact tensors to the score/LRC alignment naming."""
    if not artifact or not all(key in artifact for key in REQUIRED_ARTIFACT_KEYS):
        return None
    return {
        "pred_latent": artifact["pred_latents"],
        "encoder_hidden_states": artifact["encoder_hidden_states"],
        "encoder_attention_mask": artifact["encoder_attention_mask"],
        "context_latents": artifact["context_latents"],
        "lyric_token_ids": artifact["lyric_token_ids"],
    }


def get_audio_codes_from_sidecar(path: str | os.PathLike[str] | None) -> str | None:
    """Return generated audio codes from a JSON sidecar when available."""
    json_path = _find_json_sidecar(path)
    if json_path is None:
        return None
    codes = _load_json(json_path).get("audio_codes")
    if isinstance(codes, str) and codes.strip():
        return codes
    return None


def _sample_tensor_to_numpy(value: Any, sample_idx: int) -> np.ndarray | None:
    """Return one batch sample tensor as a CPU numpy array."""
    if not isinstance(value, torch.Tensor):
        return None
    if sample_idx < 0 or sample_idx >= value.shape[0]:
        return None
    sample = value[sample_idx:sample_idx + 1].detach().cpu()
    if sample.dtype == torch.bfloat16:
        sample = sample.float()
    return sample.numpy()


def _find_json_sidecar(path: str | os.PathLike[str] | None) -> Path | None:
    """Resolve an audio path to its generated JSON sidecar when present."""
    if path is None:
        return None
    base = Path(path)
    candidates = []
    if base.suffix.lower() == ".json":
        candidates.append(base)
    else:
        candidates.append(base.with_suffix(".json"))
    candidates.extend(_gradio_output_json_candidates(base))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _gradio_output_json_candidates(base: Path) -> list[Path]:
    """Return newest matching JSON sidecars under ``gradio_outputs``."""
    if base.suffix.lower() == ".json":
        return []
    results_root = Path.cwd() / "gradio_outputs"
    if not results_root.exists():
        return []
    filename = base.with_suffix(".json").name
    candidates = list(results_root.glob(f"batch_*/{glob.escape(filename)}"))
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON sidecar as a dictionary."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[session_artifacts] Could not read JSON sidecar {}: {}", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _batch_audio_path(batch_data: dict[str, Any], sample_idx: int) -> str | None:
    """Return the audio path for a one-based sample index."""
    audio_paths = batch_data.get("audio_paths", [])
    audio_only = [
        path for path in audio_paths
        if isinstance(path, str) and Path(path).suffix.lower() != ".json"
    ]
    idx0 = sample_idx - 1
    if 0 <= idx0 < len(audio_only):
        return audio_only[idx0]
    return None
