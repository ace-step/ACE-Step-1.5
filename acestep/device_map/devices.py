"""Device-string normalization and CUDA helpers."""

from __future__ import annotations

from acestep.device_map.errors import DeviceMapError


def device_type(device: str) -> str:
    """Return the backend type token from a device string."""
    return str(device).split(":", 1)[0]


def cuda_device_index(device: str) -> int:
    """Return the CUDA device index for a device string."""
    normalized = str(device)
    if normalized == "cuda":
        return 0
    if normalized.startswith("cuda:"):
        suffix = normalized.split(":", 1)[1]
        try:
            return int(suffix)
        except ValueError as exc:
            raise DeviceMapError(f"Not a CUDA device string: {device!r}") from exc
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
