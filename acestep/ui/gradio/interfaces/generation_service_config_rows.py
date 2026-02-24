"""Row builders for generation service configuration section."""

from typing import Any

import gradio as gr

from acestep.gpu_config import (
    GPU_TIER_LABELS,
    find_best_lm_model_on_disk,
    get_gpu_device_name,
)
from acestep.ui.gradio.i18n import t, available_languages_info


def build_language_selector(current_language: str) -> dict[str, Any]:
    """Create the service-language selector row.

    Args:
        current_language: Preselected UI language code.

    Returns:
        A component map containing the ``language_dropdown`` control.
    """

    with gr.Row():
        language_dropdown = gr.Dropdown(
            choices=[(native_name + f" ({name})" if name != native_name else name, code) for code, name, native_name in available_languages_info()],
            value=current_language,
            label=t("service.language_label"),
            info=t("service.language_info"),
            interactive=True,
            elem_classes=["has-info-container"],
            scale=1,
        )
    return {"language_dropdown": language_dropdown}


def build_gpu_info_and_tier(gpu_config: Any) -> dict[str, Any]:
    """Create GPU info display and manual tier override controls.

    Args:
        gpu_config: Active GPU configuration object with tier and VRAM metadata.

    Returns:
        A component map containing ``gpu_info_display`` and ``tier_dropdown``.
    """

    gpu_text = (
        f"\U0001f5a5\ufe0f **{get_gpu_device_name()}** \u2014 {gpu_config.gpu_memory_gb:.1f} GB VRAM "
        f"\u2014 {t('service.gpu_auto_tier')}: **{GPU_TIER_LABELS.get(gpu_config.tier, gpu_config.tier)}**"
    )
    with gr.Row():
        gpu_info_display = gr.Markdown(value=gpu_text)
    with gr.Row():
        tier_dropdown = gr.Dropdown(
            choices=[(label, key) for key, label in GPU_TIER_LABELS.items()],
            value=gpu_config.tier,
            label=t("service.tier_label"),
            info=t("service.tier_info"),
            elem_classes=["has-info-container"],
            scale=1,
        )
    return {"gpu_info_display": gpu_info_display, "tier_dropdown": tier_dropdown}


def build_checkpoint_controls(dit_handler: Any, service_pre_initialized: bool, params: dict[str, Any]) -> dict[str, Any]:
    """Create checkpoint selection and refresh controls.

    Args:
        dit_handler: DiT handler used to list available checkpoints.
        service_pre_initialized: Whether existing init params should prefill values.
        params: Startup state dictionary containing optional checkpoint value.

    Returns:
        A component map containing ``checkpoint_dropdown`` and ``refresh_btn``.
    """

    with gr.Row(equal_height=True):
        with gr.Column(scale=4):
            checkpoint_dropdown = gr.Dropdown(
                label=t("service.checkpoint_label"),
                choices=dit_handler.get_available_checkpoints(),
                value=params.get("checkpoint") if service_pre_initialized else None,
                info=t("service.checkpoint_info"),
                elem_classes=["has-info-container"],
            )
        with gr.Column(scale=1, min_width=90):
            refresh_btn = gr.Button(t("service.refresh_btn"), size="sm")
    return {"checkpoint_dropdown": checkpoint_dropdown, "refresh_btn": refresh_btn}


def build_model_device_controls(
    dit_handler: Any,
    service_pre_initialized: bool,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Create model-path and device selection controls.

    Args:
        dit_handler: DiT handler used to list available model configs.
        service_pre_initialized: Whether existing init params should prefill values.
        params: Startup state dictionary containing optional model/device values.

    Returns:
        A component map containing ``config_path``, ``device``, and ``device_value``.
    """

    with gr.Row():
        available_models = dit_handler.get_available_acestep_v15_models()
        default_model = (
            "acestep-v15-turbo"
            if "acestep-v15-turbo" in available_models
            else (available_models[0] if available_models else None)
        )
        config_path = gr.Dropdown(
            label=t("service.model_path_label"),
            choices=available_models,
            value=params.get("config_path", default_model) if service_pre_initialized else default_model,
            info=t("service.model_path_info"),
            elem_classes=["has-info-container"],
        )
        device_value = params.get("device", "auto") if service_pre_initialized else "auto"
        device = gr.Dropdown(
            choices=["auto", "cuda", "mps", "xpu", "cpu"],
            value=device_value,
            label=t("service.device_label"),
            info=t("service.device_info"),
            elem_classes=["has-info-container"],
        )
    return {
        "config_path": config_path,
        "device": device,
        "device_value": device_value,
    }


def build_lm_backend_controls(
    llm_handler: Any,
    service_pre_initialized: bool,
    params: dict[str, Any],
    recommended_lm: str | None,
    available_backends: list[str],
    recommended_backend: str,
    gpu_config: Any,
) -> dict[str, Any]:
    """Create LM model-path and backend selector controls.

    Args:
        llm_handler: LM handler used to list available LM model choices.
        service_pre_initialized: Whether existing init params should prefill values.
        params: Startup state dictionary containing optional LM/backend values.
        recommended_lm: Recommended LM model identifier for this tier.
        available_backends: Backend choices allowed for current environment.
        recommended_backend: Preferred backend selected by defaults logic.
        gpu_config: GPU configuration object used for backend info text.

    Returns:
        A component map containing ``lm_model_path`` and ``backend_dropdown``.
    """

    with gr.Row():
        all_lm_models = llm_handler.get_available_5hz_lm_models()
        default_lm_model = find_best_lm_model_on_disk(recommended_lm, all_lm_models)
        lm_model_path = gr.Dropdown(
            label=t("service.lm_model_path_label"),
            choices=all_lm_models,
            value=params.get("lm_model_path", default_lm_model) if service_pre_initialized else default_lm_model,
            info=t("service.lm_model_path_info")
            + (
                f" (Recommended: {recommended_lm})"
                if recommended_lm
                else " (LM not available for this GPU tier)"
            ),
            elem_classes=["has-info-container"],
        )
        backend_dropdown = gr.Dropdown(
            choices=available_backends,
            value=params.get("backend", recommended_backend) if service_pre_initialized else recommended_backend,
            label=t("service.backend_label"),
            info=t("service.backend_info")
            + (
                f" (vllm unavailable for {gpu_config.tier}: VRAM too low)"
                if gpu_config.lm_backend_restriction == "pt_mlx_only"
                else ""
            ),
            elem_classes=["has-info-container"],
        )
    return {
        "lm_model_path": lm_model_path,
        "backend_dropdown": backend_dropdown,
    }
