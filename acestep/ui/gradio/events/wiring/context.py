"""Typed wiring context and shared component-list builders.

The event facade contains several long output/input lists that must remain in
strict order. This module centralizes those list contracts to reduce copy-paste
risk while keeping handler wiring behavior unchanged.
"""

from dataclasses import dataclass
from typing import Any, Mapping


ComponentMap = Mapping[str, Any]

_AUTO_CHECKBOX_OUTPUT_KEYS = (
    "bpm_auto",
    "key_auto",
    "timesig_auto",
    "vocal_lang_auto",
    "duration_auto",
    "bpm",
    "key_scale",
    "time_signature",
    "vocal_language",
    "audio_duration",
)

_AUTO_CHECKBOX_INPUT_KEYS = (
    "bpm",
    "key_scale",
    "time_signature",
    "vocal_language",
    "audio_duration",
)

_MODE_UI_OUTPUT_KEYS = (
    "simple_mode_group",
    "custom_mode_group",
    "generate_btn",
    "simple_sample_created",
    "optional_params_accordion",
    "task_type",
    "src_audio_row",
    "repainting_group",
    "text2music_audio_codes_group",
    "track_name",
    "complete_track_classes",
    "generate_btn_row",
    "generation_mode",
    "results_wrapper",
    "think_checkbox",
    "load_file_col",
    "load_file",
    "audio_cover_strength",
    "cover_noise_strength",
    "captions",
    "lyrics",
    "bpm",
    "key_scale",
    "time_signature",
    "vocal_language",
    "audio_duration",
    "auto_score",
    "autogen_checkbox",
    "auto_lrc",
    "analyze_btn",
    "repainting_header_html",
    "repainting_start",
    "repainting_end",
    "previous_generation_mode",
    "remix_help_group",
    "extract_help_group",
    "complete_help_group",
    "bpm_auto",
    "key_auto",
    "timesig_auto",
    "vocal_lang_auto",
    "duration_auto",
    "text2music_audio_code_string",
    "src_audio",
)


@dataclass(frozen=True)
class GenerationWiringContext:
    """Inputs required for generation/results event wiring."""

    demo: Any
    dit_handler: Any
    llm_handler: Any
    dataset_handler: Any
    dataset_section: ComponentMap
    generation_section: ComponentMap
    results_section: ComponentMap


@dataclass(frozen=True)
class TrainingWiringContext:
    """Inputs required for training event wiring."""

    demo: Any
    dit_handler: Any
    llm_handler: Any
    training_section: ComponentMap


def build_auto_checkbox_outputs(context: GenerationWiringContext) -> list[Any]:
    """Return ordered auto-checkbox outputs for metadata field sync."""

    generation = context.generation_section
    return [generation[key] for key in _AUTO_CHECKBOX_OUTPUT_KEYS]


def build_auto_checkbox_inputs(context: GenerationWiringContext) -> list[Any]:
    """Return ordered metadata fields used to derive auto-checkbox state."""

    generation = context.generation_section
    return [generation[key] for key in _AUTO_CHECKBOX_INPUT_KEYS]


def build_mode_ui_outputs(context: GenerationWiringContext) -> list[Any]:
    """Return ordered mode-UI outputs shared across mode/remix/repaint wiring."""

    generation = context.generation_section
    return [generation[key] for key in _MODE_UI_OUTPUT_KEYS]
