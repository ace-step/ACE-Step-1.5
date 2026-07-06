"""CUDA device discovery helpers."""

from __future__ import annotations

from typing import List, Optional

from acestep.device_map.types import GpuInfo


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


def format_gpu_list_text(gpus: Optional[List[GpuInfo]] = None) -> str:
    """Return a human-readable table of visible CUDA devices."""
    visible = gpus if gpus is not None else discover_gpus()
    if not visible:
        return "No CUDA devices detected."

    lines = [
        "Visible CUDA devices:",
        "  idx  name                          total(GB)  free(GB)  compute",
    ]
    for gpu in visible:
        capability = ""
        if gpu.compute_capability is not None:
            capability = f"{gpu.compute_capability[0]}.{gpu.compute_capability[1]}"
        lines.append(
            "  {idx:>3}  {name:<28}  {total:>8.2f}  {free:>7.2f}  {capability}".format(
                idx=gpu.logical_index,
                name=gpu.name[:28],
                total=gpu.total_vram_gb,
                free=gpu.free_vram_gb,
                capability=capability or "-",
            )
        )
    return "\n".join(lines)
