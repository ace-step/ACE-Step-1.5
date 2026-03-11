"""Service initialization and tier management for generation handlers.

Contains functions for initializing the DiT/LLM services, refreshing
checkpoints, and handling GPU tier changes.
"""

import os
import sys
import gradio as gr
from loguru import logger

from acestep.ui.gradio.i18n import t
from acestep.gpu_config import (
    get_global_gpu_config, is_lm_model_size_allowed, find_best_lm_model_on_disk,
    get_gpu_config_for_tier, set_global_gpu_config, GPU_TIER_LABELS, GPU_TIER_CONFIGS,
)
from .model_config import is_pure_base_model, get_model_type_ui_settings


def refresh_checkpoints(dit_handler):
    """Refresh available checkpoints."""
    choices = dit_handler.get_available_checkpoints()
    return gr.update(choices=choices)


def init_service_wrapper(
    dit_handler, llm_handler, checkpoint, config_path, device,
    init_llm, lm_model_path, backend, use_flash_attention,
    offload_to_cpu, offload_dit_to_cpu, compile_model, quantization,
    mlx_dit=True, current_mode=None, current_batch_size=None,
):
    """Wrapper for service initialization.

    Returns status, button state, accordion state, model type settings,
    and GPU-config-aware UI limits.

    Args:
        current_batch_size: Current batch size value from UI to preserve
            after reinitialization (optional).
    """
    quant_value = "int8_weight_only" if quantization else None

    gpu_config = get_global_gpu_config()

    if sys.platform == "darwin":
        if compile_model:
            logger.info(
                "macOS detected: torch.compile not supported; compilation "
                "will use mx.compile via MLX."
            )
        if quantization:
            logger.info("macOS detected: disabling INT8 quantization (torchao incompatible with MPS)")
            quantization = False
            quant_value = None

    # Compute lm_device only when initializing the LLM to avoid overwriting a
    # previously-resolved device (e.g. "cuda") with the raw UI value ("auto").
    # "auto" is resolved to the concrete device inside llm_handler.initialize().
    if init_llm:
        if not gpu_config.available_lm_models:
            logger.warning(
                f"⚠️ GPU tier {gpu_config.tier} ({gpu_config.gpu_memory_gb:.1f}GB) does not support LM on GPU. "
                "Falling back to CPU for LM initialization."
            )
            lm_device = "cpu"
        else:
            lm_device = device

    if init_llm and lm_model_path and gpu_config.available_lm_models:
        if not is_lm_model_size_allowed(lm_model_path, gpu_config.available_lm_models):
            logger.warning(
                f"⚠️ LM model {lm_model_path} is not in the recommended list for tier {gpu_config.tier} "
                f"(recommended: {gpu_config.available_lm_models}). Proceeding with user selection — "
                f"this may cause high VRAM usage or OOM."
            )

    if init_llm and gpu_config.lm_backend_restriction == "pt_mlx_only" and backend == "vllm":
        backend = gpu_config.recommended_backend
        logger.warning(
            f"⚠️ vllm backend not supported for tier {gpu_config.tier} "
            f"(VRAM too low for KV cache), falling back to {backend}"
        )

    # Derive project_root from the checkpoint path (which is the checkpoints
    # directory itself, e.g. "<project>/checkpoints").  Passing it directly as
    # project_root would cause initialize_service to append "checkpoints" again,
    # resulting in "<project>/checkpoints/checkpoints".
    current_file = os.path.abspath(__file__)
    # This file is in acestep/ui/gradio/events/generation/
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(current_file))))))

    status, enable = dit_handler.initialize_service(
        project_root, config_path, device,
        use_flash_attention=use_flash_attention, compile_model=compile_model,
        offload_to_cpu=offload_to_cpu, offload_dit_to_cpu=offload_dit_to_cpu,
        quantization=quant_value, use_mlx_dit=mlx_dit,
    )

    if init_llm:
        checkpoint_dir = os.path.join(project_root, "checkpoints")

        lm_status, lm_success = llm_handler.initialize(
            checkpoint_dir=checkpoint_dir,
            lm_model_path=lm_model_path,
            backend=backend,
            device=lm_device,
            offload_to_cpu=offload_to_cpu,
            dtype=None,
        )

        if lm_success:
            status += f"\n{lm_status}"
        else:
            status += f"\n{lm_status}"

    is_model_initialized = dit_handler.model is not None
    accordion_state = gr.Accordion(open=not is_model_initialized)

    is_turbo = dit_handler.is_turbo_model()
    is_pure_base = is_pure_base_model((config_path or "").lower())
    model_type_settings = get_model_type_ui_settings(
        is_turbo, current_mode=current_mode, is_pure_base=is_pure_base,
    )

    gpu_config = get_global_gpu_config()
    lm_actually_initialized = llm_handler.llm_initialized if llm_handler else False
    max_duration = gpu_config.max_duration_with_lm if lm_actually_initialized else gpu_config.max_duration_without_lm
    max_batch = gpu_config.max_batch_size_with_lm if lm_actually_initialized else gpu_config.max_batch_size_without_lm

    duration_update = gr.update(
        maximum=float(max_duration),
        info=f"Duration in seconds (-1 for auto). Max: {max_duration}s / {max_duration // 60} min.",
        elem_classes=["has-info-container"],
    )

    if current_batch_size is not None:
        try:
            batch_value_int = int(current_batch_size)
            if batch_value_int >= 1:
                batch_value = min(batch_value_int, max_batch)
                if batch_value_int > max_batch:
                    logger.warning(f"Batch size {batch_value_int} exceeds GPU limit {max_batch}, clamping to {batch_value}")
            else:
                logger.warning(f"Invalid batch size {batch_value_int} (must be >= 1), using default {min(2, max_batch)}")
                batch_value = min(2, max_batch)
        except ValueError:
            logger.warning(f"Cannot convert batch size '{current_batch_size}' to integer, using default {min(2, max_batch)}")
            batch_value = min(2, max_batch)
        except TypeError:
            logger.warning(f"Invalid batch size type {type(current_batch_size).__name__}, using default {min(2, max_batch)}")
            batch_value = min(2, max_batch)
    else:
        batch_value = min(2, max_batch)

    batch_update = gr.update(
        value=batch_value, maximum=max_batch,
        info=f"Number of samples to generate (Max: {max_batch}).",
        elem_classes=["has-info-container"],
    )

    status += f"\n📊 GPU Config: tier={gpu_config.tier}, max_duration={max_duration}s, max_batch={max_batch}"
    if gpu_config.available_lm_models:
        status += f", available_lm={gpu_config.available_lm_models}"
    else:
        status += ", LM not available for this GPU tier"

    think_interactive = lm_actually_initialized

    return (
        status,
        gr.update(interactive=enable),
        accordion_state,
        *model_type_settings,
        duration_update,
        batch_update,
        gr.update(interactive=think_interactive, value=think_interactive),
    )


