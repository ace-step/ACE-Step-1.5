"""Service-configuration builders for the generation interface."""

from typing import Any

import gradio as gr

from acestep.ui.gradio.help_content import create_help_button
from acestep.ui.gradio.i18n import t

from .generation_defaults import compute_init_defaults
from .generation_service_config_rows import (
    build_checkpoint_controls,
    build_gpu_info_and_tier,
    build_language_selector,
    build_lm_backend_controls,
    build_model_device_controls,
)
from .generation_service_config_toggles import (
    build_service_init_controls,
    build_service_toggles,
)


def create_service_config_content(
    dit_handler: Any,
    llm_handler: Any,
    defaults: dict[str, Any],
    init_params: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build service-configuration controls embedded inside the Settings accordion.

    Args:
        dit_handler: DiT service handler used for checkpoint/model/device options.
        llm_handler: LM service handler used for LM model/backend options.
        defaults: Precomputed defaults from ``compute_init_defaults``.
        init_params: Optional startup state used to prefill control values.

    Returns:
        A keyed component dictionary for all service configuration controls.
    """

    params = init_params or {}
    service_pre_initialized = defaults["service_pre_initialized"]
    service_mode = defaults["service_mode"]

    with gr.Accordion(
        t("service.title"),
        open=not service_pre_initialized,
        visible=not service_mode,
        elem_classes=["has-info-container"],
    ) as service_config_accordion:
        create_help_button("service_config")
        language_controls = build_language_selector(defaults["current_language"])
        gpu_controls = build_gpu_info_and_tier(defaults["gpu_config"])
        checkpoint_controls = build_checkpoint_controls(
            dit_handler=dit_handler,
            service_pre_initialized=service_pre_initialized,
            params=params,
        )
        model_device_controls = build_model_device_controls(
            dit_handler=dit_handler,
            service_pre_initialized=service_pre_initialized,
            params=params,
        )
        lm_backend_controls = build_lm_backend_controls(
            llm_handler=llm_handler,
            service_pre_initialized=service_pre_initialized,
            params=params,
            recommended_lm=defaults["recommended_lm"],
            available_backends=defaults["available_backends"],
            recommended_backend=defaults["recommended_backend"],
            gpu_config=defaults["gpu_config"],
        )
        toggle_controls = build_service_toggles(
            dit_handler=dit_handler,
            device_value=model_device_controls["device_value"],
            service_pre_initialized=service_pre_initialized,
            params=params,
            init_lm_default=defaults["init_lm_default"],
            default_offload=defaults["default_offload"],
            default_offload_dit=defaults["default_offload_dit"],
            default_compile=defaults["default_compile"],
            default_quantization=defaults["default_quantization"],
            gpu_config=defaults["gpu_config"],
        )
        init_controls = build_service_init_controls(
            service_pre_initialized=service_pre_initialized,
            params=params,
        )

    result: dict[str, Any] = {"service_config_accordion": service_config_accordion}
    result.update(language_controls)
    result.update(gpu_controls)
    result.update(checkpoint_controls)
    result.update(
        {
            "config_path": model_device_controls["config_path"],
            "device": model_device_controls["device"],
        }
    )
    result.update(lm_backend_controls)
    result.update(toggle_controls)
    result.update(init_controls)
    result["gpu_config"] = defaults["gpu_config"]
    return result


def create_service_config_section(
    dit_handler: Any,
    llm_handler: Any,
    init_params: dict[str, Any] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Build the legacy standalone service-config map for compatibility callers.

    Args:
        dit_handler: DiT service handler used to build service controls.
        llm_handler: LM service handler used to build service controls.
        init_params: Optional startup state used to prefill control values.
        language: UI language code.

    Returns:
        A keyed component dictionary matching the legacy service-config contract.
    """

    defaults = compute_init_defaults(init_params, language)
    return create_service_config_content(dit_handler, llm_handler, defaults, init_params)
