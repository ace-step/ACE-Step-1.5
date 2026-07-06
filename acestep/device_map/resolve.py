"""Resolve the effective component layout for service initialization."""

from __future__ import annotations

import os
from typing import Optional

from loguru import logger

from acestep.gpu_config import get_dit_type_from_path

from acestep.device_map.devices import is_cuda_device, normalize_component_device
from acestep.device_map.discovery import discover_gpus
from acestep.device_map.layout import compute_auto_device_map
from acestep.device_map.parsing import parse_gpu_mapping, raw_gpu_mapping_value
from acestep.device_map.types import ComponentDeviceMap, LayoutRequest


def resolve_component_device_map(
    *,
    requested_device: str,
    gpu_mapping: Optional[str] = None,
    config_path: Optional[str] = None,
    lm_model_path: Optional[str] = None,
    use_lm: bool = True,
    batch_size: int = 1,
) -> ComponentDeviceMap:
    """
    Resolve the effective component device map for service initialization.

    When no mapping is provided, all components share ``requested_device``.
    When mapping is ``auto`` and multiple CUDA devices are visible, compute a
    VRAM-aware layout; otherwise fall back to single-device placement.
    """
    normalized_device = normalize_component_device(requested_device)
    raw_mapping = raw_gpu_mapping_value(gpu_mapping)

    if raw_mapping.lower() == "auto" and is_cuda_device(normalized_device):
        gpus = discover_gpus()
        if len(gpus) >= 2:
            dit_type = get_dit_type_from_path(config_path or "")
            layout = compute_auto_device_map(
                LayoutRequest(
                    gpus=gpus,
                    dit_type=dit_type,
                    lm_model_path=lm_model_path,
                    use_lm=use_lm,
                    batch_size=batch_size,
                )
            )
            if isinstance(layout, ComponentDeviceMap):
                logger.info("[device_map] Auto layout selected from {} GPU(s)", len(gpus))
                return layout
            logger.warning(
                "[device_map] Auto layout failed: {}. Suggestions: {}",
                layout.message,
                "; ".join(layout.suggestions),
            )

    parsed = parse_gpu_mapping(gpu_mapping, default_device=normalized_device)
    if parsed is None:
        return ComponentDeviceMap.from_single_device(normalized_device)
    return parsed


def log_device_map(device_map: ComponentDeviceMap) -> None:
    """Emit a startup log line describing the active component layout."""
    logger.info("[device_map] Active layout: {}", device_map.summary())
    if device_map.is_multi_device():
        logger.info("[device_map] Multi-device placement enabled with cross-GPU routing")
