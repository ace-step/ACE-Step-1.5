"""Catalog and capability helpers for initialization flow."""

import os
from typing import List, Optional

import torch
from loguru import logger


class InitServiceCatalogMixin:
    """Checkpoint discovery and backend capability helpers."""

    def _device_type(self) -> str:
        """Normalize the host device value to a backend type string."""
        if isinstance(self.device, str):
            return self.device.split(":", 1)[0]
        return self.device.type

    def get_available_checkpoints(self) -> List[str]:
        """Return available checkpoint directory paths under the project root."""
        project_root = self._get_project_root()
        checkpoint_dir = os.path.join(project_root, "checkpoints")
        if os.path.exists(checkpoint_dir):
            return [checkpoint_dir]
        return []

    def get_available_acestep_v15_models(self) -> List[str]:
        """Scan and return all model directory names starting with ``acestep-v15-``."""
        project_root = self._get_project_root()
        checkpoint_dir = os.path.join(project_root, "checkpoints")

        models = []
        if os.path.exists(checkpoint_dir):
            for item in os.listdir(checkpoint_dir):
                item_path = os.path.join(checkpoint_dir, item)
                if os.path.isdir(item_path) and item.startswith("acestep-v15-"):
                    models.append(item)

        models.sort()
        return models

    def is_flash_attention_available(self, device: Optional[str] = None) -> bool:
        """Check whether flash attention can be used on the target device."""
        target_device = str(device or self.device or "auto").split(":", 1)[0]
        if target_device == "auto":
            if not torch.cuda.is_available():
                return False
        else:
            if target_device != "cuda" or not torch.cuda.is_available():
                return False

        try:
            major, _ = torch.cuda.get_device_capability()
            if major < 8:
                logger.info(
                    f"[is_flash_attention_available] GPU compute capability {major}.x < 8.0 "
                    f"(pre-Ampere) — FlashAttention not supported, will use SDPA instead."
                )
                return False
        except Exception:
            return False

        try:
            import flash_attn
            return True
        except ImportError:
            return False

    def is_turbo_model(self) -> bool:
        """Check whether the currently loaded model is a turbo variant."""
        if self.config is None:
            return False
        return getattr(self.config, "is_turbo", False)
