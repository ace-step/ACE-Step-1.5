"""Dataset operations for the training UI.

Contains handlers for scanning directories, auto-labeling samples,
previewing/editing individual samples, updating settings, and saving
datasets to JSON.
"""

from typing import Any, List, Optional, Tuple

import gradio as gr

from acestep.training.dataset_builder import DatasetBuilder
from .training_utils import _safe_slider


def scan_directory(
    audio_dir: str,
    dataset_name: str,
    custom_tag: str,
    tag_position: str,
    all_instrumental: bool,
    builder_state: Optional[DatasetBuilder],
) -> Tuple[Any, str, Any, DatasetBuilder]:
    """Scan a directory for audio files.

    Returns:
        Tuple of (table_data, status, slider_update, builder_state).
    """
    if not audio_dir or not audio_dir.strip():
        return [], "❌ Please enter a directory path", _safe_slider(0, value=0, visible=False), builder_state

    builder = builder_state if builder_state else DatasetBuilder()

    builder.metadata.name = dataset_name
    builder.metadata.custom_tag = custom_tag
    builder.metadata.tag_position = tag_position
    builder.metadata.all_instrumental = all_instrumental

    samples, status = builder.scan_directory(audio_dir.strip())

    if not samples:
        return [], status, _safe_slider(0, value=0, visible=False), builder

    builder.set_all_instrumental(all_instrumental)
    if custom_tag:
        builder.set_custom_tag(custom_tag, tag_position)

    table_data = builder.get_samples_dataframe_data()
    slider_max = max(0, len(samples) - 1)

    return table_data, status, _safe_slider(slider_max, value=0, visible=len(samples) > 1), builder


def auto_label_all(
    dit_handler,
    llm_handler,
    builder_state: Optional[DatasetBuilder],
    skip_metas: bool = False,
    format_lyrics: bool = False,
    transcribe_lyrics: bool = False,
    only_unlabeled: bool = False,
    progress=None,
) -> Tuple[List[List[Any]], str, DatasetBuilder]:
    """Auto-label all samples in the dataset.

    Args:
        dit_handler: DiT handler for audio processing.
        llm_handler: LLM handler for caption generation.
        builder_state: Dataset builder state.
        skip_metas: Skip generating BPM/Key/TimeSig but still generate caption/genre.
        format_lyrics: Use LLM to format user-provided lyrics from .txt files.
        transcribe_lyrics: Use LLM to transcribe lyrics from audio.
        only_unlabeled: Only label samples without caption.
        progress: Progress callback.

    Returns:
        Tuple of (table_data, status, builder_state).
    """
    if builder_state is None:
        return [], "❌ Please scan a directory first", builder_state

    if not builder_state.samples:
        return [], "❌ No samples to label. Please scan a directory first.", builder_state

    if dit_handler is None or dit_handler.model is None:
        return (
            builder_state.get_samples_dataframe_data(),
            "❌ Model not initialized. Please initialize the service first.",
            builder_state,
        )

    if llm_handler is None or not llm_handler.llm_initialized:
        return (
            builder_state.get_samples_dataframe_data(),
            "❌ LLM not initialized. Please initialize the service with LLM enabled.",
            builder_state,
        )

    def progress_callback(msg):
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    samples, status = builder_state.label_all_samples(
        dit_handler=dit_handler,
        llm_handler=llm_handler,
        format_lyrics=format_lyrics,
        transcribe_lyrics=transcribe_lyrics,
        skip_metas=skip_metas,
        only_unlabeled=only_unlabeled,
        progress_callback=progress_callback,
    )

    table_data = builder_state.get_samples_dataframe_data()
    return gr.update(value=table_data), gr.update(value=status), builder_state


