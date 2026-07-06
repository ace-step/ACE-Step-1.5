"""
Component-level device placement for multi-GPU inference.

Supports explicit mappings, single-GPU parity, and automatic layout across
multiple CUDA devices when ``gpu_mapping=auto``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from loguru import logger

from acestep.gpu_config import (
    DIT_INFERENCE_VRAM_PER_BATCH,
    LM_VRAM,
    MODEL_VRAM,
    VRAM_SAFETY_MARGIN_GB,
    get_dit_type_from_path,
    get_lm_model_size,
)

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


@dataclass(frozen=True)
class LayoutRequest:
    """Inputs used to compute an automatic multi-GPU layout."""

    gpus: List[GpuInfo]
    dit_type: str = "turbo"
    lm_model_path: Optional[str] = None
    use_lm: bool = True
    batch_size: int = 1


@dataclass(frozen=True)
class LayoutError:
    """Returned when automatic layout cannot place all requested components."""

    message: str
    suggestions: Tuple[str, ...] = field(default_factory=tuple)


def _dit_model_vram_key(dit_type: str) -> str:
    if dit_type.startswith("dit_"):
        return dit_type
    return f"dit_{dit_type}"


def estimate_dit_peak_gb(dit_type: str, batch_size: int) -> float:
    """Estimate DiT GPU memory including co-located VAE and text encoder."""
    model_key = _dit_model_vram_key(dit_type)
    weights = MODEL_VRAM.get(model_key, MODEL_VRAM["dit_turbo"])
    per_batch = DIT_INFERENCE_VRAM_PER_BATCH.get(
        dit_type,
        DIT_INFERENCE_VRAM_PER_BATCH["turbo"],
    )
    aux = (
        MODEL_VRAM["vae"]
        + MODEL_VRAM["text_encoder"]
        + MODEL_VRAM["cuda_context"]
        + VRAM_SAFETY_MARGIN_GB
    )
    return weights + (per_batch * max(1, batch_size)) + aux


def estimate_lm_total_gb(lm_model_path: Optional[str]) -> float:
    """Estimate LM weights plus KV cache on the target GPU."""
    model_size = get_lm_model_size(lm_model_path or "acestep-5Hz-lm-1.7B")
    lm_info = LM_VRAM.get(model_size, LM_VRAM["0.6B"])
    return lm_info["weights"] + lm_info["kv_cache_4k"] + 0.3


def _sort_gpus_for_layout(gpus: List[GpuInfo]) -> List[GpuInfo]:
    return sorted(
        gpus,
        key=lambda gpu: (-gpu.free_vram_gb, -gpu.total_vram_gb, gpu.logical_index),
    )


def compute_auto_device_map(request: LayoutRequest) -> Union[ComponentDeviceMap, LayoutError]:
    """Place components across visible CUDA devices based on free VRAM."""
    gpus = _sort_gpus_for_layout(request.gpus)
    if not gpus:
        return LayoutError(
            "No CUDA devices detected for auto layout",
            suggestions=("Install CUDA drivers or pass an explicit --gpu-mapping",),
        )

    dit_need_gb = estimate_dit_peak_gb(request.dit_type, request.batch_size)
    dit_gpu = next((gpu for gpu in gpus if gpu.free_vram_gb >= dit_need_gb), None)
    if dit_gpu is None:
        return LayoutError(
            f"No GPU has {dit_need_gb:.1f}GB free for DiT ({request.dit_type})",
            suggestions=(
                "Reduce batch size",
                "Use a smaller DiT checkpoint",
                "Enable CPU offload",
                "Pass an explicit gpu mapping",
            ),
        )

    dit_device = f"cuda:{dit_gpu.logical_index}"
    lm_device = None
    if request.use_lm:
        lm_need_gb = estimate_lm_total_gb(request.lm_model_path)
        lm_candidates = [gpu for gpu in gpus if gpu.logical_index != dit_gpu.logical_index]
        lm_candidates.extend(gpu for gpu in gpus if gpu.logical_index == dit_gpu.logical_index)
        lm_gpu = next((gpu for gpu in lm_candidates if gpu.free_vram_gb >= lm_need_gb), None)
        if lm_gpu is None:
            return LayoutError(
                f"No GPU has {lm_need_gb:.1f}GB free for LM ({request.lm_model_path or 'default'})",
                suggestions=(
                    "Use a smaller LM model",
                    "Pass gpu_mapping with lm on a specific GPU",
                    "Disable LM initialization",
                ),
            )
        lm_device = f"cuda:{lm_gpu.logical_index}"

    return ComponentDeviceMap(
        dit=dit_device,
        vae=dit_device,
        text_encoder=dit_device,
        lm=lm_device,
    )


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

    Returns None when mapping is unset or explicitly set to 'auto'.
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


def _raw_gpu_mapping_value(gpu_mapping: Optional[str]) -> str:
    raw = (gpu_mapping or "").strip()
    if not raw:
        raw = os.environ.get(GPU_MAPPING_ENV, "").strip()
    return raw


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
    raw_mapping = _raw_gpu_mapping_value(gpu_mapping)

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
