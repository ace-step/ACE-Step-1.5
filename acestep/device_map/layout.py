"""VRAM-aware automatic multi-GPU layout."""

from __future__ import annotations

from typing import List, Optional, Union

from acestep.gpu_config import (
    DIT_INFERENCE_VRAM_PER_BATCH,
    LM_VRAM,
    MODEL_VRAM,
    VRAM_SAFETY_MARGIN_GB,
    get_lm_model_size,
)

from acestep.device_map.types import ComponentDeviceMap, GpuInfo, LayoutError, LayoutRequest


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


def _lm_free_vram_gb(gpu: GpuInfo, dit_gpu: GpuInfo, dit_need_gb: float) -> float:
    """Return free VRAM on *gpu* available for LM after reserving the DiT stack."""
    if gpu.logical_index != dit_gpu.logical_index:
        return gpu.free_vram_gb
    return max(0.0, gpu.free_vram_gb - dit_need_gb)


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
        lm_gpu = next(
            (
                gpu
                for gpu in lm_candidates
                if _lm_free_vram_gb(gpu, dit_gpu, dit_need_gb) >= lm_need_gb
            ),
            None,
        )
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
