"""Shared defaults/helpers for generation interface builders."""

import sys
from typing import Any

from acestep.gpu_config import GPUConfig, get_global_gpu_config
from acestep.ui.gradio.events.generation_handlers import is_pure_base_model


def compute_init_defaults(
    init_params: dict[str, Any] | None,
    language: str,
) -> dict[str, Any]:
    """Compute normalized defaults shared by generation interface sections.

    Args:
        init_params: Optional startup parameters passed to the UI layer.
        language: Fallback language code when no language is present in init params.

    Returns:
        A dictionary with computed service, GPU, and control-default values.
    """

    service_pre_initialized = init_params is not None and init_params.get("pre_initialized", False)
    service_mode = init_params is not None and init_params.get("service_mode", False)
    current_language = init_params.get("language", language) if init_params else language

    gpu_config: GPUConfig | None = init_params.get("gpu_config") if init_params else None
    if gpu_config is None:
        gpu_config = get_global_gpu_config()

    lm_initialized = init_params.get("init_llm", False) if init_params else False
    max_duration = (
        gpu_config.max_duration_with_lm
        if lm_initialized
        else gpu_config.max_duration_without_lm
    )
    max_batch_size = (
        gpu_config.max_batch_size_with_lm
        if lm_initialized
        else gpu_config.max_batch_size_without_lm
    )

    cli_batch_size = (init_params or {}).get("default_batch_size")
    if cli_batch_size is not None:
        default_batch_size = min(cli_batch_size, max_batch_size)
    else:
        default_batch_size = min(2, max_batch_size)

    init_lm_default = gpu_config.init_lm_default
    default_offload = gpu_config.offload_to_cpu_default
    default_offload_dit = gpu_config.offload_dit_to_cpu_default

    try:
        import torch

        if hasattr(torch, "xpu") and torch.xpu.is_available():
            default_offload = False
            default_offload_dit = False
    except ImportError:
        pass

    default_quantization = gpu_config.quantization_default
    default_compile = gpu_config.compile_model_default
    if sys.platform == "darwin":
        default_quantization = False
        default_compile = False

    if gpu_config.lm_backend_restriction == "pt_mlx_only":
        available_backends = ["pt", "mlx"]
    else:
        available_backends = ["vllm", "pt", "mlx"]
    recommended_backend = gpu_config.recommended_backend
    if recommended_backend not in available_backends:
        recommended_backend = available_backends[0]

    return {
        "service_pre_initialized": service_pre_initialized,
        "service_mode": service_mode,
        "current_language": current_language,
        "gpu_config": gpu_config,
        "lm_initialized": lm_initialized,
        "max_duration": max_duration,
        "max_batch_size": max_batch_size,
        "default_batch_size": default_batch_size,
        "init_lm_default": init_lm_default,
        "default_offload": default_offload,
        "default_offload_dit": default_offload_dit,
        "default_quantization": default_quantization,
        "default_compile": default_compile,
        "available_backends": available_backends,
        "recommended_backend": recommended_backend,
        "recommended_lm": gpu_config.recommended_lm_model,
    }


def resolve_is_pure_base_model(
    dit_handler: Any,
    init_params: dict[str, Any] | None,
    service_pre_initialized: bool,
) -> bool:
    """Resolve whether current model selection should use pure-base mode behavior.

    Args:
        dit_handler: DiT handler used to inspect available model names.
        init_params: Optional startup parameters that may include selected config path.
        service_pre_initialized: Whether service was already initialized before UI render.

    Returns:
        ``True`` when the selected model should use base-only generation mode options.
    """

    if service_pre_initialized and init_params and "dit_handler" in init_params:
        config_path = init_params.get("config_path", "")
        return is_pure_base_model((config_path or "").lower())

    available_models = dit_handler.get_available_acestep_v15_models()
    default_model = (
        "acestep-v15-turbo"
        if "acestep-v15-turbo" in available_models
        else (available_models[0] if available_models else None)
    )
    actual_model = init_params.get("config_path", default_model) if init_params else default_model
    return is_pure_base_model((actual_model or "").lower())
