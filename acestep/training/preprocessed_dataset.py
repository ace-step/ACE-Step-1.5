"""Preprocessed tensor dataset for ACE-Step LoRA/full fine-tuning."""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import torch
from loguru import logger
from torch.utils.data import Dataset

from acestep.training.path_safety import safe_path


class PreprocessedTensorDataset(Dataset):
    """Dataset that loads preprocessed tensor files for training."""

    def __init__(self, tensor_dir: str, cache_policy: str = "none", cache_max_items: int = 0):
        """Initialize dataset from preprocessed tensor directory.

        Args:
            tensor_dir: Directory containing preprocessed ``.pt`` samples.
            cache_policy: Cache mode ("none" or "ram_lru"). Defaults to "none".
            cache_max_items: Max samples kept in RAM when ``cache_policy='ram_lru'``.
                ``0`` disables RAM caching.

        Raises:
            ValueError: If *tensor_dir* is invalid or escapes safe root.
        """
        validated_dir = safe_path(tensor_dir)
        if not os.path.isdir(validated_dir):
            raise ValueError(f"Not an existing directory: {tensor_dir}")

        self.tensor_dir = validated_dir
        self.sample_paths: List[str] = []
        self.cache_policy = cache_policy
        self.cache_max_items = max(0, int(cache_max_items))
        self._cache: "OrderedDict[int, Dict[str, Any]]" = OrderedDict()

        manifest_path = safe_path("manifest.json", base=self.tensor_dir)
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            for raw in manifest.get("samples", []):
                resolved = self._resolve_manifest_path(raw)
                if resolved is not None:
                    self.sample_paths.append(resolved)
        else:
            for filename in os.listdir(self.tensor_dir):
                if filename.endswith(".pt") and filename != "manifest.json":
                    self.sample_paths.append(safe_path(filename, base=self.tensor_dir))

        self.valid_paths = [p for p in self.sample_paths if os.path.exists(p)]
        if len(self.valid_paths) != len(self.sample_paths):
            logger.warning(
                "Some tensor files not found: %d missing",
                len(self.sample_paths) - len(self.valid_paths),
            )

        self.latent_lengths: List[int] = []
        for vp in self.valid_paths:
            try:
                sample = torch.load(vp, map_location="cpu", weights_only=True)
                self.latent_lengths.append(int(sample["target_latents"].shape[0]))
            except (FileNotFoundError, PermissionError, EOFError, OSError, KeyError, RuntimeError) as exc:
                logger.warning("Failed to read latent length from %s: %s", vp, exc)
                self.latent_lengths.append(0)

        logger.info("PreprocessedTensorDataset: %d samples from %s", len(self.valid_paths), self.tensor_dir)

    def _resolve_manifest_path(self, raw: str) -> Optional[str]:
        """Resolve and validate manifest sample path."""
        try:
            candidate = safe_path(raw, base=self.tensor_dir)
            if os.path.exists(candidate):
                return candidate
        except ValueError:
            pass

        try:
            candidate = safe_path(raw)
            if os.path.exists(candidate):
                logger.debug("Resolved legacy manifest path via safe root: %s", raw)
                return candidate
        except ValueError:
            pass

        logger.warning("Skipping unresolvable manifest path: %s", raw)
        return None

    def __len__(self) -> int:
        return len(self.valid_paths)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        """Load one preprocessed sample."""
        if self.cache_policy == "ram_lru" and idx in self._cache:
            data = self._cache.pop(idx)
            self._cache[idx] = data
        else:
            data = torch.load(self.valid_paths[idx], map_location="cpu", weights_only=True)
            if self.cache_policy == "ram_lru" and self.cache_max_items > 0:
                self._cache[idx] = data
                while len(self._cache) > self.cache_max_items:
                    self._cache.popitem(last=False)

        return {
            "target_latents": data["target_latents"],
            "attention_mask": data["attention_mask"],
            "encoder_hidden_states": data["encoder_hidden_states"],
            "encoder_attention_mask": data["encoder_attention_mask"],
            "context_latents": data["context_latents"],
            "metadata": data.get("metadata", {}),
        }
