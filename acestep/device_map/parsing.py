"""GPU mapping string parsing."""

from __future__ import annotations

import os
from typing import Dict, Optional

from acestep.device_map.constants import COMPONENT_KEYS, GPU_MAPPING_ENV, PAIR_PATTERN, SINGLE_PATTERN
from acestep.device_map.devices import device_type
from acestep.device_map.errors import DeviceMapError
from acestep.device_map.types import ComponentDeviceMap


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
        match = PAIR_PATTERN.fullmatch(part)
        if match is None:
            raise DeviceMapError(
                f"Invalid mapping segment {part!r}; expected 'component:index'"
            )
        component, index_text = match.group(1), match.group(2)
        if component not in COMPONENT_KEYS:
            raise DeviceMapError(
                f"Unknown component {component!r}; expected one of {COMPONENT_KEYS}"
            )
        if component in pairs:
            raise DeviceMapError(f"Duplicate component entry: {component!r}")
        pairs[component] = int(index_text)
    if not pairs:
        raise DeviceMapError("GPU mapping must include at least one component")
    return pairs


_SUPPORTED_MAPPING_BACKENDS = frozenset({"cuda", "mps", "xpu", "cpu"})


def _resolve_mapping_backend(default_device: str) -> str:
    """Return the backend token used to interpret explicit GPU indices."""
    backend = device_type(default_device)
    if backend in _SUPPORTED_MAPPING_BACKENDS:
        return backend
    raise DeviceMapError(
        f"Unsupported default device {default_device!r} for GPU mapping; "
        "expected cuda, mps, xpu, or cpu"
    )


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

    backend = _resolve_mapping_backend(default_device)

    single_match = SINGLE_PATTERN.fullmatch(raw)
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


def raw_gpu_mapping_value(gpu_mapping: Optional[str]) -> str:
    """Return the effective raw mapping string from args or environment."""
    raw = (gpu_mapping or "").strip()
    if not raw:
        raw = os.environ.get(GPU_MAPPING_ENV, "").strip()
    return raw
