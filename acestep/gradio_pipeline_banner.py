"""GPU configuration banner printed at Gradio demo startup."""

from __future__ import annotations

from typing import Any

from acestep.gpu_config import VRAM_AUTO_OFFLOAD_THRESHOLD_GB


def print_gpu_banner(
    gpu_config: Any,
    gpu_memory_gb: float,
    is_mac: bool,
    auto_offload: bool,
    default_backend: str,
) -> None:
    """Print the detected GPU configuration summary used at Gradio startup."""
    print(f"\n{'=' * 60}")
    print("GPU Configuration Detected:")
    print(f"{'=' * 60}")
    print(f"  GPU Memory: {gpu_memory_gb:.2f} GB")
    print(f"  Configuration Tier: {gpu_config.tier}")
    print(
        f"  Max Duration (with LM): {gpu_config.max_duration_with_lm}s "
        f"({gpu_config.max_duration_with_lm // 60} min)"
    )
    print(
        f"  Max Duration (without LM): {gpu_config.max_duration_without_lm}s "
        f"({gpu_config.max_duration_without_lm // 60} min)"
    )
    print(f"  Max Batch Size (with LM): {gpu_config.max_batch_size_with_lm}")
    print(f"  Max Batch Size (without LM): {gpu_config.max_batch_size_without_lm}")
    print(f"  Default LM Init: {gpu_config.init_lm_default}")
    print(f"  Available LM Models: {gpu_config.available_lm_models or 'None'}")
    print(f"{'=' * 60}\n")
    if is_mac:
        print(
            f"Apple Silicon (MPS) detected — unified memory {gpu_memory_gb:.1f}GB, "
            f"no CPU offload needed, backend={default_backend}"
        )
    elif auto_offload:
        print(
            f"Auto-enabling CPU offload (GPU {gpu_memory_gb:.1f}GB < "
            f"{VRAM_AUTO_OFFLOAD_THRESHOLD_GB}GB threshold)"
        )
    elif gpu_memory_gb > 0:
        print(
            f"CPU offload disabled by default (GPU {gpu_memory_gb:.1f}GB >= "
            f"{VRAM_AUTO_OFFLOAD_THRESHOLD_GB}GB threshold)"
        )
    else:
        print("No GPU detected, running on CPU")
