"""Wiring helpers for Gradio event registration.

This package provides shared context and list-builder helpers used by the
event wiring facade in ``acestep.ui.gradio.events``.
"""

from .context import (
    GenerationWiringContext,
    TrainingWiringContext,
    build_auto_checkbox_inputs,
    build_auto_checkbox_outputs,
    build_mode_ui_outputs,
)
from .generation_metadata_wiring import register_generation_metadata_handlers
from .generation_mode_wiring import register_generation_mode_handlers
from .results_aux_wiring import register_results_aux_handlers
from .generation_service_wiring import register_generation_service_handlers

__all__ = [
    "GenerationWiringContext",
    "TrainingWiringContext",
    "build_auto_checkbox_inputs",
    "build_auto_checkbox_outputs",
    "build_mode_ui_outputs",
    "register_generation_metadata_handlers",
    "register_generation_mode_handlers",
    "register_results_aux_handlers",
    "register_generation_service_handlers",
]
