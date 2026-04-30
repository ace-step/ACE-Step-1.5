"""Utilities for dynamic multi-device component mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger  # type: ignore[reportMissingImports]

try:
    import torch  # type: ignore[reportMissingImports]
except ImportError:  # pragma: no cover - fallback for minimal environments
    torch = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ComponentDeviceMap:
    """Normalized component-to-device mapping."""

    dit: Optional[str] = None
    vae: Optional[str] = None
    lm: Optional[str] = None


def _rank_cuda_devices_by_free_vram() -> list[int]:
    """Return CUDA device indices sorted by descending free VRAM."""
    if torch is None or not torch.cuda.is_available():
        return []

    device_count = torch.cuda.device_count()
    free_by_device: list[tuple[int, int]] = []
    for idx in range(device_count):
        free_bytes = 0
        try:
            free_bytes = int(torch.cuda.mem_get_info(idx)[0])
        except RuntimeError as exc:
            logger.debug(
                "[device_mapping] mem_get_info({}) failed ({}); retrying with device context.",
                idx,
                exc,
            )
            try:
                with torch.cuda.device(idx):
                    free_bytes = int(torch.cuda.mem_get_info()[0])
            except RuntimeError as exc2:
                logger.warning(
                    "[device_mapping] Unable to query free VRAM for cuda:{} ({}); ranking it last.",
                    idx,
                    exc2,
                )
                free_bytes = 0
        free_by_device.append((idx, free_bytes))
    free_by_device.sort(key=lambda pair: pair[1], reverse=True)
    return [idx for idx, _free in free_by_device]


def resolve_component_device_map() -> ComponentDeviceMap:
    """Auto-populate component mapping from currently available CUDA devices."""
    if torch is None or not torch.cuda.is_available():
        return ComponentDeviceMap()

    ranked = _rank_cuda_devices_by_free_vram()
    if not ranked:
        return ComponentDeviceMap()

    dit_idx = ranked[0]
    vae_idx = ranked[1] if len(ranked) > 1 else ranked[0]
    lm_idx = ranked[2] if len(ranked) > 2 else ranked[-1]
    return ComponentDeviceMap(
        dit=f"cuda:{dit_idx}",
        vae=f"cuda:{vae_idx}",
        lm=f"cuda:{lm_idx}",
    )


def format_component_gpu_hint_text(
    *,
    default_device: str = "auto",
    label: str = "Component GPU hint",
) -> str:
    """Format component placement hint for UI display.

    Returns an empty string when all components resolve to the same final device,
    which avoids noisy UI on non-CUDA and single-device hosts.
    """
    mapping = resolve_component_device_map()
    resolved_devices = [
        mapping.dit or default_device,
        mapping.vae or default_device,
        mapping.lm or default_device,
    ]
    if len(set(resolved_devices)) == 1:
        return ""

    return (
        f"{label}: "
        f"DiT={resolved_devices[0]}, "
        f"VAE={resolved_devices[1]}, "
        f"LM={resolved_devices[2]}"
    )


def validate_component_device_map(mapping: ComponentDeviceMap) -> None:
    """Validate that mapped CUDA indices exist on the current host.

    Args:
        mapping: Component-to-device mapping to validate.

    Raises:
        ValueError: If any ``cuda:<idx>`` entry references an index out of range
            for visible CUDA devices.
    """
    cuda_count = torch.cuda.device_count() if torch is not None and torch.cuda.is_available() else 0
    for component, device in (
        ("dit", mapping.dit),
        ("vae", mapping.vae),
        ("lm", mapping.lm),
    ):
        if not device or not device.startswith("cuda:"):
            continue
        try:
            idx = int(device.split(":", 1)[1])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid {component} device '{device}': expected 'cuda:<int>' with "
                f"0 <= idx < {cuda_count}."
            ) from exc
        if idx < 0 or idx >= cuda_count:
            raise ValueError(
                f"Invalid {component} device '{device}': only {cuda_count} CUDA device(s) available."
            )