def get_sample_preview(
    sample_idx: int,
    builder_state: Optional[DatasetBuilder],
):
    """Get preview data for a specific sample.

    Returns:
        Tuple of (audio_path, filename, caption, genre, prompt_override, lyrics,
                  bpm, keyscale, timesig, duration, language, instrumental,
                  raw_lyrics, raw_lyrics_visible).
    """
    empty = (None, "", "", "", "Use Global Ratio", "", None, "", "", 0.0, "instrumental", True, "", False)

    if builder_state is None or not builder_state.samples:
        return empty

    if sample_idx is None:
        return empty

    idx = int(sample_idx)
    if idx < 0 or idx >= len(builder_state.samples):
        return empty

    sample = builder_state.samples[idx]
    has_raw = sample.has_raw_lyrics()

    if sample.prompt_override == "genre":
        override_choice = "Genre"
    elif sample.prompt_override == "caption":
        override_choice = "Caption"
    else:
        override_choice = "Use Global Ratio"

    display_lyrics = sample.lyrics if sample.lyrics else sample.formatted_lyrics

    return (
        sample.audio_path,
        sample.filename,
        sample.caption,
        sample.genre,
        override_choice,
        display_lyrics,
        sample.bpm,
        sample.keyscale,
        sample.timesignature,
        sample.duration,
        sample.language,
        sample.is_instrumental,
        sample.raw_lyrics if has_raw else "",
        has_raw,
    )


def save_sample_edit(
    sample_idx: int,
    caption: str,
    genre: str,
    prompt_override: str,
    lyrics: str,
    bpm: Optional[int],
    keyscale: str,
    timesig: str,
    language: str,
    is_instrumental: bool,
    builder_state: Optional[DatasetBuilder],
) -> Tuple[List[List[Any]], str, DatasetBuilder]:
    """Save edits to a sample.

    Returns:
        Tuple of (table_data, status, builder_state).
    """
    if builder_state is None:
        return [], "❌ No dataset loaded", builder_state

    idx = int(sample_idx)

    if prompt_override == "Genre":
        override_value = "genre"
    elif prompt_override == "Caption":
        override_value = "caption"
    else:
        override_value = None

    updated_lyrics = lyrics if not is_instrumental else "[Instrumental]"
    updated_formatted = updated_lyrics if updated_lyrics and updated_lyrics != "[Instrumental]" else ""
    sample, status = builder_state.update_sample(
        idx,
        caption=caption,
        genre=genre,
        prompt_override=override_value,
        lyrics=updated_lyrics,
        formatted_lyrics=updated_formatted,
        bpm=int(bpm) if bpm else None,
        keyscale=keyscale,
        timesignature=timesig,
        language="unknown" if is_instrumental else language,
        is_instrumental=is_instrumental,
        labeled=True,
    )

    table_data = builder_state.get_samples_dataframe_data()
    return table_data, status, builder_state


def update_settings(
    custom_tag: str,
    tag_position: str,
    all_instrumental: bool,
    genre_ratio: int,
    builder_state: Optional[DatasetBuilder],
) -> DatasetBuilder:
    """Update dataset settings.

    Returns:
        Updated builder_state.
    """
    if builder_state is None:
        return builder_state

    if custom_tag:
        builder_state.set_custom_tag(custom_tag, tag_position)

    builder_state.set_all_instrumental(all_instrumental)
    builder_state.metadata.genre_ratio = int(genre_ratio)

    return builder_state


def save_dataset(
    save_path: str,
    dataset_name: str,
    builder_state: Optional[DatasetBuilder],
) -> Tuple[str, Any]:
    """Save the dataset to a JSON file.

    Returns:
        Tuple of (status, save_path_update).
    """
    if builder_state is None:
        return "❌ No dataset to save. Please scan a directory first.", gr.update()

    if not builder_state.samples:
        return "❌ No samples in dataset.", gr.update()

    if not save_path or not save_path.strip():
        return "❌ Please enter a save path.", gr.update()

    save_path = save_path.strip()
    if not save_path.lower().endswith(".json"):
        save_path = save_path + ".json"

    labeled_count = builder_state.get_labeled_count()
    if labeled_count == 0:
        return (
            "⚠️ Warning: No samples have been labeled. Consider auto-labeling first.\nSaving anyway...",
            gr.update(value=save_path),
        )

    return builder_state.save_dataset(save_path, dataset_name), gr.update(value=save_path)