def on_tier_change(selected_tier, llm_handler=None):
    """Handle manual tier override from the UI dropdown.

    Updates the global GPU config and returns gr.update() for all
    affected UI components so they reflect the new tier's defaults.

    Returns a tuple of gr.update() objects for:
        (offload_to_cpu, offload_dit_to_cpu, compile_model, quantization,
         backend_dropdown, lm_model_path, init_llm, batch_size_input,
         audio_duration, gpu_info_display)
    """
    if not selected_tier or selected_tier not in GPU_TIER_CONFIGS:
        logger.warning(f"Invalid tier selection: {selected_tier}")
        return (gr.update(),) * 10

    new_config = get_gpu_config_for_tier(selected_tier)
    set_global_gpu_config(new_config)
    logger.info(f"🔄 Tier manually changed to {selected_tier} — updating UI defaults")

    if new_config.lm_backend_restriction == "pt_mlx_only":
        available_backends = ["pt", "mlx"]
    else:
        available_backends = ["vllm", "pt", "mlx"]
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
    _gpu_device_name = get_gpu_device_name()
    gpu_info_text = (
        f"🖥️ **{_gpu_device_name}** — {new_config.gpu_memory_gb:.1f} GB VRAM "
        f"— {t('service.gpu_auto_tier')}: **{tier_label}**"
    )

    return (
        gr.update(
            value=new_config.offload_to_cpu_default,
            info=t("service.offload_cpu_info") + (" (recommended for this tier)" if new_config.offload_to_cpu_default else ""),
            elem_classes=["has-info-container"],
        ),
        gr.update(
            value=new_config.offload_dit_to_cpu_default,
            info=t("service.offload_dit_cpu_info") + (" (recommended for this tier)" if new_config.offload_dit_to_cpu_default else ""),
            elem_classes=["has-info-container"],
        ),
        gr.update(value=new_config.compile_model_default),
        gr.update(
            value=new_config.quantization_default,
            info=t("service.quantization_info") + (" (recommended for this tier)" if new_config.quantization_default else ""),
            elem_classes=["has-info-container"],
        ),
        gr.update(choices=available_backends, value=recommended_backend, elem_classes=["has-info-container"]),
        gr.update(
            choices=all_disk_models, value=default_lm_model,
            info=t("service.lm_model_path_info") + (f" (Recommended: {recommended_lm})" if recommended_lm else " (LM not available for this GPU tier)."),
            elem_classes=["has-info-container"],
        ),
        gr.update(value=new_config.init_lm_default, elem_classes=["has-info-container"]),
        gr.update(
            value=min(2, max_batch), maximum=max_batch,
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
