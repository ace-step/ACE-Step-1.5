"""CLI/API status serialization and deprecation helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from loguru import logger

from acestep.device_map.constants import GPU_MAPPING_ENV, LM_DEVICE_ENV
from acestep.device_map.discovery import discover_gpus
from acestep.device_map.types import ComponentDeviceMap, GpuInfo


def gpu_info_to_dict(gpu: GpuInfo) -> Dict[str, object]:
    """Serialize a :class:`GpuInfo` record for CLI and API responses."""
    payload: Dict[str, object] = {
        "index": gpu.logical_index,
        "name": gpu.name,
        "total_vram_gb": gpu.total_vram_gb,
        "free_vram_gb": gpu.free_vram_gb,
    }
    if gpu.compute_capability is not None:
        payload["compute_capability"] = list(gpu.compute_capability)
    return payload


def device_map_to_dict(device_map: ComponentDeviceMap) -> Dict[str, object]:
    """Serialize an active component layout for status endpoints."""
    return {
        "dit": device_map.dit,
        "vae": device_map.vae,
        "text_encoder": device_map.text_encoder,
        "lm": device_map.lm,
        "lm_tensor_parallel": device_map.lm_tensor_parallel,
        "summary": device_map.summary(),
        "multi_device": device_map.is_multi_device(),
    }


def collect_gpu_runtime_status(handler: Any = None) -> Dict[str, object]:
    """Collect GPU inventory and the active component layout for API status."""
    gpus = [gpu_info_to_dict(gpu) for gpu in discover_gpus()]
    device_map = getattr(handler, "device_map", None) if handler is not None else None
    mapping_env = os.environ.get(GPU_MAPPING_ENV, "").strip() or None
    return {
        "gpus": gpus,
        "gpu_mapping": mapping_env,
        "device_map": device_map_to_dict(device_map) if device_map is not None else None,
    }


def log_lm_device_deprecation(
    *,
    explicit_lm_device: Optional[str] = None,
    gpu_mapping_env: Optional[str] = None,
    using_device_map_lm: bool = False,
) -> None:
    """Warn when legacy ``ACESTEP_LM_DEVICE`` should be replaced by gpu mapping."""
    explicit = (explicit_lm_device or os.getenv(LM_DEVICE_ENV, "")).strip()
    if not explicit:
        return

    mapping = (gpu_mapping_env or os.environ.get(GPU_MAPPING_ENV, "")).strip()
    if mapping and using_device_map_lm:
        logger.warning(
            "[device_map] ACESTEP_LM_DEVICE={} is ignored because {}={} "
            "assigns the LM device. Use 'lm:N' in the mapping instead.",
            explicit,
            GPU_MAPPING_ENV,
            mapping,
        )
        return

    if not mapping:
        logger.warning(
            "[device_map] ACESTEP_LM_DEVICE is deprecated; use {} instead "
            "(e.g. 'single:1' or 'dit:0,vae:0,text_encoder:0,lm:1'). Current value: {}",
            GPU_MAPPING_ENV,
            explicit,
        )
