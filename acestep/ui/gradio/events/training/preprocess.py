"""Preprocessing and dataset loading for the training UI.

Contains handlers for loading existing datasets, preprocessing
audio to tensor files, and loading preprocessed tensor datasets.
"""

import os
import json
from typing import Any, Optional

import gradio as gr
from loguru import logger

from acestep.training.dataset_builder import DatasetBuilder
from acestep.training.path_safety import safe_path
from acestep.debug_utils import debug_log_for, debug_start_for, debug_end_for
from .training_utils import _safe_slider


def load_existing_dataset_for_preprocess(
    dataset_path: str,
    builder_state: Optional[DatasetBuilder],
):
    """Load an existing dataset JSON file for preprocessing.

    This allows users to load a previously saved dataset and proceed to
    preprocessing without having to re-scan and re-label.

    Returns:
        Tuple of (status, table_data, slider_update, builder_state,
                  audio_path, filename, caption, genre, prompt_override,
                  lyrics, bpm, keyscale, timesig, duration, language,
                  instrumental, raw_lyrics, has_raw,
                  name_update, tag_update, pos_update, instr_update,
                  ratio_update).
    """
    empty_preview = (
        None, "", "", "", "Use Global Ratio", "",
        None, "", "", 0.0, "instrumental", True, "", False,
    )

    if not dataset_path or not dataset_path.strip():
        updates = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
        return (
            "❌ Please enter a dataset path",
            [],
            _safe_slider(0, value=0, visible=False),
            builder_state,
        ) + empty_preview + updates

    try:
        dataset_path = safe_path(dataset_path.strip())
    except ValueError:
        updates = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
        return (
            f"❌ Rejected unsafe dataset path: {dataset_path}",
            [],
            _safe_slider(0, value=0, visible=False),
            builder_state,
        ) + empty_preview + updates

    debug_log_for("dataset", f"UI load_existing_dataset_for_preprocess: path='{dataset_path}'")

    if not os.path.exists(dataset_path):
        updates = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
        return (
            f"❌ Dataset not found: {dataset_path}",
            [],
            _safe_slider(0, value=0, visible=False),
            builder_state,
        ) + empty_preview + updates

    builder = DatasetBuilder()

    t0 = debug_start_for("dataset", "load_dataset")
    samples, status = builder.load_dataset(dataset_path)
    debug_end_for("dataset", "load_dataset", t0)

    if not samples:
        updates = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
        return (
            status,
            [],
            _safe_slider(0, value=0, visible=False),
            builder,
        ) + empty_preview + updates

    table_data = builder.get_samples_dataframe_data()
    slider_max = max(0, len(samples) - 1)

    labeled_count = builder.get_labeled_count()
    info = f"📂 Loaded dataset: {builder.metadata.name}\n"
    info += f"🔢 Samples: {len(samples)} ({labeled_count} labeled)\n"
    info += f"🏷️ Custom Tag: {builder.metadata.custom_tag or '(none)'}\n"
    info += "✅ Ready for preprocessing! You can also edit samples below."
    if any((s.formatted_lyrics and not s.lyrics) for s in builder.samples):
        info += "\nℹ️ Showing formatted lyrics where lyrics are empty."

    first_sample = builder.samples[0]
    has_raw = first_sample.has_raw_lyrics()

    if first_sample.prompt_override == "genre":
        override_choice = "Genre"
    elif first_sample.prompt_override == "caption":
        override_choice = "Caption"
    else:
        override_choice = "Use Global Ratio"

    display_lyrics = first_sample.lyrics if first_sample.lyrics else first_sample.formatted_lyrics

    preview = (
        first_sample.audio_path,
        first_sample.filename,
        first_sample.caption,
        first_sample.genre,
        override_choice,
        display_lyrics,
        first_sample.bpm,
        first_sample.keyscale,
        first_sample.timesignature,
        first_sample.duration,
        first_sample.language,
        first_sample.is_instrumental,
        first_sample.raw_lyrics if has_raw else "",
        has_raw,
    )

    updates = (
        gr.update(value=builder.metadata.name),
        gr.update(value=builder.metadata.custom_tag),
        gr.update(value=builder.metadata.tag_position),
        gr.update(value=builder.metadata.all_instrumental),
        gr.update(value=builder.metadata.genre_ratio),
    )

    return (
        info,
        table_data,
        _safe_slider(slider_max, value=0, visible=len(samples) > 1),
        builder,
    ) + preview + updates


def preprocess_dataset(
    output_dir: str,
    preprocess_mode: str,
    dit_handler,
    builder_state: Optional[DatasetBuilder],
    progress=None,
) -> str:
    """Preprocess dataset to tensor files for fast training.

    Converts audio files to VAE latents and text to embeddings.

    Returns:
        Status message.
    """
    if builder_state is None:
        return "❌ No dataset loaded. Please scan a directory first."

    if not builder_state.samples:
        return "❌ No samples in dataset."

    labeled_count = builder_state.get_labeled_count()
    if labeled_count == 0:
        return "❌ No labeled samples. Please auto-label or manually label samples first."

    if not output_dir or not output_dir.strip():
        return "❌ Please enter an output directory."

    if dit_handler is None or dit_handler.model is None:
        return "❌ Model not initialized. Please initialize the service first."

    def progress_callback(msg):
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    mode = str(preprocess_mode or "lora").strip().lower()
    if mode not in {"lora", "lokr"}:
        mode = "lora"

    t0 = debug_start_for("dataset", "preprocess_to_tensors")
    output_paths, status = builder_state.preprocess_to_tensors(
        dit_handler=dit_handler,
        output_dir=output_dir.strip(),
        preprocess_mode=mode,
        progress_callback=progress_callback,
    )
    debug_end_for("dataset", "preprocess_to_tensors", t0)

    return status


def load_training_dataset(tensor_dir: str) -> str:
    """Load a preprocessed tensor dataset for training.

    Returns:
        Info text about the dataset.
    """
    if not tensor_dir or not tensor_dir.strip():
        return "❌ Please enter a tensor directory path"

    try:
        tensor_dir = safe_path(tensor_dir.strip())
    except ValueError:
        return f"❌ Rejected unsafe tensor directory path: {tensor_dir}"

    if not os.path.exists(tensor_dir):
        return f"❌ Directory not found: {tensor_dir}"

    if not os.path.isdir(tensor_dir):
        return f"❌ Not a directory: {tensor_dir}"

    manifest_path = os.path.join(tensor_dir, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)

            num_samples = manifest.get("num_samples", 0)
            metadata = manifest.get("metadata", {})
            name = metadata.get("name", "Unknown")
            custom_tag = metadata.get("custom_tag", "")

            info = f"📂 Loaded preprocessed dataset: {name}\n"
            info += f"🔢 Samples: {num_samples} preprocessed tensors\n"
            info += f"🏷️ Custom Tag: {custom_tag or '(none)'}"

            return info
        except Exception as e:
            logger.warning(f"Failed to read manifest: {e}")

    pt_files = [f for f in os.listdir(tensor_dir) if f.endswith(".pt")]

    if not pt_files:
        return f"❌ No .pt tensor files found in {tensor_dir}"

    info = f"📂 Found {len(pt_files)} tensor files in {tensor_dir}\n"
    info += "ℹ️ No manifest.json found - using all .pt files"

    return info
