"""
Event Handlers for Training Tab

Contains all event handler functions for the dataset builder and training UI.
"""

import os
import json
from typing import Any, Dict, List, Tuple, Optional
from loguru import logger
import gradio as gr

from acestep.training.dataset_builder import DatasetBuilder, AudioSample


def create_dataset_builder() -> DatasetBuilder:
    """Create a new DatasetBuilder instance."""
    return DatasetBuilder()


def _safe_slider(max_value: int, value: int = 0, visible: Optional[bool] = None) -> gr.Slider:
    """Create a slider with a non-zero range to avoid Gradio math errors."""
    max_value = max(1, int(max_value))
    kwargs = {"maximum": max_value, "value": min(int(value), max_value)}
    if visible is not None:
        kwargs["visible"] = visible
    return gr.Slider(**kwargs)

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
        Tuple of (table_data, status, slider_update, builder_state)
    """
    if not audio_dir or not audio_dir.strip():
        return [], "âŒ Please enter a directory path", _safe_slider(0, value=0, visible=False), builder_state
    
    # Create or use existing builder
    builder = builder_state if builder_state else DatasetBuilder()
    
    # Set metadata before scanning
    builder.metadata.name = dataset_name
    builder.metadata.custom_tag = custom_tag
    builder.metadata.tag_position = tag_position
    builder.metadata.all_instrumental = all_instrumental
    
    # Scan directory
    samples, status = builder.scan_directory(audio_dir.strip())
    
    if not samples:
        return [], status, _safe_slider(0, value=0, visible=False), builder
    
    # Set instrumental and tag for all samples
    builder.set_all_instrumental(all_instrumental)
    if custom_tag:
        builder.set_custom_tag(custom_tag, tag_position)
    
    # Get table data
    table_data = builder.get_samples_dataframe_data()
    
    # Calculate slider max and return as Slider update
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
        dit_handler: DiT handler for audio processing
        llm_handler: LLM handler for caption generation
        builder_state: Dataset builder state
        skip_metas: If True, skip generating BPM/Key/TimeSig but still generate caption/genre
        format_lyrics: If True, use LLM to format user-provided lyrics from .txt files
        transcribe_lyrics: If True, use LLM to transcribe lyrics from audio (ignores .txt files)
        only_unlabeled: If True, only label samples without caption
        progress: Progress callback

    Returns:
        Tuple of (table_data, status, builder_state)
    """
    if builder_state is None:
        return [], "âŒ Please scan a directory first", builder_state

    if not builder_state.samples:
        return [], "âŒ No samples to label. Please scan a directory first.", builder_state

    # Check if handlers are initialized
    if dit_handler is None or dit_handler.model is None:
        return builder_state.get_samples_dataframe_data(), "âŒ Model not initialized. Please initialize the service first.", builder_state

    if llm_handler is None or not llm_handler.llm_initialized:
        return builder_state.get_samples_dataframe_data(), "âŒ LLM not initialized. Please initialize the service with LLM enabled.", builder_state

    def progress_callback(msg):
        if progress:
            try:
                progress(msg)
            except:
                pass

    # Label all samples (skip_metas only skips BPM/Key/TimeSig, still generates caption/genre)
    samples, status = builder_state.label_all_samples(
        dit_handler=dit_handler,
        llm_handler=llm_handler,
        format_lyrics=format_lyrics,
        transcribe_lyrics=transcribe_lyrics,
        skip_metas=skip_metas,
        only_unlabeled=only_unlabeled,
        progress_callback=progress_callback,
    )

    # Get updated table data
    table_data = builder_state.get_samples_dataframe_data()

    return table_data, status, builder_state


