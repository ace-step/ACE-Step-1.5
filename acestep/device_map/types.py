"""Datatypes describing GPUs and per-component device layouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from acestep.device_map.devices import device_index_label, normalize_component_device
from acestep.device_map.constants import COMPONENT_KEYS


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
        if key not in COMPONENT_KEYS:
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
