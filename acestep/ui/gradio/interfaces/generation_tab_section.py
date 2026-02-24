"""Generation-tab section orchestrator for the Gradio interface."""

from typing import Any

import gradio as gr

from acestep.constants import GENERATION_MODES_BASE, GENERATION_MODES_TURBO

from .generation_defaults import compute_init_defaults, resolve_is_pure_base_model
from .generation_tab_primary_controls import (
    build_hidden_generation_state,
    build_mode_selector_controls,
)
from .generation_tab_simple_controls import (
    build_simple_mode_controls,
)
from .generation_tab_source_controls import (
    build_source_track_and_code_controls,
)
from .generation_tab_generate_controls import (
    build_generate_row_controls,
)
from .generation_tab_optional_controls import (
    build_optional_parameter_controls,
)
from .generation_tab_secondary_controls import (
    build_cover_strength_controls,
    build_custom_mode_controls,
    build_repainting_controls,
)


def create_generation_tab_section(
    dit_handler: Any,
    llm_handler: Any,
    init_params: dict[str, Any] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Create generation-tab controls and mode-specific UI sections.

    Args:
        dit_handler: DiT service handler used for model-aware mode defaults.
        llm_handler: LM service handler retained for signature parity with callers.
        init_params: Optional startup state used to prefill runtime defaults.
        language: UI language code used for default computation.

    Returns:
        A merged component map for generation-tab controls and runtime metadata.
    """

    _ = llm_handler  # retained for caller signature parity
    defaults = compute_init_defaults(init_params, language)
    service_pre_initialized = defaults["service_pre_initialized"]
    service_mode = defaults["service_mode"]
    lm_initialized = defaults["lm_initialized"]
    max_duration = defaults["max_duration"]
    max_batch_size = defaults["max_batch_size"]
    default_batch_size = defaults["default_batch_size"]

    is_pure_base_model = resolve_is_pure_base_model(
        dit_handler=dit_handler,
        init_params=init_params,
        service_pre_initialized=service_pre_initialized,
    )
    initial_mode_choices = GENERATION_MODES_BASE if is_pure_base_model else GENERATION_MODES_TURBO

    with gr.Group():
        mode_controls = build_mode_selector_controls(initial_mode_choices)
        hidden_state_controls = build_hidden_generation_state()
        simple_mode_controls = build_simple_mode_controls()
        source_track_code_controls = build_source_track_and_code_controls()
        cover_controls = build_cover_strength_controls()
        custom_mode_controls = build_custom_mode_controls()
        repainting_controls = build_repainting_controls()
        optional_controls = build_optional_parameter_controls(
            max_duration=max_duration,
            max_batch_size=max_batch_size,
            default_batch_size=default_batch_size,
            service_mode=service_mode,
        )
        generate_controls = build_generate_row_controls(
            service_pre_initialized=service_pre_initialized,
            init_params=init_params,
            lm_initialized=lm_initialized,
            service_mode=service_mode,
        )

    result: dict[str, Any] = {}
    result.update(mode_controls)
    result.update(hidden_state_controls)
    result.update(simple_mode_controls)
    result.update(source_track_code_controls)
    result.update(cover_controls)
    result.update(custom_mode_controls)
    result.update(repainting_controls)
    result.update(optional_controls)
    result.update(generate_controls)
    result.update(
        {
            "max_duration": max_duration,
            "max_batch_size": max_batch_size,
        }
    )
    return result