def get_sample_preview(
    sample_idx: int,
    builder_state: Optional[DatasetBuilder],
):
    """Get preview data for a specific sample.

    Returns:
        Tuple of (audio_path, filename, caption, genre, prompt_override, lyrics, bpm, keyscale, timesig,
                  duration, language, instrumental, raw_lyrics, raw_lyrics_visible)
    """
    empty = (None, "", "", "", "Use Global Ratio", "", None, "", "", 0.0, "instrumental", True, "", False)

    if builder_state is None or not builder_state.samples:
        return empty

    idx = int(sample_idx)
    if idx < 0 or idx >= len(builder_state.samples):
        return empty

    sample = builder_state.samples[idx]

    # Show raw lyrics panel only when raw lyrics exist
    has_raw = sample.has_raw_lyrics()

    # Convert prompt_override to dropdown choice
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
        Tuple of (table_data, status, builder_state)
    """
    if builder_state is None:
        return [], "âŒ No dataset loaded", builder_state

    idx = int(sample_idx)

    # Convert dropdown choice to prompt_override value
    if prompt_override == "Genre":
        override_value = "genre"
    elif prompt_override == "Caption":
        override_value = "caption"
    else:
        override_value = None  # Use Global Ratio

    # Update sample
    sample, status = builder_state.update_sample(
        idx,
        caption=caption,
        genre=genre,
        prompt_override=override_value,
        lyrics=lyrics if not is_instrumental else "[Instrumental]",
        bpm=int(bpm) if bpm else None,
        keyscale=keyscale,
        timesignature=timesig,
        language="unknown" if is_instrumental else language,
        is_instrumental=is_instrumental,
        labeled=True,
    )

    # Get updated table data
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
        Updated builder_state
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
) -> str:
    """Save the dataset to a JSON file.
    
    Returns:
        Status message
    """
    if builder_state is None:
        return "âŒ No dataset to save. Please scan a directory first."
    
    if not builder_state.samples:
        return "âŒ No samples in dataset."
    
    if not save_path or not save_path.strip():
        return "âŒ Please enter a save path."
    
    # Check if any samples are labeled
    labeled_count = builder_state.get_labeled_count()
    if labeled_count == 0:
        return "âš ï¸ Warning: No samples have been labeled. Consider auto-labeling first.\nSaving anyway..."
    
    return builder_state.save_dataset(save_path.strip(), dataset_name)


def load_existing_dataset_for_preprocess(
    dataset_path: str,
    builder_state: Optional[DatasetBuilder],
):
    """Load an existing dataset JSON file for preprocessing.

    This allows users to load a previously saved dataset and proceed to preprocessing
    without having to re-scan and re-label.

    Returns:
        Tuple of (status, table_data, slider_update, builder_state,
                  audio_path, filename, caption, genre, prompt_override,
                  lyrics, bpm, keyscale, timesig, duration, language, instrumental,
                  raw_lyrics, has_raw)
    """
    # Empty preview: (audio_path, filename, caption, genre, prompt_override, lyrics, bpm, keyscale, timesig, duration, language, instrumental, raw_lyrics, has_raw)
    empty_preview = (None, "", "", "", "Use Global Ratio", "", None, "", "", 0.0, "instrumental", True, "", False)

    if not dataset_path or not dataset_path.strip():
        updates = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
        return ("âŒ Please enter a dataset path", [], _safe_slider(0, value=0, visible=False), builder_state) + empty_preview + updates

    dataset_path = dataset_path.strip()

    if not os.path.exists(dataset_path):
        updates = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
        return (f"âŒ Dataset not found: {dataset_path}", [], _safe_slider(0, value=0, visible=False), builder_state) + empty_preview + updates

    # Create new builder (don't reuse old state when loading a file)
    builder = DatasetBuilder()

    # Load the dataset
    samples, status = builder.load_dataset(dataset_path)

    if not samples:
        updates = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
        return (status, [], _safe_slider(0, value=0, visible=False), builder) + empty_preview + updates

    # Get table data
    table_data = builder.get_samples_dataframe_data()

    # Calculate slider max
    slider_max = max(0, len(samples) - 1)

    # Create info text
    labeled_count = builder.get_labeled_count()
    info = f"âœ… Loaded dataset: {builder.metadata.name}\n"
    info += f"ðŸ“Š Samples: {len(samples)} ({labeled_count} labeled)\n"
    info += f"ðŸ·ï¸ Custom Tag: {builder.metadata.custom_tag or '(none)'}\n"
    info += "ðŸ“ Ready for preprocessing! You can also edit samples below."
    if any((s.formatted_lyrics and not s.lyrics) for s in builder.samples):
        info += "\nâ„¹ï¸ Showing formatted lyrics where lyrics are empty."

    # Get first sample preview
    first_sample = builder.samples[0]
    has_raw = first_sample.has_raw_lyrics()

    # Convert prompt_override to dropdown choice
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

    return (info, table_data, _safe_slider(slider_max, value=0, visible=len(samples) > 1), builder) + preview + updates


def preprocess_dataset(
    output_dir: str,
    dit_handler,
    builder_state: Optional[DatasetBuilder],
    progress=None,
) -> str:
    """Preprocess dataset to tensor files for fast training.
    
    This converts audio files to VAE latents and text to embeddings.
    
    Returns:
        Status message
    """
    if builder_state is None:
        return "âŒ No dataset loaded. Please scan a directory first."
    
    if not builder_state.samples:
        return "âŒ No samples in dataset."
    
    labeled_count = builder_state.get_labeled_count()
    if labeled_count == 0:
        return "âŒ No labeled samples. Please auto-label or manually label samples first."
    
    if not output_dir or not output_dir.strip():
        return "âŒ Please enter an output directory."
    
    if dit_handler is None or dit_handler.model is None:
        return "âŒ Model not initialized. Please initialize the service first."
    
    def progress_callback(msg):
        if progress:
            try:
                progress(msg)
            except:
                pass
    
    # Run preprocessing
    output_paths, status = builder_state.preprocess_to_tensors(
        dit_handler=dit_handler,
        output_dir=output_dir.strip(),
        progress_callback=progress_callback,
    )
    
    return status


def load_training_dataset(
    tensor_dir: str,
) -> str:
    """Load a preprocessed tensor dataset for training.
    
    Returns:
        Info text about the dataset
    """
    if not tensor_dir or not tensor_dir.strip():
        return "âŒ Please enter a tensor directory path"
    
    tensor_dir = tensor_dir.strip()
    
    if not os.path.exists(tensor_dir):
        return f"âŒ Directory not found: {tensor_dir}"
    
    if not os.path.isdir(tensor_dir):
        return f"âŒ Not a directory: {tensor_dir}"
    
    # Check for manifest
    manifest_path = os.path.join(tensor_dir, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            num_samples = manifest.get("num_samples", 0)
            metadata = manifest.get("metadata", {})
            name = metadata.get("name", "Unknown")
            custom_tag = metadata.get("custom_tag", "")
            
            info = f"âœ… Loaded preprocessed dataset: {name}\n"
            info += f"ðŸ“Š Samples: {num_samples} preprocessed tensors\n"
            info += f"ðŸ·ï¸ Custom Tag: {custom_tag or '(none)'}"
            
            return info
        except Exception as e:
            logger.warning(f"Failed to read manifest: {e}")
    
    # Fallback: count .pt files
    pt_files = [f for f in os.listdir(tensor_dir) if f.endswith('.pt')]
    
    if not pt_files:
        return f"âŒ No .pt tensor files found in {tensor_dir}"
    
    info = f"âœ… Found {len(pt_files)} tensor files in {tensor_dir}\n"
    info += "âš ï¸ No manifest.json found - using all .pt files"
    
    return info


# Training handlers

import time
import re


def _format_duration(seconds):
    """Format seconds to human readable string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def start_training(
    tensor_dir: str,
    dit_handler,
    lora_rank: int,
    lora_alpha: int,
    lora_dropout: float,
    learning_rate: float,
    train_epochs: int,
    train_batch_size: int,
    gradient_accumulation: int,
    save_every_n_epochs: int,
    training_shift: float,
    training_seed: int,
    lora_output_dir: str,
    training_state: Dict,
    progress=None,
):
    """Start LoRA training from preprocessed tensors.
    
    This is a generator function that yields progress updates.
    """
    if not tensor_dir or not tensor_dir.strip():
        yield "âŒ Please enter a tensor directory path", "", None, training_state
        return
    
    tensor_dir = tensor_dir.strip()
    
    if not os.path.exists(tensor_dir):
        yield f"âŒ Tensor directory not found: {tensor_dir}", "", None, training_state
        return
    
    if dit_handler is None or dit_handler.model is None:
        yield "âŒ Model not initialized. Please initialize the service first.", "", None, training_state
        return
    
    # Check for required training dependencies
    try:
        from lightning.fabric import Fabric
        from peft import get_peft_model, LoraConfig
    except ImportError as e:
        yield f"âŒ Missing required packages: {e}\nPlease install: pip install peft lightning", "", None, training_state
        return
    
    training_state["is_training"] = True
    training_state["should_stop"] = False
    
    try:
        from acestep.training.trainer import LoRATrainer
        from acestep.training.configs import LoRAConfig as LoRAConfigClass, TrainingConfig
        
        # Create configs
        lora_config = LoRAConfigClass(
            r=lora_rank,
            alpha=lora_alpha,
            dropout=lora_dropout,
        )
        
        training_config = TrainingConfig(
            shift=training_shift,
            learning_rate=learning_rate,
            batch_size=train_batch_size,
            gradient_accumulation_steps=gradient_accumulation,
            max_epochs=train_epochs,
            save_every_n_epochs=save_every_n_epochs,
            seed=training_seed,
            output_dir=lora_output_dir,
        )
        
        import pandas as pd
        
        # Initialize training log and loss history
        log_lines = []
        loss_data = pd.DataFrame({"step": [0], "loss": [0.0]})
        
        # Start timer
        start_time = time.time()
        
        yield f"ðŸš€ Starting training from {tensor_dir}...", "", loss_data, training_state
        
        # Create trainer
        trainer = LoRATrainer(
            dit_handler=dit_handler,
            lora_config=lora_config,
            training_config=training_config,
        )
        
        # Collect loss history
        step_list = []
        loss_list = []
        
        # Train with progress updates using preprocessed tensors
        for step, loss, status in trainer.train_from_preprocessed(tensor_dir, training_state):
            # Calculate elapsed time and ETA
            elapsed_seconds = time.time() - start_time
            time_info = f"â±ï¸ Elapsed: {_format_duration(elapsed_seconds)}"
            
            # Parse "Epoch x/y" from status to calculate ETA
            match = re.search(r"Epoch\s+(\d+)/(\d+)", str(status))
            if match:
                current_ep = int(match.group(1))
                total_ep = int(match.group(2))
                if current_ep > 0:
                    eta_seconds = (elapsed_seconds / current_ep) * (total_ep - current_ep)
                    time_info += f" | ETA: ~{_format_duration(eta_seconds)}"
            
            # Display status with time info
            display_status = f"{status}\n{time_info}"
            
            # Terminal log
            log_msg = f"[{_format_duration(elapsed_seconds)}] Step {step}: {status}"
            logger.info(log_msg)
            
            # Add to UI log
            log_lines.append(status)
            if len(log_lines) > 15:
                log_lines = log_lines[-15:]
            log_text = "\n".join(log_lines)
            
            # Track loss for plot (only valid values)
            if step > 0 and loss is not None and loss == loss:  # Check for NaN
                step_list.append(step)
                loss_list.append(float(loss))
                loss_data = pd.DataFrame({"step": step_list, "loss": loss_list})
            
            yield display_status, log_text, loss_data, training_state
            
            if training_state.get("should_stop", False):
                logger.info("â¹ï¸ Training stopped by user")
                log_lines.append("â¹ï¸ Training stopped by user")
                yield f"â¹ï¸ Stopped ({time_info})", "\n".join(log_lines[-15:]), loss_data, training_state
                break
        
        total_time = time.time() - start_time
        training_state["is_training"] = False
        completion_msg = f"âœ… Training completed! Total time: {_format_duration(total_time)}"
        
        logger.info(completion_msg)
        log_lines.append(completion_msg)
        
        yield completion_msg, "\n".join(log_lines[-15:]), loss_data, training_state
        
    except Exception as e:
        logger.exception("Training error")
        training_state["is_training"] = False
        import pandas as pd
        empty_df = pd.DataFrame({"step": [], "loss": []})
        yield f"âŒ Error: {str(e)}", str(e), empty_df, training_state


