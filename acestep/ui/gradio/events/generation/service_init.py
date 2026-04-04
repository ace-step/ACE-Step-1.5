"""Service initialization helpers for generation handlers."""

import os
import sys

import gradio as gr
from loguru import logger

from acestep.gpu_config import get_global_gpu_config, is_lm_model_size_allowed, resolve_lm_backend
from acestep.text_tasks.external_lm_providers import get_external_provider_profile
from acestep.text_tasks.external_lm_runtime_store import (
    load_external_lm_runtime_settings,
    save_external_lm_runtime_settings,
)
from acestep.ui.gradio.i18n import t

from .model_config import (
    get_model_type_ui_settings,
    is_pure_base_model,
    is_sft_model,
    is_xl_model,
)
from .service_init_helpers import (
    build_post_init_result,
    configure_external_llm,
    resolve_project_root,
    select_quantization_value,
)
from .service_tier_updates import on_tier_change


def refresh_checkpoints(dit_handler):
    """Refresh available checkpoints."""
    choices = dit_handler.get_available_checkpoints()
    return gr.update(choices=choices)


def _select_quantization_value(
    *,
    quantization_enabled: bool,
    device: str,
) -> str | None:
    """Return the DiT quantization mode selected for the current UI state."""

    return select_quantization_value(
        quantization_enabled=quantization_enabled,
        device=device,
    )


def update_llm_backend_ui(backend: str, init_llm_checked: bool, local_init_llm_state: bool):
    """Toggle local/external LM widgets based on the selected backend."""

    is_external = (backend or "").strip().lower() == "external"
    info_key = "service.init_llm_info_external" if is_external else "service.init_llm_info"
    remembered_local_value = bool(local_init_llm_state)
    checkbox_update = (
        gr.update(info=t(info_key), value=True)
        if is_external
        else gr.update(info=t(info_key), value=remembered_local_value)
    )
    next_local_init_llm_state = bool(init_llm_checked) if is_external else remembered_local_value
    return (
        gr.update(visible=not is_external),
        gr.Accordion(visible=True, open=is_external),
        checkbox_update,
        next_local_init_llm_state,
    )


def hydrate_external_lm_provider_fields(provider: str):
    """Load saved non-secret runtime settings for the selected provider."""

    try:
        profile = get_external_provider_profile(provider)
    except ValueError:
        return gr.update(), gr.update()

    stored = load_external_lm_runtime_settings(profile.provider_id) or {}
    model = str(stored.get("model", "")).strip() or profile.default_model
    base_url = str(stored.get("base_url", "")).strip() or profile.default_base_url
    return gr.update(value=model), gr.update(value=base_url)


def init_service_wrapper(
    dit_handler,
    llm_handler,
    checkpoint,
    config_path,
    device,
    init_llm,
    lm_model_path,
    backend,
    external_llm_provider="",
    external_llm_model="",
    external_llm_base_url="",
    external_llm_api_key="",
    use_flash_attention=False,
    offload_to_cpu=False,
    offload_dit_to_cpu=False,
    compile_model=False,
    quantization=False,
    mlx_dit=True,
    current_mode=None,
    current_batch_size=None,
):
    """Wrapper for service initialization."""
    quant_value = _select_quantization_value(
        quantization_enabled=quantization,
        device=device,
    )

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

    normalized_backend = (backend or "").strip().lower()
    external_profile = None
    if normalized_backend == "external":
        external_profile = get_external_provider_profile(external_llm_provider)

    if init_llm and normalized_backend != "external":
        if not gpu_config.available_lm_models:
            logger.warning(
                f"⚠️ GPU tier {gpu_config.tier} ({gpu_config.gpu_memory_gb:.1f}GB) does not support LM on GPU. "
                "Falling back to CPU for LM initialization."
            )
            lm_device = "cpu"
        else:
            lm_device = device

    if init_llm and normalized_backend != "external" and lm_model_path and gpu_config.available_lm_models:
        if not is_lm_model_size_allowed(lm_model_path, gpu_config.available_lm_models):
            logger.warning(
                f"⚠️ LM model {lm_model_path} is not in the recommended list for tier {gpu_config.tier} "
                f"(recommended: {gpu_config.available_lm_models}). Proceeding with user selection — "
                f"this may cause high VRAM usage or OOM."
            )

    if normalized_backend != "external":
        resolved_backend = resolve_lm_backend(backend, gpu_config)
    else:
        resolved_backend = normalized_backend
    if init_llm and normalized_backend != "external" and resolved_backend != backend:
        backend = resolved_backend
        logger.warning(
            f"⚠️ Requested LM backend is not supported for tier {gpu_config.tier} "
            f"on this hardware, falling back to {backend}"
        )

    current_file = os.path.abspath(__file__)
    project_root = resolve_project_root(current_file)

    status, enable = dit_handler.initialize_service(
        project_root,
        config_path,
        device,
        use_flash_attention=use_flash_attention,
        compile_model=compile_model,
        offload_to_cpu=offload_to_cpu,
        offload_dit_to_cpu=offload_dit_to_cpu,
        quantization=quant_value,
        use_mlx_dit=mlx_dit,
    )

    if init_llm and normalized_backend == "external":
        provider = (
            external_profile.provider_id
            if external_profile is not None
            else (external_llm_provider or "").strip().lower()
        )
        model = (external_llm_model or "").strip() or (
            external_profile.default_model if external_profile is not None else ""
        )
        base_url = (external_llm_base_url or "").strip() or (
            external_profile.default_base_url if external_profile is not None else ""
        )
        status = configure_external_llm(
            llm_handler=llm_handler,
            profile=external_profile,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=(external_llm_api_key or "").strip(),
            save_runtime_settings=save_external_lm_runtime_settings,
            status=status,
        )
    elif init_llm:
        checkpoint_dir = os.path.join(project_root, "checkpoints")

        lm_status, _lm_success = llm_handler.initialize(
            checkpoint_dir=checkpoint_dir,
            lm_model_path=lm_model_path,
            backend=backend,
            device=lm_device,
            offload_to_cpu=offload_to_cpu,
            dtype=None,
        )

        status += f"\n{lm_status}"

    config_path_lower = (config_path or "").lower()
    if is_xl_model(config_path_lower) and gpu_config is not None:
        gpu_mem = getattr(gpu_config, "gpu_memory_gb", 0)
        if 0 < gpu_mem < 16:
            gr.Warning(
                f"XL (4B) model requires ≥16GB VRAM (detected {gpu_mem:.0f}GB). "
                "Consider using a 2B model, or enable CPU offload."
            )

    return build_post_init_result(
        dit_handler=dit_handler,
        llm_handler=llm_handler,
        config_path=config_path,
        current_mode=current_mode,
        current_batch_size=current_batch_size,
        status=status,
        enable=enable,
        get_gpu_config_fn=get_global_gpu_config,
        get_model_type_ui_settings_fn=get_model_type_ui_settings,
        is_pure_base_model_fn=is_pure_base_model,
        is_sft_model_fn=is_sft_model,
    )
