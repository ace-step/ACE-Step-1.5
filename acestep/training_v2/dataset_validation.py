"""Dataset validation utilities for preprocessed training tensors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import torch


REQUIRED_KEYS = (
    "target_latents",
    "attention_mask",
    "encoder_hidden_states",
    "encoder_attention_mask",
    "context_latents",
)


def _has_nonfinite(tensors: List[torch.Tensor]) -> bool:
    """Return True if any tensor contains NaN or Inf values."""
    return any(not torch.isfinite(t).all() for t in tensors if isinstance(t, torch.Tensor))


def validate_preprocessed_dataset(dataset_dir: str) -> Dict[str, Any]:
    """Validate a preprocessed dataset directory and return summary stats."""
    root = Path(dataset_dir)
    files = sorted(p for p in root.glob("*.pt") if p.name != "manifest.json")

    valid = 0
    invalid = 0
    nonfinite = 0
    lengths: List[int] = []
    errors: List[str] = []

    for file_path in files:
        try:
            data = torch.load(str(file_path), map_location="cpu", weights_only=True)
            missing = [k for k in REQUIRED_KEYS if k not in data]
            if missing:
                invalid += 1
                errors.append(f"{file_path.name}: missing keys {missing}")
                continue

            tensors = [data[k] for k in REQUIRED_KEYS]
            if _has_nonfinite(tensors):
                nonfinite += 1

            latent_len = int(data["target_latents"].shape[0])
            lengths.append(latent_len)
            valid += 1
        except Exception as exc:  # explicit diagnostic handling
            invalid += 1
            errors.append(f"{file_path.name}: {exc}")

    avg_len = float(sum(lengths) / max(len(lengths), 1))
    return {
        "total_samples": len(files),
        "valid_samples": valid,
        "invalid_samples": invalid,
        "nan_or_inf_samples": nonfinite,
        "min_latent_length": min(lengths) if lengths else 0,
        "max_latent_length": max(lengths) if lengths else 0,
        "avg_latent_length": avg_len,
        "errors": errors,
    }
