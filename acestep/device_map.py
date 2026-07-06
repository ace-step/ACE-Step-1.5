"""
Component-level device placement for multi-GPU inference.

PR1 scope: parse explicit mappings, discover GPUs, and resolve per-component
device strings. Auto-layout across multiple GPUs is deferred to PR2.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from loguru import logger

GPU_MAPPING_ENV = "ACESTEP_GPU_MAPPING"

_COMPONENT_KEYS = ("dit", "vae", "text_encoder", "lm")
_SINGLE_PATTERN = re.compile(r"^single:(\d+)$")
_PAIR_PATTERN = re.compile(r"^([a-z_]+):(\d+)$")


@dataclass(frozen=True)
class GpuInfo:
    """Describes one visible CUDA device using logical indices."""

    logical_index: int
    name: str
    total_vram_gb: float
    free_vram_gb: float
    compute_capability: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class ComponentDeviceMap:
    """Per-component runtime device strings for inference."""

    dit: str
    vae: str
    text_encoder: str
    lm: Optional[str] = None
    lm_tensor_parallel: int = 1

    def device_for(self, component: str) -> str:
        """Return the resolved device string for a component key."""
        key = component.strip().lower()
        if key == "model":
            key = "dit"
        if key not in _COMPONENT_KEYS:
            raise KeyError(f"Unknown component: {component}")
        value = getattr(self, key)
        if value is None:
            raise ValueError(f"Component '{component}' has no assigned device")
        return value

    def is_multi_device(self) -> bool:
        """Return True when components target more than one distinct device."""
        devices = {self.dit, self.vae, self.text_encoder}
        if self.lm is not None:
            devices.add(self.lm)
        return len(devices) > 1

    def summary(self) -> str:
        """Return a compact human-readable layout description."""
        parts = [
            f"dit:{device_index_label(self.dit)}",
            f"vae:{device_index_label(self.vae)}",
            f"text_encoder:{device_index_label(self.text_encoder)}",
        ]
        if self.lm is not None:
            parts.append(f"lm:{device_index_label(self.lm)}")
        if self.lm_tensor_parallel > 1:
            parts.append(f"lm_tp={self.lm_tensor_parallel}")
        return ", ".join(parts)

    @classmethod
    def from_single_device(cls, device: str) -> "ComponentDeviceMap":
        """Place all inference components on one device."""
        normalized = normalize_component_device(device)
        return cls(
            dit=normalized,
            vae=normalized,
            text_encoder=normalized,
            lm=normalized,
        )


class DeviceMapError(ValueError):
    """Raised when a GPU mapping string cannot be parsed or validated."""


def device_type(device: str) -> str:
    """Return the backend type token from a device string."""
    return str(device).split(":", 1)[0]


def cuda_device_index(device: str) -> int:
    """Return the CUDA device index for a device string."""
    normalized = str(device)
    if normalized == "cuda":
        return 0
    if normalized.startswith("cuda:"):
        return int(normalized.split(":", 1)[1])
    raise DeviceMapError(f"Not a CUDA device string: {device!r}")


def is_cuda_device(device: str) -> bool:
    """Return whether *device* refers to a CUDA backend."""
    return device_type(device) == "cuda"


def normalize_component_device(device: str) -> str:
    """Normalize device strings used for component placement."""
    value = str(device).strip()
    if not value:
        raise DeviceMapError("Device string cannot be empty")
    if value == "cuda":
        return "cuda:0"
    return value


def device_index_label(device: str) -> str:
    """Return a short index label for logs/UI."""
    if is_cuda_device(device):
        return str(cuda_device_index(device))
    return device_type(device)


def set_active_cuda_device(device: str) -> None:
    """Set the active CUDA device when loading or running on a specific GPU."""
    if not is_cuda_device(device):
        return
    import torch

    if not torch.cuda.is_available():
        return
    index = cuda_device_index(device)
    torch.cuda.set_device(index)


def discover_gpus() -> List[GpuInfo]:
    """Enumerate visible CUDA devices and their current VRAM stats."""
    import torch

    if not torch.cuda.is_available():
        return []

    gpus: List[GpuInfo] = []
    for index in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(index)
        free_bytes, total_bytes = torch.cuda.mem_get_info(index)
        try:
            capability = torch.cuda.get_device_capability(index)
        except Exception:
            capability = None
        gpus.append(
            GpuInfo(
                logical_index=index,
                name=props.name,
                total_vram_gb=round(total_bytes / (1024**3), 2),
                free_vram_gb=round(free_bytes / (1024**3), 2),
                compute_capability=capability,
            )
        )
    return gpus


def _format_device_for_backend(backend: str, index: int) -> str:
    if backend == "cuda":
        return f"cuda:{index}"
    if backend in {"mps", "xpu", "cpu"}:
        if index != 0:
            raise DeviceMapError(
                f"Component index {index} is invalid for backend '{backend}'"
            )
        return backend if backend != "xpu" else "xpu:0"
    raise DeviceMapError(f"Unsupported backend for component mapping: {backend!r}")


def _parse_mapping_pairs(mapping: str) -> Dict[str, int]:
    pairs: Dict[str, int] = {}
    for raw_part in mapping.split(","):
        part = raw_part.strip()
        if not part:
            continue
        match = _PAIR_PATTERN.fullmatch(part)
        if match is None:
            raise DeviceMapError(
                f"Invalid mapping segment {part!r}; expected 'component:index'"
            )
        component, index_text = match.group(1), match.group(2)
        if component not in _COMPONENT_KEYS:
            raise DeviceMapError(
                f"Unknown component {component!r}; expected one of {_COMPONENT_KEYS}"
            )
        if component in pairs:
            raise DeviceMapError(f"Duplicate component entry: {component!r}")
        pairs[component] = int(index_text)
    if not pairs:
        raise DeviceMapError("GPU mapping must include at least one component")
    return pairs


def parse_gpu_mapping(
    mapping: Optional[str],
    *,
    default_device: str,
) -> Optional[ComponentDeviceMap]:
    """
    Parse a GPU mapping string into a component device map.

    Returns None when mapping is unset or set to 'auto' (PR1 legacy behavior).
    """
    raw = (mapping or "").strip()
    if not raw:
        raw = os.environ.get(GPU_MAPPING_ENV, "").strip()
    if not raw or raw.lower() == "auto":
        return None

    backend = device_type(default_device)
    if backend not in {"cuda", "mps", "xpu", "cpu"}:
        backend = "cuda" if is_cuda_device(default_device) else device_type(default_device)

    single_match = _SINGLE_PATTERN.fullmatch(raw)
    if single_match is not None:
        index = int(single_match.group(1))
        device = _format_device_for_backend(backend, index)
        return ComponentDeviceMap.from_single_device(device)

    pairs = _parse_mapping_pairs(raw)
    dit_index = pairs.get("dit")
    if dit_index is None:
        raise DeviceMapError("Explicit GPU mapping must include a 'dit' component")

    dit_device = _format_device_for_backend(backend, dit_index)
    vae_device = _format_device_for_backend(backend, pairs.get("vae", dit_index))
    text_encoder_device = _format_device_for_backend(
        backend,
        pairs.get("text_encoder", dit_index),
    )
    lm_device = None
    if "lm" in pairs:
        lm_device = _format_device_for_backend(backend, pairs["lm"])

    return ComponentDeviceMap(
        dit=dit_device,
        vae=vae_device,
        text_encoder=text_encoder_device,
        lm=lm_device,
    )


def resolve_component_device_map(
    *,
    requested_device: str,
    gpu_mapping: Optional[str] = None,
) -> ComponentDeviceMap:
    """
    Resolve the effective component device map for service initialization.

    When no mapping is provided, all components share ``requested_device``.
    """
    normalized_device = normalize_component_device(requested_device)
    parsed = parse_gpu_mapping(gpu_mapping, default_device=normalized_device)
    if parsed is None:
        return ComponentDeviceMap.from_single_device(normalized_device)
    return parsed


def log_device_map(device_map: ComponentDeviceMap) -> None:
    """Emit a startup log line describing the active component layout."""
    logger.info("[device_map] Active layout: {}", device_map.summary())
    if device_map.is_multi_device():
        logger.info(
            "[device_map] Multi-device placement enabled; "
            "cross-GPU inference routing arrives in PR2"
        )
