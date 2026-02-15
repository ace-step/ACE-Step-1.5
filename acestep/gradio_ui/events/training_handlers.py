"""
Event Handlers for Training Tab

Contains all event handler functions for the dataset builder and training UI.
"""

import os
import json
from typing import Any, Dict, List, Tuple, Optional
from loguru import logger
import gradio as gr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from acestep.training.dataset_builder import DatasetBuilder, AudioSample
from acestep.debug_utils import debug_log_for, debug_start_for, debug_end_for
from acestep.gpu_config import get_global_gpu_config
from acestep.gradio_ui.i18n import t

SAFE_TRAINING_ROOT = os.path.abspath(os.getcwd())


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

    # Force UI refresh for table and status
    return gr.update(value=table_data), gr.update(value=status), builder_state


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

    if sample_idx is None:
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
) -> Tuple[str, Any]:
    """Save the dataset to a JSON file.
    
    Returns:
        Status message
    """
    if builder_state is None:
        return "âŒ No dataset to save. Please scan a directory first.", gr.update()
    
    if not builder_state.samples:
        return "âŒ No samples in dataset.", gr.update()
    
    if not save_path or not save_path.strip():
        return "âŒ Please enter a save path.", gr.update()
    
    save_path = save_path.strip()
    if not save_path.lower().endswith(".json"):
        save_path = save_path + ".json"
    
    # Check if any samples are labeled
    labeled_count = builder_state.get_labeled_count()
    if labeled_count == 0:
        return "âš ï¸ Warning: No samples have been labeled. Consider auto-labeling first.\nSaving anyway...", gr.update(value=save_path)

    return builder_state.save_dataset(save_path, dataset_name), gr.update(value=save_path)


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
    debug_log_for("dataset", f"UI load_existing_dataset_for_preprocess: path='{dataset_path}'")

    if not os.path.exists(dataset_path):
        updates = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
        return (f"âŒ Dataset not found: {dataset_path}", [], _safe_slider(0, value=0, visible=False), builder_state) + empty_preview + updates

    # Create new builder (don't reuse old state when loading a file)
    builder = DatasetBuilder()

    # Load the dataset
    t0 = debug_start_for("dataset", "load_dataset")
    samples, status = builder.load_dataset(dataset_path)
    debug_end_for("dataset", "load_dataset", t0)

    if not samples:
        updates = (gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
        return (status, [], _safe_slider(0, value=0, visible=False), builder) + empty_preview + updates

    # Get table data
    table_data = builder.get_samples_dataframe_data()

    # Calculate slider max
    slider_max = max(0, len(samples) - 1)

    # Create info text
    labeled_count = builder.get_labeled_count()
    info = f"ðŸ“‚ Loaded dataset: {builder.metadata.name}\n"
    info += f"ðŸ”¢ Samples: {len(samples)} ({labeled_count} labeled)\n"
    info += f"ðŸ·ï¸ Custom Tag: {builder.metadata.custom_tag or '(none)'}\n"
    info += "âœ… Ready for preprocessing! You can also edit samples below."
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
    preprocess_mode: str,
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
            
            info = f"ðŸ“‚ Loaded preprocessed dataset: {name}\n"
            info += f"ðŸ”¢ Samples: {num_samples} preprocessed tensors\n"
            info += f"ðŸ·ï¸ Custom Tag: {custom_tag or '(none)'}"
            
            return info
        except Exception as e:
            logger.warning(f"Failed to read manifest: {e}")
    
    # Fallback: count .pt files
    pt_files = [f for f in os.listdir(tensor_dir) if f.endswith('.pt')]
    
    if not pt_files:
        return f"âŒ No .pt tensor files found in {tensor_dir}"
    
    info = f"ðŸ“‚ Found {len(pt_files)} tensor files in {tensor_dir}\n"
    info += "â„¹ï¸ No manifest.json found - using all .pt files"
    
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


def _training_loss_figure(
    training_state: Dict,
    step_list: List[int],
    loss_list: List[float],
) -> Optional[Any]:
    """Build a training/validation loss plot (matplotlib Figure) for gr.Plot."""
    steps = training_state.get("plot_steps") or step_list
    loss = training_state.get("plot_loss") or loss_list
    if not steps or not loss:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.set_xlabel("Step")
        ax.set_ylabel("Loss")
        ax.set_title("Training loss")
        fig.tight_layout()
        return fig
    ema = training_state.get("plot_ema")
    val_steps = training_state.get("plot_val_steps") or []
    val_loss = training_state.get("plot_val_loss") or []
    best_step = training_state.get("plot_best_step")

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(steps, loss, color="tab:blue", alpha=0.35, label="Loss (raw)", linewidth=1)
    if ema and len(ema) == len(steps):
        ax.plot(steps, ema, color="tab:blue", alpha=1.0, label="Loss (smoothed)", linewidth=1.5)
    if val_steps and val_loss:
        ax.scatter(val_steps, val_loss, color="tab:orange", s=24, zorder=5, label="Validation")
    if best_step is not None:
        ax.axvline(x=best_step, color="tab:green", linestyle="--", alpha=0.8, label="Best checkpoint")
    ax.set_xlabel("Step")
    ax.set_ylabel("Loss")
    ax.set_title("Training loss")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


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
    resume_checkpoint_dir: str,
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
    
    # Training preset: LoRA training must run on non-quantized DiT.
    if getattr(dit_handler, "quantization", None) is not None:
        gpu_config = get_global_gpu_config()
        if gpu_config.gpu_memory_gb <= 0:
            yield (
                "WARNING: CPU-only training detected. Using best-effort training path "
                "(non-quantized DiT). Performance will be sub-optimal.",
                "",
                None,
                training_state,
            )
        elif gpu_config.tier in {"tier1", "tier2", "tier3", "tier4"}:
            yield (
                f"WARNING: Low VRAM tier detected ({gpu_config.gpu_memory_gb:.1f} GB, {gpu_config.tier}). "
                "Using best-effort training path (non-quantized DiT). Performance may be sub-optimal.",
                "",
                None,
                training_state,
            )

        yield "Switching model to training preset (disable quantization)...", "", None, training_state
        if hasattr(dit_handler, "switch_to_training_preset"):
            switch_status, switched = dit_handler.switch_to_training_preset()
            if not switched:
                yield f"âŒ {switch_status}", "", None, training_state
                return
            yield f"âœ… {switch_status}", "", None, training_state
        else:
            yield "âŒ Training requires non-quantized DiT, and auto-switch is unavailable in this build.", "", None, training_state
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
        
        device_attr = getattr(dit_handler, "device", "")
        if hasattr(device_attr, "type"):
            device_type = str(device_attr.type).lower()
        else:
            device_type = str(device_attr).split(":", 1)[0].lower()

        # Use device-tuned dataloader defaults while preserving CUDA acceleration.
        if device_type == "cuda":
            num_workers = 4
            pin_memory = True
            prefetch_factor = 2
            persistent_workers = True
            pin_memory_device = "cuda"
            mixed_precision = "bf16"
        elif device_type == "xpu":
            num_workers = 4
            pin_memory = True
            prefetch_factor = 2
            persistent_workers = True
            pin_memory_device = ""
            mixed_precision = "bf16"
        elif device_type == "mps":
            num_workers = 0
            pin_memory = False
            prefetch_factor = 2
            persistent_workers = False
            pin_memory_device = ""
            mixed_precision = "fp16"
        else:
            cpu_count = os.cpu_count() or 2
            num_workers = min(4, max(1, cpu_count // 2))
            pin_memory = False
            prefetch_factor = 2
            persistent_workers = num_workers > 0
            pin_memory_device = ""
            mixed_precision = "fp32"

        logger.info(
            f"Training loader config: device={device_type}, workers={num_workers}, "
            f"pin_memory={pin_memory}, pin_memory_device={pin_memory_device}, "
            f"persistent_workers={persistent_workers}"
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
            num_workers=num_workers,
            pin_memory=pin_memory,
            prefetch_factor=prefetch_factor,
            persistent_workers=persistent_workers,
            pin_memory_device=pin_memory_device,
            mixed_precision=mixed_precision,
        )
        
        # Initialize training log and loss history
        log_lines = []
        step_list = []
        loss_list = []
        initial_plot = _training_loss_figure(training_state, step_list, loss_list)
        
        # Start timer
        start_time = time.time()
        
        yield f"ðŸš€ Starting training from {tensor_dir}...", "", initial_plot, training_state
        
        # Create trainer
        trainer = LoRATrainer(
            dit_handler=dit_handler,
            lora_config=lora_config,
            training_config=training_config,
        )
        
        training_failed = False
        failure_message = ""
        
        resume_from = None
        if resume_checkpoint_dir and resume_checkpoint_dir.strip():
            normalized_resume = _safe_join(SAFE_TRAINING_ROOT, resume_checkpoint_dir.strip())
            if normalized_resume and os.path.exists(normalized_resume):
                resume_from = normalized_resume
        
        for step, loss, status in trainer.train_from_preprocessed(tensor_dir, training_state, resume_from=resume_from):
            status_text = str(status)
            status_lower = status_text.lower()
            if (
                status_text.startswith("Ã¢ÂÅ’")
                or status_text.startswith("âŒ")
                or "training failed" in status_lower
                or "error:" in status_lower
                or "module not found" in status_lower
            ):
                training_failed = True
                failure_message = status_text
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
            
            plot_figure = _training_loss_figure(training_state, step_list, loss_list)
            yield display_status, log_text, plot_figure, training_state
            
            if training_state.get("should_stop", False):
                logger.info("â¹ï¸ Training stopped by user")
                log_lines.append("â¹ï¸ Training stopped by user")
                yield f"â¹ï¸ Stopped ({time_info})", "\n".join(log_lines[-15:]), plot_figure, training_state
                break
        
        total_time = time.time() - start_time
        training_state["is_training"] = False
        final_plot = _training_loss_figure(training_state, step_list, loss_list)
        if training_failed:
            final_msg = f"{failure_message}\nElapsed: {_format_duration(total_time)}"
            logger.warning(final_msg)
            log_lines.append(failure_message)
            yield final_msg, "\n".join(log_lines[-15:]), final_plot, training_state
            return
        completion_msg = f"âœ… Training completed! Total time: {_format_duration(total_time)}"
        
        logger.info(completion_msg)
        log_lines.append(completion_msg)
        
        yield completion_msg, "\n".join(log_lines[-15:]), final_plot, training_state
        
    except Exception as e:
        logger.exception("Training error")
        training_state["is_training"] = False
        yield f"âŒ Error: {str(e)}", str(e), _training_loss_figure({}, [], []), training_state

def _safe_join(base_root: str, user_path: str) -> Optional[str]:
    """Safely join user path to base root, preventing directory traversal."""
    if not user_path or not user_path.strip():
        return None
    candidate = user_path.strip()
    if os.path.isabs(candidate):
        return None
    abs_root = os.path.abspath(base_root)
    joined = os.path.abspath(os.path.join(abs_root, candidate))
    try:
        common = os.path.commonpath([abs_root, joined])
    except ValueError:
        return None
    if common != abs_root:
        return None
    return joined



def stop_training(training_state: Dict) -> Tuple[str, Dict]:
    """Stop the current training process.
    
    Returns:
        Tuple of (status, training_state)
    """
    if not training_state.get("is_training", False):
        return t("training.stop_no_training"), training_state
    
    training_state["should_stop"] = True
    return t("training.stop_stopping"), training_state


def export_lora(
    export_path: str,
    lora_output_dir: str,
) -> str:
    """Export the trained LoRA weights.
    
    Returns:
        Status message
    """
    if not export_path or not export_path.strip():
        return t("training.export_path_required")
    # Resolve and validate the base LoRA output directory within the safe root
    safe_lora_dir = _safe_join(SAFE_TRAINING_ROOT, lora_output_dir)
    if safe_lora_dir is None:
        return t("training.invalid_lora_output_dir")
    
    
    # Check if there's a trained model to export
    final_dir = os.path.join(safe_lora_dir, "final")
    checkpoint_dir = os.path.join(safe_lora_dir, "checkpoints")
    
    # Prefer final, fallback to checkpoints
    if os.path.exists(final_dir):
        source_path = final_dir
    elif os.path.exists(checkpoint_dir):
        # Find the latest checkpoint
        checkpoints = [d for d in os.listdir(checkpoint_dir) if d.startswith("epoch_")]
        if not checkpoints:
            return t("training.no_checkpoints_found")
        
        checkpoints.sort(key=lambda x: int(x.split("_")[1]))
        latest = checkpoints[-1]
        source_path = os.path.join(checkpoint_dir, latest)
    else:
        return t("training.no_trained_model_found", path=lora_output_dir)
    

    # Resolve and validate the export destination within the safe root
    safe_export_path = _safe_join(SAFE_TRAINING_ROOT, export_path)
    if safe_export_path is None:
        return t("training.invalid_export_path")
    

    try:
        import shutil
        
        # Ensure parent directory exists
        parent_dir = os.path.dirname(safe_export_path) or "."
        os.makedirs(parent_dir, exist_ok=True)
        
        if os.path.exists(safe_export_path):
            shutil.rmtree(safe_export_path)
        
        shutil.copytree(source_path, safe_export_path)
        
        return t("training.lora_exported", path=safe_export_path)
        
    except Exception as e:
        logger.exception("Export error")
        return t("training.export_failed", error=str(e))


def start_lokr_training(
    tensor_dir: str,
    dit_handler,
    lokr_linear_dim: int,
    lokr_linear_alpha: int,
    lokr_factor: int,
    lokr_decompose_both: bool,
    lokr_use_tucker: bool,
    lokr_use_scalar: bool,
    lokr_weight_decompose: bool,
    learning_rate: float,
    train_epochs: int,
    train_batch_size: int,
    gradient_accumulation: int,
    save_every_n_epochs: int,
    training_shift: float,
    training_seed: int,
    lokr_output_dir: str,
    training_state: Dict,
    progress=None,
):
    """Start LoKr training from preprocessed tensors."""
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

    if getattr(dit_handler, "quantization", None) is not None:
        yield "Switching model to training preset (disable quantization)...", "", None, training_state
        if hasattr(dit_handler, "switch_to_training_preset"):
            switch_status, switched = dit_handler.switch_to_training_preset()
            if not switched:
                yield f"âŒ {switch_status}", "", None, training_state
                return
            yield f"âœ… {switch_status}", "", None, training_state
        else:
            yield "âŒ Training requires non-quantized DiT, and auto-switch is unavailable in this build.", "", None, training_state
            return

    try:
        from lightning.fabric import Fabric  # noqa: F401
    except ImportError as e:
        yield f"âŒ Missing required packages: {e}\nPlease install: pip install lightning lycoris-lora", "", None, training_state
        return

    training_state["is_training"] = True
    training_state["should_stop"] = False
    training_state["adapter_type"] = "lokr"

    try:
        from acestep.training.configs import LoKRConfig as LoKRConfigClass, TrainingConfig
        from acestep.training.trainer import LoKRTrainer

        device_attr = getattr(dit_handler, "device", "")
        if hasattr(device_attr, "type"):
            device_type = str(device_attr.type).lower()
        else:
            device_type = str(device_attr).split(":", 1)[0].lower()

        if device_type == "cuda":
            num_workers = 4
            pin_memory = True
            prefetch_factor = 2
            persistent_workers = True
            pin_memory_device = "cuda"
            mixed_precision = "bf16"
        elif device_type == "xpu":
            num_workers = 4
            pin_memory = True
            prefetch_factor = 2
            persistent_workers = True
            pin_memory_device = ""
            mixed_precision = "bf16"
        elif device_type == "mps":
            num_workers = 0
            pin_memory = False
            prefetch_factor = 2
            persistent_workers = False
            pin_memory_device = ""
            mixed_precision = "fp16"
        else:
            num_workers = 0
            pin_memory = False
            prefetch_factor = 2
            persistent_workers = False
            pin_memory_device = ""
            mixed_precision = "fp32"

        lokr_config = LoKRConfigClass(
            linear_dim=lokr_linear_dim,
            linear_alpha=lokr_linear_alpha,
            factor=lokr_factor,
            decompose_both=lokr_decompose_both,
            use_tucker=lokr_use_tucker,
            use_scalar=lokr_use_scalar,
            weight_decompose=lokr_weight_decompose,
        )
        training_config = TrainingConfig(
            shift=training_shift,
            learning_rate=learning_rate,
            batch_size=train_batch_size,
            gradient_accumulation_steps=gradient_accumulation,
            max_epochs=train_epochs,
            save_every_n_epochs=save_every_n_epochs,
            seed=training_seed,
            output_dir=lokr_output_dir,
            num_workers=num_workers,
            pin_memory=pin_memory,
            prefetch_factor=prefetch_factor,
            persistent_workers=persistent_workers,
            pin_memory_device=pin_memory_device,
            mixed_precision=mixed_precision,
        )

        log_lines = []
        step_list = []
        loss_list = []
        initial_plot = _training_loss_figure(training_state, step_list, loss_list)
        start_time = time.time()
        yield f"ðŸš€ Starting LoKr training from {tensor_dir}...", "", initial_plot, training_state

        trainer = LoKRTrainer(
            dit_handler=dit_handler,
            lokr_config=lokr_config,
            training_config=training_config,
        )

        training_failed = False
        failure_message = ""

        for step, loss, status in trainer.train_from_preprocessed(tensor_dir, training_state):
            status_text = str(status)
            status_lower = status_text.lower()
            if (
                status_text.startswith("âŒ")
                or "training failed" in status_lower
                or "error:" in status_lower
                or "module not found" in status_lower
            ):
                training_failed = True
                failure_message = status_text

            elapsed_seconds = time.time() - start_time
            time_info = f"â±ï¸ Elapsed: {_format_duration(elapsed_seconds)}"
            match = re.search(r"Epoch\s+(\d+)/(\d+)", status_text)
            if match:
                current_ep = int(match.group(1))
                total_ep = int(match.group(2))
                if current_ep > 0:
                    eta_seconds = (elapsed_seconds / current_ep) * (total_ep - current_ep)
                    time_info += f" | ETA: ~{_format_duration(eta_seconds)}"

            display_status = f"{status_text}\n{time_info}"
            log_lines.append(status_text)
            if len(log_lines) > 15:
                log_lines = log_lines[-15:]
            log_text = "\n".join(log_lines)

            if step > 0 and loss is not None and loss == loss:
                step_list.append(step)
                loss_list.append(float(loss))

            plot_figure = _training_loss_figure(training_state, step_list, loss_list)
            yield display_status, log_text, plot_figure, training_state

            if training_state.get("should_stop", False):
                log_lines.append("â¹ï¸ Training stopped by user")
                yield f"â¹ï¸ Stopped ({time_info})", "\n".join(log_lines[-15:]), plot_figure, training_state
                break

        total_time = time.time() - start_time
        training_state["is_training"] = False
        final_plot = _training_loss_figure(training_state, step_list, loss_list)
        if training_failed:
            final_msg = f"{failure_message}\nElapsed: {_format_duration(total_time)}"
            log_lines.append(failure_message)
            yield final_msg, "\n".join(log_lines[-15:]), final_plot, training_state
            return

        completion_msg = f"âœ… LoKr training completed! Total time: {_format_duration(total_time)}"
        log_lines.append(completion_msg)
        yield completion_msg, "\n".join(log_lines[-15:]), final_plot, training_state

    except Exception as e:
        logger.exception("LoKr training error")
        training_state["is_training"] = False
        yield f"âŒ Error: {str(e)}", str(e), _training_loss_figure({}, [], []), training_state


def list_lokr_export_epochs(lokr_output_dir: str) -> Tuple[Any, str]:
    """List available LoKr checkpoint epochs for export dropdown."""
    default_choice = t("training.latest_auto")
    if not lokr_output_dir or not lokr_output_dir.strip():
        return gr.update(choices=[default_choice], value=default_choice), t("training.lokr_output_dir_required")

    checkpoint_dir = os.path.join(lokr_output_dir.strip(), "checkpoints")
    if not os.path.isdir(checkpoint_dir):
        return gr.update(choices=[default_choice], value=default_choice), t("training.lokr_no_checkpoints_use_latest")

    checkpoints = []
    for d in os.listdir(checkpoint_dir):
        if not d.startswith("epoch_"):
            continue
        weight_file = os.path.join(checkpoint_dir, d, "lokr_weights.safetensors")
        if not os.path.exists(weight_file):
            continue
        try:
            epoch_num = int(d.split("_")[1])
        except Exception:
            continue
        checkpoints.append((epoch_num, d))

    if not checkpoints:
        return gr.update(choices=[default_choice], value=default_choice), t("training.lokr_no_exportable_checkpoints")

    checkpoints.sort(key=lambda x: x[0], reverse=True)
    choices = [default_choice] + [d for _, d in checkpoints]
    return gr.update(choices=choices, value=default_choice), t("training.lokr_found_checkpoints", count=len(checkpoints))


def export_lokr(
    export_path: str,
    lokr_output_dir: str,
    selected_epoch: Optional[str] = None,
) -> str:
    """Export trained LoKr weights.

    Returns:
        Status message
    """
    if not export_path or not export_path.strip():
        return t("training.export_path_required")

    final_dir = os.path.join(lokr_output_dir, "final")
    checkpoint_dir = os.path.join(lokr_output_dir, "checkpoints")
    default_epoch_choice = t("training.latest_auto")

    chosen_epoch = (selected_epoch or "").strip()
    if not chosen_epoch:
        chosen_epoch = default_epoch_choice

    checkpoint_names: List[str] = []
    if os.path.isdir(checkpoint_dir):
        for d in os.listdir(checkpoint_dir):
            if not d.startswith("epoch_"):
                continue
            try:
                int(d.split("_")[1])
            except Exception:
                continue
            checkpoint_names.append(d)
        checkpoint_names.sort(key=lambda x: int(x.split("_")[1]))

    # Determine source
    explicit_epoch = chosen_epoch not in {default_epoch_choice, "latest", "Latest", "auto", "Auto"}
    if explicit_epoch:
        requested = chosen_epoch
        if requested.isdigit():
            requested = f"epoch_{requested}"
        if requested not in checkpoint_names:
            return t("training.lokr_selected_epoch_not_found", chosen=chosen_epoch, available=(", ".join(checkpoint_names) if checkpoint_names else "(none)"))
        source_file = os.path.join(checkpoint_dir, requested, "lokr_weights.safetensors")
        if not os.path.exists(source_file):
            return t("training.lokr_no_weights_selected_epoch", epoch=requested)
    elif os.path.exists(os.path.join(final_dir, "lokr_weights.safetensors")):
        source_file = os.path.join(final_dir, "lokr_weights.safetensors")
    elif checkpoint_names:
        latest_checkpoint = checkpoint_names[-1]
        source_file = os.path.join(checkpoint_dir, latest_checkpoint, "lokr_weights.safetensors")
        if not os.path.exists(source_file):
            return t("training.lokr_no_weights_latest_checkpoint", checkpoint=latest_checkpoint)
    else:
        return t("training.lokr_no_trained_weights_found", path=lokr_output_dir)

    try:
        import shutil

        export_path = export_path.strip()
        if export_path.lower().endswith(".safetensors"):
            os.makedirs(os.path.dirname(export_path) if os.path.dirname(export_path) else ".", exist_ok=True)
            shutil.copy2(source_file, export_path)
            return t("training.lokr_exported", path=export_path)

        os.makedirs(export_path, exist_ok=True)
        dst_file = os.path.join(export_path, "lokr_weights.safetensors")
        shutil.copy2(source_file, dst_file)
        return t("training.lokr_exported", path=dst_file)

    except Exception as e:
        logger.exception("LoKr export error")
        return t("training.export_failed", error=str(e))