def stop_training(training_state: Dict) -> Tuple[str, Dict]:
    """Stop the current training process.
    
    Returns:
        Tuple of (status, training_state)
    """
    if not training_state.get("is_training", False):
        return "âš ï¸ No training in progress", training_state
    
    training_state["should_stop"] = True
    return "â¹ï¸ Stopping training...", training_state


def export_lora(
    export_path: str,
    lora_output_dir: str,
) -> str:
    """Export the trained LoRA weights.
    
    Returns:
        Status message
    """
    if not export_path or not export_path.strip():
        return "âŒ Please enter an export path"
    
    # Check if there's a trained model to export
    final_dir = os.path.join(lora_output_dir, "final")
    checkpoint_dir = os.path.join(lora_output_dir, "checkpoints")
    
    # Prefer final, fallback to checkpoints
    if os.path.exists(final_dir):
        source_path = final_dir
    elif os.path.exists(checkpoint_dir):
        # Find the latest checkpoint
        checkpoints = [d for d in os.listdir(checkpoint_dir) if d.startswith("epoch_")]
        if not checkpoints:
            return "âŒ No checkpoints found"
        
        checkpoints.sort(key=lambda x: int(x.split("_")[1]))
        latest = checkpoints[-1]
        source_path = os.path.join(checkpoint_dir, latest)
    else:
        return f"âŒ No trained model found in {lora_output_dir}"
    
    try:
        import shutil
        
        export_path = export_path.strip()
        os.makedirs(os.path.dirname(export_path) if os.path.dirname(export_path) else ".", exist_ok=True)
        
        if os.path.exists(export_path):
            shutil.rmtree(export_path)
        
        shutil.copytree(source_path, export_path)
        
        return f"âœ… LoRA exported to {export_path}"
        
    except Exception as e:
        logger.exception("Export error")
        return f"âŒ Export failed: {str(e)}"





