"""Generation service-layer event wiring helpers.

This module contains wiring related to service initialization, LoRA controls,
auto-checkbox controls, and visibility updates for generation components.
"""

from typing import Any

import gradio as gr

from .. import generation_handlers as gen_h
from ...i18n import get_i18n, reset_language_context, set_language_context
from .context import GenerationWiringContext
from .generation_service_wiring_sections import (
    register_dataset_handlers,
    register_external_lm_field_handlers,
    register_generation_init_handlers,
    register_generation_model_handlers,
)
from .generation_service_wiring_support import register_generation_support_handlers


def register_generation_service_handlers(
    context: GenerationWiringContext,
) -> tuple[list[Any], list[Any]]:
    """Register generation service/init handlers and return auto-checkbox lists."""

    dataset_section = context.dataset_section
    generation_section = context.generation_section
    results_section = context.results_section
    dit_handler = context.dit_handler
    dataset_handler = context.dataset_handler

    register_dataset_handlers(dataset_section, dataset_handler)
    register_generation_model_handlers(generation_section, dit_handler)

    generation_section["language_dropdown"].change(
        fn=lambda language: _apply_runtime_language(language),
        inputs=[generation_section["language_dropdown"]],
        outputs=[generation_section["language_dropdown"]],
    )

    generation_section["backend_dropdown"].change(
        fn=gen_h.update_llm_backend_ui,
        inputs=[
            generation_section["backend_dropdown"],
            generation_section["init_llm_checkbox"],
            generation_section["init_llm_local_state"],
        ],
        outputs=[
            generation_section["local_lm_column"],
            generation_section["external_llm_accordion"],
            generation_section["init_llm_checkbox"],
            generation_section["init_llm_local_state"],
        ],
    )
    register_external_lm_field_handlers(generation_section)

    generation_section["external_llm_fetch_models_btn"].click(
        fn=gen_h.fetch_external_lm_models,
        inputs=[
            generation_section["external_llm_provider"],
            generation_section["external_llm_model"],
            generation_section["external_llm_base_url"],
            generation_section["external_llm_api_key"],
        ],
        outputs=[
            generation_section["external_llm_model"],
            generation_section["external_llm_status"],
        ],
    )

    generation_section["external_llm_save_btn"].click(
        fn=gen_h.save_external_lm_settings,
        inputs=[
            generation_section["external_llm_provider"],
            generation_section["external_llm_model"],
            generation_section["external_llm_base_url"],
            generation_section["external_llm_api_key"],
        ],
        outputs=[generation_section["external_llm_status"]],
    )

    generation_section["external_llm_test_btn"].click(
        fn=gen_h.test_external_lm_endpoint,
        inputs=[
            generation_section["external_llm_provider"],
            generation_section["external_llm_model"],
            generation_section["external_llm_base_url"],
            generation_section["external_llm_api_key"],
        ],
        outputs=[generation_section["external_llm_status"]],
    )

    generation_section["external_llm_doctor_btn"].click(
        fn=gen_h.run_external_lm_runtime_doctor,
        inputs=[
            generation_section["external_llm_provider"],
            generation_section["external_llm_model"],
            generation_section["external_llm_base_url"],
            generation_section["external_llm_api_key"],
        ],
        outputs=[generation_section["external_llm_status"]],
    )
    register_generation_init_handlers(generation_section, dit_handler, context.llm_handler)
    return register_generation_support_handlers(context)


def _apply_runtime_language(language: str) -> dict[str, Any]:
    """Update i18n language at the Gradio request boundary.

    Sets a per-request ``ContextVar`` so any ``t()`` calls within this
    handler use *language*, then updates the shared instance default so
    future requests without an explicit context inherit it.  The
    ``ContextVar`` is reset on exit to avoid poisoning reused
    thread-pool workers with a stale language value.

    Args:
        language: Selected UI language code from the language dropdown.

    Returns:
        A ``gr.update`` payload preserving the selected dropdown value.
    """
    # Set ContextVar for this handler's scope.  No t() calls happen here
    # today, but the pattern establishes the request-boundary convention
    # for future handlers that adopt per-request language isolation.
    token = set_language_context(language)
    try:
        get_i18n(language)
        return gr.update(value=language)
    finally:
        reset_language_context(token)
