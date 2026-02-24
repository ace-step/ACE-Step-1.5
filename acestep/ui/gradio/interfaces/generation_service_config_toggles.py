"""Toggle and init controls for generation service configuration."""

from typing import Any

import gradio as gr

from acestep.ui.gradio.i18n import t

try:
    from acestep.models.mlx import mlx_available as _mlx_avail
except ImportError:
    def _mlx_avail() -> bool:
        """Return False when MLX dependency is unavailable."""

        return False


def build_service_toggles(
    dit_handler: Any,
    device_value: str,
    service_pre_initialized: bool,
    params: dict[str, Any],
    init_lm_default: bool,
    default_offload: bool,
    default_offload_dit: bool,
    default_compile: bool,
    default_quantization: bool,
    gpu_config: Any,
) -> dict[str, Any]:
    """Create service toggle checkboxes for runtime and optimization settings.

    Args:
        dit_handler: DiT handler used for flash-attention capability detection.
        device_value: Current device dropdown value used for availability checks.
        service_pre_initialized: Whether existing init params should prefill values.
        params: Startup state dictionary with optional toggle overrides.
        init_lm_default: Default value for init-LLM toggle.
        default_offload: Default value for LM offload-to-CPU toggle.
        default_offload_dit: Default value for DiT offload-to-CPU toggle.
        default_compile: Default value for compile-model toggle.
        default_quantization: Default value for quantization toggle.
        gpu_config: GPU configuration object used for LM availability messaging.

    Returns:
        A component map for all service toggles (LLM, flash attention, offload, compile, quantization, MLX).
    """

    with gr.Row():
        lm_info_text = t("service.init_llm_info")
        if not gpu_config.available_lm_models:
            lm_info_text += " " + t("service.lm_unavailable_vram")
        init_llm_checkbox = gr.Checkbox(
            label=t("service.init_llm_label"),
            value=params.get("init_llm", init_lm_default) if service_pre_initialized else init_lm_default,
            info=lm_info_text,
        )

        flash_attn_available = dit_handler.is_flash_attention_available(device_value)
        use_flash_attention_checkbox = gr.Checkbox(
            label=t("service.flash_attention_label"),
            value=params.get("use_flash_attention", flash_attn_available)
            if service_pre_initialized
            else flash_attn_available,
            interactive=flash_attn_available,
            info=t("service.flash_attention_info_enabled")
            if flash_attn_available
            else t("service.flash_attention_info_disabled"),
            elem_classes=["has-info-container"],
        )
        offload_to_cpu_checkbox = gr.Checkbox(
            label=t("service.offload_cpu_label"),
            value=params.get("offload_to_cpu", default_offload) if service_pre_initialized else default_offload,
            info=t("service.offload_cpu_info")
            + (" (recommended for this tier)" if default_offload else " (optional for this tier)"),
            elem_classes=["has-info-container"],
        )
        offload_dit_to_cpu_checkbox = gr.Checkbox(
            label=t("service.offload_dit_cpu_label"),
            value=params.get("offload_dit_to_cpu", default_offload_dit)
            if service_pre_initialized
            else default_offload_dit,
            info=t("service.offload_dit_cpu_info")
            + (" (recommended for this tier)" if default_offload_dit else " (optional for this tier)"),
            elem_classes=["has-info-container"],
        )
        compile_model_checkbox = gr.Checkbox(
            label=t("service.compile_model_label"),
            value=params.get("compile_model", default_compile) if service_pre_initialized else default_compile,
            info=t("service.compile_model_info"),
            elem_classes=["has-info-container"],
        )
        quantization_checkbox = gr.Checkbox(
            label=t("service.quantization_label"),
            value=params.get("quantization", default_quantization) if service_pre_initialized else default_quantization,
            info=t("service.quantization_info")
            + (" (recommended for this tier)" if default_quantization else " (optional for this tier)"),
            elem_classes=["has-info-container"],
        )

        mlx_ok = _mlx_avail()
        mlx_dit_checkbox = gr.Checkbox(
            label=t("service.mlx_dit_label"),
            value=params.get("mlx_dit", mlx_ok) if service_pre_initialized else mlx_ok,
            interactive=mlx_ok,
            info=t("service.mlx_dit_info_enabled") if mlx_ok else t("service.mlx_dit_info_disabled"),
            elem_classes=["has-info-container"],
        )
    return {
        "init_llm_checkbox": init_llm_checkbox,
        "use_flash_attention_checkbox": use_flash_attention_checkbox,
        "offload_to_cpu_checkbox": offload_to_cpu_checkbox,
        "offload_dit_to_cpu_checkbox": offload_dit_to_cpu_checkbox,
        "compile_model_checkbox": compile_model_checkbox,
        "quantization_checkbox": quantization_checkbox,
        "mlx_dit_checkbox": mlx_dit_checkbox,
    }


def build_service_init_controls(service_pre_initialized: bool, params: dict[str, Any]) -> dict[str, Any]:
    """Create service initialization action and status controls.

    Args:
        service_pre_initialized: Whether existing init params should prefill status.
        params: Startup state dictionary containing optional init status text.

    Returns:
        A component map containing ``init_btn`` and ``init_status``.
    """

    init_btn = gr.Button(t("service.init_btn"), variant="primary", size="lg")
    init_status = gr.Textbox(
        label=t("service.status_label"),
        interactive=False,
        lines=3,
        value=params.get("init_status", "") if service_pre_initialized else "",
    )
    return {"init_btn": init_btn, "init_status": init_status}
