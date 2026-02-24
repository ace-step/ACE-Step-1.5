"""Training dataset-load and preprocess wiring helpers."""

from typing import Any, Mapping

import gradio as gr

from .. import training_handlers as train_h
from .context import TrainingWiringContext


_DATASET_LOAD_SHARED_OUTPUT_KEYS = (
    "audio_files_table",
    "sample_selector",
    "dataset_builder_state",
    "preview_audio",
    "preview_filename",
    "edit_caption",
    "edit_genre",
    "prompt_override",
    "edit_lyrics",
    "edit_bpm",
    "edit_keyscale",
    "edit_timesig",
    "edit_duration",
    "edit_language",
    "edit_instrumental",
    "raw_lyrics_display",
    "has_raw_lyrics_state",
    "dataset_name",
    "custom_tag",
    "tag_position",
    "all_instrumental",
    "genre_ratio",
)


def _build_dataset_load_outputs(
    training_section: Mapping[str, Any],
    status_key: str,
) -> list[Any]:
    """Return the ordered output list for dataset-load button wiring."""

    return [training_section[status_key]] + [
        training_section[key] for key in _DATASET_LOAD_SHARED_OUTPUT_KEYS
    ]


def register_training_dataset_load_handler(
    context: TrainingWiringContext,
    *,
    button_key: str,
    path_key: str,
    status_key: str,
) -> None:
    """Register one dataset JSON load button with shared output/update contracts."""

    training_section = context.training_section
    training_section[button_key].click(
        fn=train_h.load_existing_dataset_for_preprocess,
        inputs=[
            training_section[path_key],
            training_section["dataset_builder_state"],
        ],
        outputs=_build_dataset_load_outputs(training_section, status_key),
    ).then(
        fn=lambda has_raw: gr.update(visible=has_raw),
        inputs=[training_section["has_raw_lyrics_state"]],
        outputs=[training_section["raw_lyrics_display"]],
    )


def register_training_preprocess_handler(context: TrainingWiringContext) -> None:
    """Register preprocess button wiring for tensor conversion."""

    training_section = context.training_section
    dit_handler = context.dit_handler
    training_section["preprocess_btn"].click(
        fn=lambda output_dir, mode, state: train_h.preprocess_dataset(
            output_dir, mode, dit_handler, state
        ),
        inputs=[
            training_section["preprocess_output_dir"],
            training_section["preprocess_mode"],
            training_section["dataset_builder_state"],
        ],
        outputs=[training_section["preprocess_progress"]],
    )
