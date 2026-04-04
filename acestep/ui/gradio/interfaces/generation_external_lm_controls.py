"""External-LM configuration controls for the generation settings UI."""

import os
from typing import Any

import gradio as gr

from acestep.text_tasks.external_lm_model_cache import (
    load_cached_external_models,
)
from acestep.text_tasks.external_lm_providers import (
    get_external_base_url_preset_choices,
    get_external_base_url_preset_value,
    get_external_provider_choices,
    get_external_provider_profile,
)
from acestep.text_tasks.external_lm_runtime_store import (
    load_external_lm_runtime_settings,
)
from acestep.ui.gradio.i18n import t
def build_external_lm_controls(
    *,
    service_pre_initialized: bool,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Create the external-LM configuration accordion shown above LM controls."""

    external_prefill = _resolve_external_prefill_state(
        params=params,
        service_pre_initialized=service_pre_initialized,
    )
    external_backend_selected = (
        str(params.get("backend", "")).strip().lower() == "external"
        if service_pre_initialized
        else False
    )

    with gr.Accordion(
        f"🧠 {t('service.external_llm_title')}",
        open=external_backend_selected,
    ) as external_llm_accordion:
        gr.Markdown(
            t("service.external_llm_description"),
            elem_classes=["no-tooltip"],
        )
        with gr.Row():
            external_llm_provider = gr.Dropdown(
                choices=get_external_provider_choices(),
                value=external_prefill["provider"],
                label=t("service.external_llm_provider_label"),
                info=t("service.external_llm_provider_info"),
                elem_classes=["has-info-container"],
            )
            external_llm_base_url_preset = gr.Dropdown(
                choices=external_prefill["base_url_preset_choices"],
                value=external_prefill["base_url_preset"],
                label=t("service.external_llm_base_url_preset_label"),
                info=t("service.external_llm_base_url_preset_info"),
                elem_classes=["has-info-container"],
            )
        with gr.Row(equal_height=True):
            with gr.Column(scale=4):
                external_llm_model = gr.Dropdown(
                    choices=external_prefill["model_choices"],
                    value=external_prefill["model"],
                    allow_custom_value=True,
                    label=t("service.external_llm_model_label"),
                    info=t("service.external_llm_model_info"),
                    elem_classes=["has-info-container"],
                )
            with gr.Column(scale=1, min_width=90):
                external_llm_fetch_models_btn = gr.Button(
                    f"🔄 {t('service.external_llm_fetch_models_btn')}",
                    size="sm",
                )
        with gr.Row():
            external_llm_base_url = gr.Textbox(
                value=external_prefill["base_url"],
                label=t("service.external_llm_base_url_label"),
                info=t("service.external_llm_base_url_info"),
                elem_classes=["has-info-container"],
            )
            external_llm_api_key = gr.Textbox(
                value=external_prefill["api_key"],
                type="password",
                label=t("service.external_llm_api_key_label"),
                info=t("service.external_llm_api_key_info"),
                elem_classes=["has-info-container", "external-lm-api-key"],
                elem_id="external-lm-api-key",
            )
        with gr.Row():
            with gr.Column():
                gr.Markdown(
                    f"**{t('service.external_llm_status_label')}**",
                    elem_classes=["no-tooltip"],
                )
                external_llm_status = gr.Markdown(
                    value=external_prefill["status"],
                    elem_classes=["external-lm-status", "no-tooltip"],
                )
        with gr.Row():
            external_llm_save_btn = gr.Button(
                t("service.external_llm_save_btn"),
                variant="secondary",
            )
            external_llm_test_btn = gr.Button(
                t("service.external_llm_test_btn"),
                variant="secondary",
            )
            external_llm_doctor_btn = gr.Button(
                t("service.external_llm_doctor_btn"),
                variant="secondary",
            )

    return {
        "external_llm_accordion": external_llm_accordion,
        "external_llm_provider": external_llm_provider,
        "external_llm_base_url_preset": external_llm_base_url_preset,
        "external_llm_model": external_llm_model,
        "external_llm_fetch_models_btn": external_llm_fetch_models_btn,
        "external_llm_base_url": external_llm_base_url,
        "external_llm_api_key": external_llm_api_key,
        "external_llm_status": external_llm_status,
        "external_llm_save_btn": external_llm_save_btn,
        "external_llm_test_btn": external_llm_test_btn,
        "external_llm_doctor_btn": external_llm_doctor_btn,
    }
def _resolve_external_prefill_state(
    *,
    params: dict[str, Any],
    service_pre_initialized: bool,
) -> dict[str, Any]:
    """Return initial provider/model/base-url values for external LM controls."""

    requested_provider = str(
        params.get("external_llm_provider")
        or os.getenv("ACESTEP_EXTERNAL_LM_PROVIDER", "")
    ).strip().lower()
    stored = load_external_lm_runtime_settings(requested_provider or None) or {}
    provider = (
        requested_provider
        or str(stored.get("provider", "")).strip().lower()
        or get_external_provider_choices()[0][1]
    )
    profile = get_external_provider_profile(provider)

    model = (
        str(params.get("external_llm_model", "")).strip()
        if service_pre_initialized
        else ""
    ) or str(os.getenv("ACESTEP_EXTERNAL_LM_MODEL", "")).strip() or str(
        stored.get("model", "")
    ).strip() or profile.default_model

    base_url = (
        str(params.get("external_llm_base_url", "")).strip()
        if service_pre_initialized
        else ""
    ) or str(os.getenv("ACESTEP_EXTERNAL_BASE_URL", "")).strip() or str(
        stored.get("base_url", "")
    ).strip() or profile.default_base_url

    api_key = str(params.get("external_llm_api_key", "")).strip() if service_pre_initialized else ""
    status = str(params.get("external_llm_status", "")).strip() if service_pre_initialized else ""
    return {
        "provider": provider,
        "model": model,
        "model_choices": _build_external_model_choices(
            provider=provider, protocol=profile.protocol, base_url=base_url, model=model
        ),
        "base_url": base_url,
        "base_url_preset_choices": get_external_base_url_preset_choices(provider),
        "base_url_preset": get_external_base_url_preset_value(provider, base_url),
        "api_key": api_key,
        "status": status,
    }
def _build_external_model_choices(
    *,
    provider: str,
    protocol: str,
    base_url: str,
    model: str,
) -> list[str]:
    """Return cached model choices plus the current selection for the provider."""

    cached = load_cached_external_models(
        provider=provider,
        protocol=protocol,
        base_url=base_url,
    ) or []
    choices = [str(item).strip() for item in cached if str(item).strip()]
    normalized_model = (model or "").strip()
    if normalized_model and normalized_model not in choices:
        choices.insert(0, normalized_model)
    return choices
