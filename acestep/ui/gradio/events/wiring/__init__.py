"""Wiring helpers for Gradio event registration.

This package provides shared context and list-builder helpers used by the
event wiring facade in ``acestep.ui.gradio.events``.
"""

from __future__ import annotations

from typing import Any

from .context import (
    GenerationWiringContext,
    TrainingWiringContext,
    build_auto_checkbox_inputs,
    build_auto_checkbox_outputs,
    build_mode_ui_outputs,
)


def register_generation_metadata_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register metadata-related generation handlers via lazy import."""
    from .generation_metadata_wiring import register_generation_metadata_handlers as _register

    return _register(*args, **kwargs)


def register_generation_metadata_file_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register generation metadata file handlers via lazy import."""
    from .generation_metadata_file_wiring import register_generation_metadata_file_handlers as _register

    return _register(*args, **kwargs)


def register_generation_batch_navigation_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register generation batch-navigation handlers via lazy import."""
    from .generation_batch_navigation_wiring import register_generation_batch_navigation_handlers as _register

    return _register(*args, **kwargs)


def register_generation_mode_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register generation mode handlers via lazy import."""
    from .generation_mode_wiring import register_generation_mode_handlers as _register

    return _register(*args, **kwargs)


def register_generation_run_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register generation run handlers via lazy import."""
    from .generation_run_wiring import register_generation_run_handlers as _register

    return _register(*args, **kwargs)


def register_results_aux_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register results auxiliary handlers via lazy import."""
    from .results_aux_wiring import register_results_aux_handlers as _register

    return _register(*args, **kwargs)


def register_results_restore_and_lrc_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register results restore/LRC handlers via lazy import."""
    from .results_display_wiring import register_results_restore_and_lrc_handlers as _register

    return _register(*args, **kwargs)


def register_results_save_button_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register results save-button handlers via lazy import."""
    from .results_display_wiring import register_results_save_button_handlers as _register

    return _register(*args, **kwargs)


def register_generation_service_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register generation service handlers via lazy import."""
    from .generation_service_wiring import register_generation_service_handlers as _register

    return _register(*args, **kwargs)


def register_training_dataset_builder_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register training dataset builder handlers via lazy import."""
    from .training_dataset_builder_wiring import register_training_dataset_builder_handlers as _register

    return _register(*args, **kwargs)


def register_training_dataset_load_handler(*args: Any, **kwargs: Any) -> Any:
    """Register training dataset load handlers via lazy import."""
    from .training_dataset_preprocess_wiring import register_training_dataset_load_handler as _register

    return _register(*args, **kwargs)


def register_training_preprocess_handler(*args: Any, **kwargs: Any) -> Any:
    """Register training preprocess handlers via lazy import."""
    from .training_dataset_preprocess_wiring import register_training_preprocess_handler as _register

    return _register(*args, **kwargs)


def register_training_run_handlers(*args: Any, **kwargs: Any) -> Any:
    """Register training run handlers via lazy import."""
    from .training_run_wiring import register_training_run_handlers as _register

    return _register(*args, **kwargs)


__all__ = [
    "GenerationWiringContext",
    "TrainingWiringContext",
    "build_auto_checkbox_inputs",
    "build_auto_checkbox_outputs",
    "build_mode_ui_outputs",
    "register_generation_batch_navigation_handlers",
    "register_generation_metadata_file_handlers",
    "register_generation_metadata_handlers",
    "register_generation_mode_handlers",
    "register_generation_run_handlers",
    "register_results_aux_handlers",
    "register_results_restore_and_lrc_handlers",
    "register_results_save_button_handlers",
    "register_generation_service_handlers",
    "register_training_dataset_builder_handlers",
    "register_training_dataset_load_handler",
    "register_training_preprocess_handler",
    "register_training_run_handlers",
]
