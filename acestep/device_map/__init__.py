"""
Component-level device placement for multi-GPU inference.

Public API facade — import from ``acestep.device_map`` as before.
"""

from acestep.device_map.constants import GPU_MAPPING_ENV, LM_DEVICE_ENV
from acestep.device_map.devices import (
    cuda_device_index,
    device_index_label,
    device_type,
    is_cuda_device,
    normalize_component_device,
    set_active_cuda_device,
)
from acestep.device_map.discovery import discover_gpus, format_gpu_list_text
from acestep.device_map.errors import DeviceMapError
from acestep.device_map.layout import (
    compute_auto_device_map,
    estimate_dit_peak_gb,
    estimate_lm_total_gb,
)
from acestep.device_map.parsing import parse_gpu_mapping
from acestep.device_map.resolve import log_device_map, resolve_component_device_map
from acestep.device_map.status import (
    collect_gpu_runtime_status,
    device_map_to_dict,
    gpu_info_to_dict,
    log_lm_device_deprecation,
)
from acestep.device_map.types import (
    ComponentDeviceMap,
    GpuInfo,
    LayoutError,
    LayoutRequest,
)

__all__ = [
    "GPU_MAPPING_ENV",
    "LM_DEVICE_ENV",
    "ComponentDeviceMap",
    "DeviceMapError",
    "GpuInfo",
    "LayoutError",
    "LayoutRequest",
    "collect_gpu_runtime_status",
    "compute_auto_device_map",
    "cuda_device_index",
    "device_index_label",
    "device_map_to_dict",
    "device_type",
    "discover_gpus",
    "estimate_dit_peak_gb",
    "estimate_lm_total_gb",
    "format_gpu_list_text",
    "gpu_info_to_dict",
    "is_cuda_device",
    "log_device_map",
    "log_lm_device_deprecation",
    "normalize_component_device",
    "parse_gpu_mapping",
    "resolve_component_device_map",
    "set_active_cuda_device",
]
