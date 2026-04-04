"""GPU-tier-driven UI update helpers for generation service controls."""

import gradio as gr
from loguru import logger

from acestep.gpu_config import (
    GPU_TIER_CONFIGS,
    GPU_TIER_LABELS,
    find_best_lm_model_on_disk,
    get_gpu_config_for_tier,
    set_global_gpu_config,
)
from acestep.ui.gradio.i18n import t


def on_tier_change(selected_tier, llm_handler=None):
    """Handle manual tier override from the UI dropdown."""

    if not selected_tier or selected_tier not in GPU_TIER_CONFIGS:
        logger.warning(f"Invalid tier selection: {selected_tier}")
        return (gr.update(),) * 10

    new_config = get_gpu_config_for_tier(selected_tier)
    set_global_gpu_config(new_config)
    logger.info(f"🔄 Tier manually changed to {selected_tier} — updating UI defaults")

    if new_config.lm_backend_restriction == "pt_only":
        available_backends = ["pt"]
    elif new_config.lm_backend_restriction == "pt_mlx_only":
        available_backends = ["pt", "mlx"]
    else:
        available_backends = ["vllm", "pt", "mlx"]
    if "external" not in available_backends:
        available_backends.append("external")
    recommended_backend = new_config.recommended_backend
    if recommended_backend not in available_backends:
        recommended_backend = available_backends[0]

    all_disk_models = llm_handler.get_available_5hz_lm_models() if llm_handler else []
    recommended_lm = new_config.recommended_lm_model
    default_lm_model = find_best_lm_model_on_disk(recommended_lm, all_disk_models)

    max_duration = new_config.max_duration_without_lm
    max_batch = new_config.max_batch_size_without_lm

    tier_label = GPU_TIER_LABELS.get(selected_tier, selected_tier)
    from acestep.gpu_config import get_gpu_device_name

    gpu_info_text = (
        f"🖥️ **{get_gpu_device_name()}** — {new_config.gpu_memory_gb:.1f} GB VRAM "
        f"— {t('service.gpu_auto_tier')}: **{tier_label}**"
    )
    recommended_suffix = " (recommended for this tier)"

    return (
        gr.update(
            value=new_config.offload_to_cpu_default,
            info=t("service.offload_cpu_info")
            + (recommended_suffix if new_config.offload_to_cpu_default else ""),
            elem_classes=["has-info-container"],
        ),
        gr.update(
            value=new_config.offload_dit_to_cpu_default,
            info=t("service.offload_dit_cpu_info")
            + (recommended_suffix if new_config.offload_dit_to_cpu_default else ""),
            elem_classes=["has-info-container"],
        ),
        gr.update(value=new_config.compile_model_default),
        gr.update(
            value=new_config.quantization_default,
            info=t("service.quantization_info")
            + (recommended_suffix if new_config.quantization_default else ""),
            elem_classes=["has-info-container"],
        ),
        gr.update(choices=available_backends, value=recommended_backend, elem_classes=["has-info-container"]),
        gr.update(
            choices=all_disk_models,
            value=default_lm_model,
            info=t("service.lm_model_path_info")
            + (
                f" (Recommended: {recommended_lm})"
                if recommended_lm
                else " (LM not available for this GPU tier)."
            ),
            elem_classes=["has-info-container"],
        ),
        gr.update(value=new_config.init_lm_default, elem_classes=["has-info-container"]),
        gr.update(
            value=min(2, max_batch),
            maximum=max_batch,
            info=f"Number of samples to generate (Max: {max_batch}).",
            elem_classes=["has-info-container"],
        ),
        gr.update(
            maximum=float(max_duration),
            info=f"Duration in seconds (-1 for auto). Max: {max_duration}s / {max_duration // 60} min.",
            elem_classes=["has-info-container"],
        ),
        gr.update(value=gpu_info_text),
    )
