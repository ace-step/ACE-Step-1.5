"""
GPU Detection, VRAM Query, and Estimation Budget Calculation

Provides:
    detect_gpu()            -- auto-detect best available accelerator
    get_available_vram_mb() -- query free VRAM on the selected device
    estimate_batch_budget() -- compute how many estimation batches fit in VRAM
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import torch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------

@dataclass
class GPUInfo:
    """Describes the detected accelerator."""

    device: str
    """Torch device string, e.g. 'cuda:0', 'mps', 'xpu', 'cpu'."""

    device_type: str
    """Canonical type: 'cuda', 'mps', 'xpu', 'cpu'."""

    name: str
    """Human-readable device name."""

    vram_total_mb: Optional[float] = None
    """Total device memory in MiB (None for CPU / unknown)."""

    vram_free_mb: Optional[float] = None
    """Free device memory in MiB (None for CPU / unknown)."""

    precision: str = "fp32"
    """Recommended precision for this device."""

    def __str__(self) -> str:
        parts = [f"device={self.device}", f"name={self.name}"]
        if self.vram_total_mb is not None:
            parts.append(f"vram_total={self.vram_total_mb:.0f}MiB")
        if self.vram_free_mb is not None:
            parts.append(f"vram_free={self.vram_free_mb:.0f}MiB")
        parts.append(f"precision={self.precision}")
        return "GPUInfo(" + ", ".join(parts) + ")"


def detect_gpu(requested_device: str = "auto", requested_precision: str = "auto") -> GPUInfo:
    """Detect the best available accelerator.

    Priority: CUDA > MPS > XPU > CPU.

    Args:
        requested_device: 'auto', 'cuda', 'cuda:N', 'mps', 'xpu', 'cpu'.
        requested_precision: 'auto', 'bf16', 'fp16', 'fp32'.

    Returns:
        GPUInfo with device string, name, VRAM stats, and recommended precision.
    """
    device_type: str
    device_str: str
    name: str
    vram_total: Optional[float] = None
    vram_free: Optional[float] = None

    if requested_device == "auto":
        if torch.cuda.is_available():
            device_str = "cuda:0"
            device_type = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device_str = "mps"
            device_type = "mps"
        elif hasattr(torch, "xpu") and torch.xpu.is_available():
            device_str = "xpu:0"
            device_type = "xpu"
        else:
            device_str = "cpu"
            device_type = "cpu"
    else:
        device_str = requested_device
        device_type = requested_device.split(":")[0]

    # Resolve name + VRAM
    if device_type == "cuda":
        idx = 0
        if ":" in device_str:
            idx = int(device_str.split(":")[1])
        name = torch.cuda.get_device_name(idx)
        vram_total = torch.cuda.get_device_properties(idx).total_memory / (1024 ** 2)
        vram_free = _cuda_free_mb(idx)
    elif device_type == "mps":
        name = "Apple MPS"
    elif device_type == "xpu":
        idx = 0
        if ":" in device_str:
            idx = int(device_str.split(":")[1])
        name = f"Intel XPU:{idx}"
        if hasattr(torch.xpu, "get_device_properties"):
            props = torch.xpu.get_device_properties(idx)
            vram_total = getattr(props, "total_memory", 0) / (1024 ** 2)
    else:
        name = "CPU"

    # Resolve precision
    if requested_precision == "auto":
        if device_type in ("cuda", "xpu"):
            precision = "bf16"
        elif device_type == "mps":
            precision = "fp16"
        else:
            precision = "fp32"
    else:
        precision = requested_precision

    return GPUInfo(
        device=device_str,
        device_type=device_type,
        name=name,
        vram_total_mb=vram_total,
        vram_free_mb=vram_free,
        precision=precision,
    )


# ---------------------------------------------------------------------------
# VRAM helpers
# ---------------------------------------------------------------------------

def _cuda_free_mb(idx: int = 0) -> float:
    """Return free CUDA memory in MiB for device *idx*."""
    torch.cuda.synchronize(idx)
    free, _total = torch.cuda.mem_get_info(idx)
    return free / (1024 ** 2)


def get_available_vram_mb(device: str = "auto") -> Optional[float]:
    """Query free VRAM on the given device.

    Returns None when VRAM cannot be determined (CPU / MPS).
    """
    info = detect_gpu(requested_device=device)
    return info.vram_free_mb


# ---------------------------------------------------------------------------
# Estimation batch budget
# ---------------------------------------------------------------------------

# Rough per-batch memory estimates for a single forward+backward pass through
# the DiT decoder with all parameters requiring gradients.
# These are *very* conservative upper bounds.
_BYTES_PER_BATCH_2B_BF16: float = 1200.0  # ~1.2 GiB per sample (24 layers, hidden_size=2048)
_BYTES_PER_BATCH_XL_BF16: float = 2000.0  # ~2.0 GiB per sample (32 layers, hidden_size=2560)

# Model weight VRAM offsets (MiB) subtracted before estimating batch budget.
_WEIGHT_OFFSET_2B: float = 4096.0   # ~4 GiB for 2B decoder weights
_WEIGHT_OFFSET_XL: float = 6000.0   # ~6 GiB for XL (4B) decoder weights


def get_gpu_info(device: str = "auto") -> dict:
    """Return GPU info as a flat dict suitable for TUI widgets.

    Keys: name, vram_used_gb, vram_total_gb, utilization, temperature, power.
    Missing values are returned as 0.
    """
    try:
        info = detect_gpu(requested_device=device)
        total_mb = info.vram_total_mb or 0
        free_mb = info.vram_free_mb or 0
        used_mb = max(0, total_mb - free_mb)
        return {
            "name": info.name,
            "vram_used_gb": used_mb / 1024,
            "vram_total_gb": total_mb / 1024,
            "utilization": 0,  # nvidia-smi would be needed for live util
            "temperature": 0,
            "power": 0,
        }
    except Exception:
        return {
            "name": "Unknown",
            "vram_used_gb": 0,
            "vram_total_gb": 0,
            "utilization": 0,
            "temperature": 0,
            "power": 0,
        }


def estimate_batch_budget(
    device: str = "auto",
    safety_factor: float = 0.8,
    min_batches: int = 4,
    max_batches: int = 64,
    variant: str = "",
) -> int:
    """Estimate how many estimation batches fit in available VRAM.

    Args:
        device: Device string or 'auto'.
        safety_factor: Fraction of free VRAM to use (0-1).
        min_batches: Floor value.
        max_batches: Ceiling value.
        variant: Model variant (e.g. "turbo", "xl_base"). XL variants use
                 larger weight and per-batch estimates.

    Returns:
        Number of estimation batches (clamped to [min_batches, max_batches]).
    """
    free_mb = get_available_vram_mb(device)
    if free_mb is None:
        logger.info("[INFO] VRAM unknown -- using minimum batch budget of %d", min_batches)
        return min_batches

    is_xl = variant.startswith("xl") if variant else False
    weight_offset = _WEIGHT_OFFSET_XL if is_xl else _WEIGHT_OFFSET_2B
    per_batch = _BYTES_PER_BATCH_XL_BF16 if is_xl else _BYTES_PER_BATCH_2B_BF16

    usable_mb = free_mb * safety_factor
    usable_mb = max(0.0, usable_mb - weight_offset)
    raw_batches = int(usable_mb / per_batch) if per_batch > 0 else 0
    # Only apply min_batches floor when there is actual headroom;
    # if usable VRAM is exhausted, clamp to 1 to avoid OOM.
    lower_bound = 1 if raw_batches == 0 else min_batches
    n_batches = max(lower_bound, min(raw_batches, max_batches))

    logger.info(
        "[INFO] Estimation budget: %d batches (%.0f MiB free, %.0f MiB usable)",
        n_batches,
        free_mb,
        usable_mb,
    )
    return n_batches
