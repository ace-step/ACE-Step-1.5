"""Utilities for dynamic multi-device component mapping.

Based on PR #1149 (imsarang) — extended with explicit environment-variable
overrides (ACESTEP_DIT_DEVICE / ACESTEP_VAE_DEVICE / ACESTEP_LM_DEVICE) so that
users of asymmetric multi-GPU rigs can pin each component deterministically
(e.g. DiT on the fast card, LM on the second card).
"""

from __future__ import annotations

import os
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


def _env_device_overrides() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Read explicit per-component device overrides from the environment."""
    def _norm(val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        val = val.strip()
        return val or None

    return (
        _norm(os.getenv("ACESTEP_DIT_DEVICE")),
        _norm(os.getenv("ACESTEP_VAE_DEVICE")),
        _norm(os.getenv("ACESTEP_LM_DEVICE")),
    )


def resolve_component_device_map() -> ComponentDeviceMap:
    """Auto-populate component mapping from available CUDA devices.

    Explicit env overrides (ACESTEP_DIT_DEVICE / ACESTEP_VAE_DEVICE /
    ACESTEP_LM_DEVICE) take precedence over the free-VRAM auto-ranking, allowing
    deterministic pinning on asymmetric multi-GPU setups.
    """
    env_dit, env_vae, env_lm = _env_device_overrides()

    if torch is None or not torch.cuda.is_available():
        if env_dit or env_vae or env_lm:
            return ComponentDeviceMap(dit=env_dit, vae=env_vae, lm=env_lm)
        return ComponentDeviceMap()

    ranked = _rank_cuda_devices_by_free_vram()
    if not ranked:
        if env_dit or env_vae or env_lm:
            return ComponentDeviceMap(dit=env_dit, vae=env_vae, lm=env_lm)
        return ComponentDeviceMap()

    dit_idx = ranked[0]
    vae_idx = ranked[1] if len(ranked) > 1 else ranked[0]
    lm_idx = ranked[2] if len(ranked) > 2 else ranked[-1]

    return ComponentDeviceMap(
        dit=env_dit or f"cuda:{dit_idx}",
        vae=env_vae or f"cuda:{vae_idx}",
        lm=env_lm or f"cuda:{lm_idx}",
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
