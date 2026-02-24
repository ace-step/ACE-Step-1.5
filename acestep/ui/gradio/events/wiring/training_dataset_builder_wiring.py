"""Training dataset-builder event wiring helpers."""

from typing import Any, Mapping

import gradio as gr

from .. import training_handlers as train_h
from .context import TrainingWiringContext


_SAMPLE_PREVIEW_OUTPUT_KEYS = (
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
)

_SETTINGS_TRIGGER_KEYS = (
    "custom_tag",
    "tag_position",
    "all_instrumental",
    "genre_ratio",
)

_CHECKMARK = "\u2705"


def _build_sample_preview_outputs(training_section: Mapping[str, Any]) -> list[Any]:
    """Return ordered sample-preview outputs shared by preview refresh handlers."""

    return [training_section[key] for key in _SAMPLE_PREVIEW_OUTPUT_KEYS]


def register_training_dataset_builder_handlers(context: TrainingWiringContext) -> None:
    """Register dataset-builder handlers while preserving existing IO ordering."""

    training_section = context.training_section
    dit_handler = context.dit_handler
    llm_handler = context.llm_handler
    sample_preview_outputs = _build_sample_preview_outputs(training_section)

    training_section["scan_btn"].click(
        fn=lambda directory, name, tag, pos, instr, state: train_h.scan_directory(
            directory, name, tag, pos, instr, state
        ),
        inputs=[
            training_section["audio_directory"],
            training_section["dataset_name"],
            training_section["custom_tag"],
            training_section["tag_position"],
            training_section["all_instrumental"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["audio_files_table"],
            training_section["scan_status"],
            training_section["sample_selector"],
            training_section["dataset_builder_state"],
        ],
    )

    training_section["auto_label_btn"].click(
        fn=lambda state, skip, fmt_lyrics, trans_lyrics, only_unlab: train_h.auto_label_all(
            dit_handler, llm_handler, state, skip, fmt_lyrics, trans_lyrics, only_unlab
        ),
        inputs=[
            training_section["dataset_builder_state"],
            training_section["skip_metas"],
            training_section["format_lyrics"],
            training_section["transcribe_lyrics"],
            training_section["only_unlabeled"],
        ],
        outputs=[
            training_section["audio_files_table"],
            training_section["label_progress"],
            training_section["dataset_builder_state"],
        ],
    ).then(
        fn=train_h.get_sample_preview,
        inputs=[
            training_section["sample_selector"],
            training_section["dataset_builder_state"],
        ],
        outputs=sample_preview_outputs,
    ).then(
        fn=lambda status: f"{status or (_CHECKMARK + ' Auto-label complete.')}\n{_CHECKMARK} Preview refreshed.",
        inputs=[training_section["label_progress"]],
        outputs=[training_section["label_progress"]],
    ).then(
        fn=lambda has_raw: gr.update(visible=bool(has_raw)),
        inputs=[training_section["has_raw_lyrics_state"]],
        outputs=[training_section["raw_lyrics_display"]],
    )

    training_section["format_lyrics"].change(
        fn=lambda fmt: gr.update(value=False) if fmt else gr.update(),
        inputs=[training_section["format_lyrics"]],
        outputs=[training_section["transcribe_lyrics"]],
    )

    training_section["transcribe_lyrics"].change(
        fn=lambda trans: gr.update(value=False) if trans else gr.update(),
        inputs=[training_section["transcribe_lyrics"]],
        outputs=[training_section["format_lyrics"]],
    )

    training_section["sample_selector"].change(
        fn=train_h.get_sample_preview,
        inputs=[
            training_section["sample_selector"],
            training_section["dataset_builder_state"],
        ],
        outputs=sample_preview_outputs,
    ).then(
        fn=lambda has_raw: gr.update(visible=has_raw),
        inputs=[training_section["has_raw_lyrics_state"]],
        outputs=[training_section["raw_lyrics_display"]],
    )

    training_section["save_edit_btn"].click(
        fn=train_h.save_sample_edit,
        inputs=[
            training_section["sample_selector"],
            training_section["edit_caption"],
            training_section["edit_genre"],
            training_section["prompt_override"],
            training_section["edit_lyrics"],
            training_section["edit_bpm"],
            training_section["edit_keyscale"],
            training_section["edit_timesig"],
            training_section["edit_language"],
            training_section["edit_instrumental"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["audio_files_table"],
            training_section["edit_status"],
            training_section["dataset_builder_state"],
        ],
    )

    for trigger_key in _SETTINGS_TRIGGER_KEYS:
        training_section[trigger_key].change(
            fn=train_h.update_settings,
            inputs=[
                training_section["custom_tag"],
                training_section["tag_position"],
                training_section["all_instrumental"],
                training_section["genre_ratio"],
                training_section["dataset_builder_state"],
            ],
            outputs=[training_section["dataset_builder_state"]],
        )

    training_section["save_dataset_btn"].click(
        fn=train_h.save_dataset,
        inputs=[
            training_section["save_path"],
            training_section["dataset_name"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["save_status"],
            training_section["save_path"],
        ],
    )
