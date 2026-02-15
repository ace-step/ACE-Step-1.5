"""
Generation Input Handlers Module
Contains event handlers and helper functions related to generation inputs
"""
import os
import sys
import json
import random
import glob
import re
import gradio as gr
from typing import Optional, List, Tuple
from loguru import logger
from acestep.constants import (
    TASK_TYPES_TURBO,
    TASK_TYPES_BASE,
    GENERATION_MODES_TURBO,
    GENERATION_MODES_BASE,
    MODE_TO_TASK_TYPE,
)
from acestep.gradio_ui.i18n import t
from acestep.inference import understand_music, create_sample, format_sample
from acestep.gpu_config import (
    get_global_gpu_config, is_lm_model_size_allowed, find_best_lm_model_on_disk,
    get_gpu_config_for_tier, set_global_gpu_config, GPU_TIER_LABELS, GPU_TIER_CONFIGS,
)


def clamp_duration_to_gpu_limit(duration_value: Optional[float], llm_handler=None) -> Optional[float]:
    """
    Clamp duration value to GPU memory limit.
    
    Args:
        duration_value: Duration in seconds (can be None or -1 for no limit)
        llm_handler: LLM handler instance (to check if LM is initialized)
        
    Returns:
        Clamped duration value, or original value if within limits
    """
    if duration_value is None or duration_value <= 0:
        return duration_value
    
    gpu_config = get_global_gpu_config()
    lm_initialized = llm_handler.llm_initialized if llm_handler else False
    max_duration = gpu_config.max_duration_with_lm if lm_initialized else gpu_config.max_duration_without_lm
    
    if duration_value > max_duration:
        return float(max_duration)
    
    return duration_value


def parse_and_validate_timesteps(
    timesteps_str: str,
    inference_steps: int
) -> Tuple[Optional[List[float]], bool, str]:
    """
    Parse timesteps string and validate.
    
    Args:
        timesteps_str: Comma-separated timesteps string (e.g., "0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0")
        inference_steps: Expected number of inference steps
        
    Returns:
        Tuple of (parsed_timesteps, has_warning, warning_message)
        - parsed_timesteps: List of float timesteps, or None if invalid/empty
        - has_warning: Whether a warning was shown
        - warning_message: Description of the warning
    """
    if not timesteps_str or not timesteps_str.strip():
        return None, False, ""
    
    # Parse comma-separated values
    values = [v.strip() for v in timesteps_str.split(",") if v.strip()]
    
    if not values:
        return None, False, ""
    
    # Handle optional trailing 0
    if values[-1] != "0":
        values.append("0")
    
    try:
        timesteps = [float(v) for v in values]
    except ValueError:
        gr.Warning(t("messages.invalid_timesteps_format"))
        return None, True, "Invalid format"
    
    # Validate range [0, 1]
    if any(ts < 0 or ts > 1 for ts in timesteps):
        gr.Warning(t("messages.timesteps_out_of_range"))
        return None, True, "Out of range"
    
    # Check if count matches inference_steps
    actual_steps = len(timesteps) - 1
    if actual_steps != inference_steps:
        gr.Warning(t("messages.timesteps_count_mismatch", actual=actual_steps, expected=inference_steps))
        return timesteps, True, f"Using {actual_steps} steps from timesteps"
    
    return timesteps, False, ""


def load_metadata(file_obj, llm_handler=None):
    """Load generation parameters from a JSON file
    
    Args:
        file_obj: Uploaded file object
        llm_handler: LLM handler instance (optional, for GPU duration limit check)
    """
    if file_obj is None:
        gr.Warning(t("messages.no_file_selected"))
        return [None] * 37 + [False]  # Return None for all 37 fields, False for is_format_caption
    
    try:
        # Read the uploaded file
        if hasattr(file_obj, 'name'):
            filepath = file_obj.name
        else:
            filepath = file_obj
        
        with open(filepath, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Extract all fields
        task_type = metadata.get('task_type', 'text2music')
        captions = metadata.get('caption', '')
        lyrics = metadata.get('lyrics', '')
        vocal_language = metadata.get('vocal_language', 'unknown')
        
        # Convert bpm
        bpm_value = metadata.get('bpm')
        if bpm_value is not None and bpm_value != "N/A":
            try:
                bpm = int(bpm_value) if bpm_value else None
            except:
                bpm = None
        else:
            bpm = None
        
        key_scale = metadata.get('keyscale', '')
        time_signature = metadata.get('timesignature', '')
        
        # Convert duration
        duration_value = metadata.get('duration', -1)
        if duration_value is not None and duration_value != "N/A":
            try:
                audio_duration = float(duration_value)
                # Clamp duration to GPU memory limit
                audio_duration = clamp_duration_to_gpu_limit(audio_duration, llm_handler)
            except:
                audio_duration = -1
        else:
            audio_duration = -1
        
        batch_size = metadata.get('batch_size', 2)
        # Clamp batch_size to GPU memory limit
        gpu_config = get_global_gpu_config()
        lm_initialized = llm_handler.llm_initialized if llm_handler else False
        max_batch_size = gpu_config.max_batch_size_with_lm if lm_initialized else gpu_config.max_batch_size_without_lm
        batch_size = min(int(batch_size), max_batch_size)
        inference_steps = metadata.get('inference_steps', 8)
        guidance_scale = metadata.get('guidance_scale', 7.0)
        seed = metadata.get('seed', '-1')
        random_seed = False  # Always set to False when loading to enable reproducibility with saved seed
        use_adg = metadata.get('use_adg', False)
        cfg_interval_start = metadata.get('cfg_interval_start', 0.0)
        cfg_interval_end = metadata.get('cfg_interval_end', 1.0)
        audio_format = metadata.get('audio_format', 'flac')
        lm_temperature = metadata.get('lm_temperature', 0.85)
        lm_cfg_scale = metadata.get('lm_cfg_scale', 2.0)
        lm_top_k = metadata.get('lm_top_k', 0)
        lm_top_p = metadata.get('lm_top_p', 0.9)
        lm_negative_prompt = metadata.get('lm_negative_prompt', 'NO USER INPUT')
        use_cot_metas = metadata.get('use_cot_metas', True)  # Added: read use_cot_metas
        use_cot_caption = metadata.get('use_cot_caption', True)
        use_cot_language = metadata.get('use_cot_language', True)
        audio_cover_strength = metadata.get('audio_cover_strength', 1.0)
        cover_noise_strength = metadata.get('cover_noise_strength', 0.0)
        think = metadata.get('thinking', True)  # Fixed: read 'thinking' not 'think'
        # If LM not initialized, force think to False and warn
        lm_ok = llm_handler.llm_initialized if llm_handler else False
        if think and not lm_ok:
            think = False
            gr.Warning(t("messages.think_requires_lm"))
        audio_codes = metadata.get('audio_codes', '')
        # When JSON has LM-generated audio codes AND thinking was True,
        # set think=False so the loaded codes are used directly for
        # reproducibility instead of being discarded by a fresh LM pass.
        if think and audio_codes and audio_codes.strip():
            think = False
        repainting_start = metadata.get('repainting_start', 0.0)
        repainting_end = metadata.get('repainting_end', -1)
        track_name = metadata.get('track_name')
        complete_track_classes = metadata.get('complete_track_classes', [])
        shift = metadata.get('shift', 3.0)  # Default 3.0 for base models
        infer_method = metadata.get('infer_method', 'ode')  # Default 'ode' for diffusion inference
        custom_timesteps = metadata.get('timesteps', '')  # Custom timesteps (stored as 'timesteps' in JSON)
        if custom_timesteps is None:
            custom_timesteps = ''
        instrumental = metadata.get('instrumental', False)  # Added: read instrumental
        
        gr.Info(t("messages.params_loaded", filename=os.path.basename(filepath)))
        
        return (
            task_type, captions, lyrics, vocal_language, bpm, key_scale, time_signature,
            audio_duration, batch_size, inference_steps, guidance_scale, seed, random_seed,
            use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method,
            custom_timesteps,  # Added: custom_timesteps (between infer_method and audio_format)
            audio_format, lm_temperature, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
            use_cot_metas, use_cot_caption, use_cot_language, audio_cover_strength,
            cover_noise_strength, think, audio_codes, repainting_start, repainting_end,
            track_name, complete_track_classes, instrumental,
            True  # Set is_format_caption to True when loading from file
        )
        
    except json.JSONDecodeError as e:
        gr.Warning(t("messages.invalid_json", error=str(e)))
        return [None] * 37 + [False]
    except Exception as e:
        gr.Warning(t("messages.load_error", error=str(e)))
        return [None] * 37 + [False]


def load_random_example(task_type: str, llm_handler=None):
    """Load a random example from the task-specific examples directory
    
    Args:
        task_type: The task type (e.g., "text2music")
        llm_handler: LLM handler instance (optional, for GPU duration limit check)
        
    Returns:
        Tuple of (caption, lyrics, think, bpm, duration, keyscale, language, timesignature) for updating UI components
    """
    try:
        # Get the project root directory
        current_file = os.path.abspath(__file__)
        # This file is in acestep/gradio_ui/events/, need 4 levels up to reach project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
        
        # Construct the examples directory path
        examples_dir = os.path.join(project_root, "examples", task_type)
        
        # Check if directory exists
        if not os.path.exists(examples_dir):
            gr.Warning(f"Examples directory not found: examples/{task_type}/")
            return "", "", True, None, None, "", "", ""
        
        # Find all JSON files in the directory
        json_files = glob.glob(os.path.join(examples_dir, "*.json"))
        
        if not json_files:
            gr.Warning(f"No JSON files found in examples/{task_type}/")
            return "", "", True, None, None, "", "", ""
        
        # Randomly select one file
        selected_file = random.choice(json_files)
        
        # Read and parse JSON
        try:
            with open(selected_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract caption (prefer 'caption', fallback to 'prompt')
            caption_value = data.get('caption', data.get('prompt', ''))
            if not isinstance(caption_value, str):
                caption_value = str(caption_value) if caption_value else ''
            
            # Extract lyrics
            lyrics_value = data.get('lyrics', '')
            if not isinstance(lyrics_value, str):
                lyrics_value = str(lyrics_value) if lyrics_value else ''
            
            # Extract think (default to True if not present)
            think_value = data.get('think', True)
            if not isinstance(think_value, bool):
                think_value = True
            # If LM not initialized, force think to False and warn
            lm_ok = llm_handler.llm_initialized if llm_handler else False
            if think_value and not lm_ok:
                think_value = False
                gr.Warning(t("messages.think_requires_lm"))
            
            # Extract optional metadata fields
            bpm_value = None
            if 'bpm' in data and data['bpm'] not in [None, "N/A", ""]:
                try:
                    bpm_value = int(data['bpm'])
                except (ValueError, TypeError):
                    pass
            
            duration_value = None
            if 'duration' in data and data['duration'] not in [None, "N/A", ""]:
                try:
                    duration_value = float(data['duration'])
                    # Clamp duration to GPU memory limit
                    duration_value = clamp_duration_to_gpu_limit(duration_value, llm_handler)
                except (ValueError, TypeError):
                    pass
            
            keyscale_value = data.get('keyscale', '')
            if keyscale_value in [None, "N/A"]:
                keyscale_value = ''
            
            language_value = data.get('language', '')
            if language_value in [None, "N/A"]:
                language_value = ''
            
            timesignature_value = data.get('timesignature', '')
            if timesignature_value in [None, "N/A"]:
                timesignature_value = ''
            
            gr.Info(t("messages.example_loaded", filename=os.path.basename(selected_file)))
            return caption_value, lyrics_value, think_value, bpm_value, duration_value, keyscale_value, language_value, timesignature_value
            
        except json.JSONDecodeError as e:
            gr.Warning(t("messages.example_failed", filename=os.path.basename(selected_file), error=str(e)))
            return "", "", True, None, None, "", "", ""
        except Exception as e:
            gr.Warning(t("messages.example_error", error=str(e)))
            return "", "", True, None, None, "", "", ""
            
    except Exception as e:
        gr.Warning(t("messages.example_error", error=str(e)))
        return "", "", True, None, None, "", "", ""


def sample_example_smart(llm_handler, task_type: str, constrained_decoding_debug: bool = False):
    """Smart sample function that uses LM if initialized, otherwise falls back to examples
    
    This is a Gradio wrapper that uses the understand_music API from acestep.inference
    to generate examples when LM is available.
    
    Args:
        llm_handler: LLM handler instance
        task_type: The task type (e.g., "text2music")
        constrained_decoding_debug: Whether to enable debug logging for constrained decoding
        
    Returns:
        Tuple of (caption, lyrics, think, bpm, duration, keyscale, language, timesignature) for updating UI components
    """
    # Check if LM is initialized
    if llm_handler.llm_initialized:
        # Use LM to generate example via understand_music API
        try:
            result = understand_music(
                llm_handler=llm_handler,
                audio_codes="NO USER INPUT",  # Empty input triggers example generation
                temperature=0.85,
                use_constrained_decoding=True,
                constrained_decoding_debug=constrained_decoding_debug,
            )
            
            if result.success:
                gr.Info(t("messages.lm_generated"))
                # Clamp duration to GPU memory limit
                clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
                return (
                    result.caption,
                    result.lyrics,
                    True,  # Always enable think when using LM-generated examples
                    result.bpm,
                    clamped_duration,
                    result.keyscale,
                    result.language,
                    result.timesignature,
                )
            else:
                gr.Warning(t("messages.lm_fallback"))
                return load_random_example(task_type)
                
        except Exception as e:
            gr.Warning(t("messages.lm_fallback"))
            return load_random_example(task_type)
    else:
        # LM not initialized, use examples directory
        return load_random_example(task_type)


def load_random_simple_description():
    """Load a random description from the simple_mode examples directory.

    Returns:
        Tuple of (description, instrumental, vocal_language) for updating UI components
    """
    try:
        # Get the project root directory
        current_file = os.path.abspath(__file__)
        # This file is in acestep/gradio_ui/events/, need 4 levels up to reach project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))

        # Construct the examples directory path
        examples_dir = os.path.join(project_root, "examples", "simple_mode")

        # Check if directory exists
        if not os.path.exists(examples_dir):
            gr.Warning(t("messages.simple_examples_not_found"))
            return gr.update(), gr.update(), gr.update()

        # Find all JSON files in the directory
        json_files = glob.glob(os.path.join(examples_dir, "*.json"))

        if not json_files:
            gr.Warning(t("messages.simple_examples_empty"))
            return gr.update(), gr.update(), gr.update()

        # Randomly select one file
        selected_file = random.choice(json_files)

        # Read and parse JSON
        try:
            with open(selected_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract fields
            description = data.get('description', '')
            instrumental = data.get('instrumental', False)
            vocal_language = data.get('vocal_language', 'unknown')

            # Ensure vocal_language is a string
            if isinstance(vocal_language, list):
                vocal_language = vocal_language[0] if vocal_language else 'unknown'

            gr.Info(t("messages.simple_example_loaded", filename=os.path.basename(selected_file)))
            return description, instrumental, vocal_language
            
        except json.JSONDecodeError as e:
            gr.Warning(t("messages.example_failed", filename=os.path.basename(selected_file), error=str(e)))
            return gr.update(), gr.update(), gr.update()
        except Exception as e:
            gr.Warning(t("messages.example_error", error=str(e)))
            return gr.update(), gr.update(), gr.update()
            
    except Exception as e:
        gr.Warning(t("messages.example_error", error=str(e)))
        return gr.update(), gr.update(), gr.update()


def refresh_checkpoints(dit_handler):
    """Refresh available checkpoints"""
    choices = dit_handler.get_available_checkpoints()
    return gr.update(choices=choices)


def _is_pure_base_model(config_path_lower: str) -> bool:
    """Check if a model path refers to a pure base model (not SFT or turbo).
    
    Only pure base models support extended tasks (Extract, Lego, Complete).
    SFT and turbo models only support Simple, Custom, Remix, Repaint.
    
    Examples:
        "acestep-v15-base" → True (pure base)
        "acestep-v15-base-sft-fix-inst" → False (SFT variant)
        "acestep-v15-sft" → False (SFT)
        "acestep-v15-turbo" → False (turbo)
    """
    return "base" in config_path_lower and "sft" not in config_path_lower and "turbo" not in config_path_lower


def update_model_type_settings(config_path, current_mode=None):
    """Update UI settings based on model type (fallback when handler not initialized yet).
    
    Args:
        config_path: Model config path string (used to determine turbo vs base).
        current_mode: Current generation mode value to preserve across choices update.
    
    Note: This is used as a fallback when the user changes config_path dropdown 
    before initializing the model. The actual settings are determined by the 
    handler's is_turbo_model() method after initialization.
    """
    if config_path is None:
        config_path = ""
    config_path_lower = config_path.lower()
    
    # Determine model category from config_path string.
    # is_turbo controls inference-step defaults (turbo = few steps, base/sft = many steps).
    # is_pure_base controls extended task availability (Extract/Lego/Complete).
    if "turbo" in config_path_lower:
        is_turbo = True
    else:
        is_turbo = False
    is_pure_base = _is_pure_base_model(config_path_lower)
    
    return get_model_type_ui_settings(is_turbo, current_mode=current_mode, is_pure_base=is_pure_base)


def init_service_wrapper(dit_handler, llm_handler, checkpoint, config_path, device, init_llm, lm_model_path, backend, use_flash_attention, offload_to_cpu, offload_dit_to_cpu, compile_model, quantization, mlx_dit=True, current_mode=None, current_batch_size=None):
    """Wrapper for service initialization, returns status, button state, accordion state, model type settings, and GPU-config-aware UI limits.
    
    Args:
        current_batch_size: Current batch size value from UI to preserve after reinitialization (optional)
    """
    # Convert quantization checkbox to value (int8_weight_only if checked, None if not)
    quant_value = "int8_weight_only" if quantization else None
    
    # --- Tier-aware validation before initialization ---
    gpu_config = get_global_gpu_config()
    
    # macOS safety: quantization (torchao) is unsupported on MPS.
    # Compilation is allowed — the handler redirects it to mx.compile for
    # MLX components instead of torch.compile.
    if sys.platform == "darwin":
        if compile_model:
            logger.info(
                "macOS detected: torch.compile not supported; compilation "
                "will use mx.compile via MLX."
            )
        if quantization:
            logger.info("macOS detected: disabling INT8 quantization (torchao incompatible with MPS)")
            quantization = False
            quant_value = None
    
    # Validate LM request against GPU tier
    if init_llm and not gpu_config.available_lm_models:
        logger.warning(
            f"⚠️ GPU tier {gpu_config.tier} ({gpu_config.gpu_memory_gb:.1f}GB) does not support LM on GPU. "
            "Falling back to CPU for LM initialization."
        )
        llm_handler.device = "cpu"
    else:
        llm_handler.device = device
    
    # Warn (but respect) if the selected LM model exceeds the tier's recommendation
    if init_llm and lm_model_path and gpu_config.available_lm_models:
        if not is_lm_model_size_allowed(lm_model_path, gpu_config.available_lm_models):
            logger.warning(
                f"⚠️ LM model {lm_model_path} is not in the recommended list for tier {gpu_config.tier} "
                f"(recommended: {gpu_config.available_lm_models}). Proceeding with user selection — "
                f"this may cause high VRAM usage or OOM."
            )
    
    # Validate backend against tier restriction
    if init_llm and gpu_config.lm_backend_restriction == "pt_mlx_only" and backend == "vllm":
        backend = gpu_config.recommended_backend  # Fallback to pt
        logger.warning(f"⚠️ vllm backend not supported for tier {gpu_config.tier} (VRAM too low for KV cache), falling back to {backend}")
    
    # Initialize DiT handler
    status, enable = dit_handler.initialize_service(
        checkpoint, config_path, device,
        use_flash_attention=use_flash_attention, compile_model=compile_model, 
        offload_to_cpu=offload_to_cpu, offload_dit_to_cpu=offload_dit_to_cpu,
        quantization=quant_value, use_mlx_dit=mlx_dit,
    )
    
    # Initialize LM handler if requested
    if init_llm:
        # Get checkpoint directory
        current_file = os.path.abspath(__file__)
        # This file is in acestep/gradio_ui/events/, need 4 levels up to reach project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
        checkpoint_dir = os.path.join(project_root, "checkpoints")
        
        lm_status, lm_success = llm_handler.initialize(
            checkpoint_dir=checkpoint_dir,
            lm_model_path=lm_model_path,
            backend=backend,
            device=llm_handler.device,
            offload_to_cpu=offload_to_cpu,
            dtype=None,
        )
        
        if lm_success:
            status += f"\n{lm_status}"
        else:
            status += f"\n{lm_status}"
            # Don't fail the entire initialization if LM fails, but log it
            # Keep enable as is (DiT initialization result) even if LM fails
    
    # Check if model is initialized - if so, collapse the accordion
    is_model_initialized = dit_handler.model is not None
    accordion_state = gr.Accordion(open=not is_model_initialized)
    
    # Get model type settings based on actual loaded model and config_path
    is_turbo = dit_handler.is_turbo_model()
    is_pure_base = _is_pure_base_model((config_path or "").lower())
    model_type_settings = get_model_type_ui_settings(is_turbo, current_mode=current_mode, is_pure_base=is_pure_base)
    
    # --- Update UI limits based on GPU config and actual LM state ---
    gpu_config = get_global_gpu_config()
    lm_actually_initialized = llm_handler.llm_initialized if llm_handler else False
    max_duration = gpu_config.max_duration_with_lm if lm_actually_initialized else gpu_config.max_duration_without_lm
    max_batch = gpu_config.max_batch_size_with_lm if lm_actually_initialized else gpu_config.max_batch_size_without_lm
    
    duration_update = gr.update(
        maximum=float(max_duration),
        info=f"Duration in seconds (-1 for auto). Max: {max_duration}s / {max_duration // 60} min.",
        elem_classes=["has-info-container"],
    )
    
    # Preserve current batch size if provided, otherwise use default of min(2, max_batch)
    # Convert to int first and validate it's at least 1, then clamp to max.
    # Note: Values exceeding max_batch are intentionally clamped rather than rejected,
    # allowing users to set a high value that works across different GPU configurations.
    if current_batch_size is not None:
        try:
            batch_value_int = int(current_batch_size)
            if batch_value_int >= 1:
                batch_value = min(batch_value_int, max_batch)
                if batch_value_int > max_batch:
                    logger.warning(f"Batch size {batch_value_int} exceeds GPU limit {max_batch}, clamping to {batch_value}")
            else:
                logger.warning(f"Invalid batch size {batch_value_int} (must be >= 1), using default {min(2, max_batch)}")
                batch_value = min(2, max_batch)
        except ValueError:
            logger.warning(f"Cannot convert batch size '{current_batch_size}' to integer, using default {min(2, max_batch)}")
            batch_value = min(2, max_batch)
        except TypeError:
            logger.warning(f"Invalid batch size type {type(current_batch_size).__name__}, using default {min(2, max_batch)}")
            batch_value = min(2, max_batch)
    else:
        batch_value = min(2, max_batch)
    
    batch_update = gr.update(
        value=batch_value,
        maximum=max_batch,
        info=f"Number of samples to generate (Max: {max_batch}).",
        elem_classes=["has-info-container"],
    )
    
    # Add GPU config info to status
    status += f"\n📊 GPU Config: tier={gpu_config.tier}, max_duration={max_duration}s, max_batch={max_batch}"
    if gpu_config.available_lm_models:
        status += f", available_lm={gpu_config.available_lm_models}"
    else:
        status += ", LM not available for this GPU tier"
    
    # Think checkbox: interactive and checked only when LLM is initialized
    think_interactive = lm_actually_initialized
    
    return (
        status, 
        gr.update(interactive=enable), 
        accordion_state,
        *model_type_settings,
        # GPU-config-aware UI updates
        duration_update,
        batch_update,
        # Think checkbox
        gr.update(interactive=think_interactive, value=think_interactive),
    )


def on_tier_change(selected_tier, llm_handler=None):
    """
    Handle manual tier override from the UI dropdown.
    
    Updates the global GPU config and returns gr.update() for all
    affected UI components so they reflect the new tier's defaults.
    
    Returns a tuple of gr.update() objects for:
        (offload_to_cpu, offload_dit_to_cpu, compile_model, quantization,
         backend_dropdown, lm_model_path, init_llm, batch_size_input,
         audio_duration, gpu_info_display)
    """
    if not selected_tier or selected_tier not in GPU_TIER_CONFIGS:
        logger.warning(f"Invalid tier selection: {selected_tier}")
        return (gr.update(),) * 10
    
    # Build new config for the selected tier and update global
    new_config = get_gpu_config_for_tier(selected_tier)
    set_global_gpu_config(new_config)
    logger.info(f"🔄 Tier manually changed to {selected_tier} — updating UI defaults")
    
    # Backend choices
    if new_config.lm_backend_restriction == "pt_mlx_only":
        available_backends = ["pt", "mlx"]
    else:
        available_backends = ["vllm", "pt", "mlx"]
    recommended_backend = new_config.recommended_backend
    if recommended_backend not in available_backends:
        recommended_backend = available_backends[0]
    
    # LM model choices — show all disk models (no filtering by tier);
    # tier only influences the default/recommended selection.
    all_disk_models = llm_handler.get_available_5hz_lm_models() if llm_handler else []
    
    recommended_lm = new_config.recommended_lm_model
    default_lm_model = find_best_lm_model_on_disk(recommended_lm, all_disk_models)
    
    # Duration and batch limits (use without-LM limits as safe default; init will refine)
    max_duration = new_config.max_duration_without_lm
    max_batch = new_config.max_batch_size_without_lm
    
    # GPU info markdown update
    tier_label = GPU_TIER_LABELS.get(selected_tier, selected_tier)
    from acestep.gpu_config import get_gpu_device_name
    _gpu_device_name = get_gpu_device_name()
    gpu_info_text = f"🖥️ **{_gpu_device_name}** — {new_config.gpu_memory_gb:.1f} GB VRAM — {t('service.gpu_auto_tier')}: **{tier_label}**"
    
    return (
        # offload_to_cpu_checkbox
        gr.update(value=new_config.offload_to_cpu_default,
                  info=t("service.offload_cpu_info") + (" (recommended for this tier)" if new_config.offload_to_cpu_default else ""),
                  elem_classes=["has-info-container"]),
        # offload_dit_to_cpu_checkbox
        gr.update(value=new_config.offload_dit_to_cpu_default,
                  info=t("service.offload_dit_cpu_info") + (" (recommended for this tier)" if new_config.offload_dit_to_cpu_default else ""),
                  elem_classes=["has-info-container"]),
        # compile_model_checkbox
        gr.update(value=new_config.compile_model_default),
        # quantization_checkbox
        gr.update(value=new_config.quantization_default,
                  info=t("service.quantization_info") + (" (recommended for this tier)" if new_config.quantization_default else ""),
                  elem_classes=["has-info-container"]),
        # backend_dropdown
        gr.update(choices=available_backends, value=recommended_backend, elem_classes=["has-info-container"]),
        # lm_model_path
        gr.update(choices=all_disk_models, value=default_lm_model,
                  info=t("service.lm_model_path_info") + (f" (Recommended: {recommended_lm})" if recommended_lm else " (LM not available for this GPU tier)."),
                  elem_classes=["has-info-container"]),
        # init_llm_checkbox
        gr.update(value=new_config.init_lm_default, elem_classes=["has-info-container"]),
        # batch_size_input
        gr.update(value=min(2, max_batch), maximum=max_batch,
                  info=f"Number of samples to generate (Max: {max_batch}).",
                  elem_classes=["has-info-container"]),
        # audio_duration
        gr.update(maximum=float(max_duration),
                  info=f"Duration in seconds (-1 for auto). Max: {max_duration}s / {max_duration // 60} min.",
                  elem_classes=["has-info-container"]),
        # gpu_info_display
        gr.update(value=gpu_info_text),
    )


def get_ui_control_config(is_turbo: bool, is_pure_base: bool = False) -> dict:
    """Return UI control configuration (values, limits, visibility) for model type.
    
    Args:
        is_turbo: Whether the model is a turbo variant (affects inference steps, guidance, etc.).
        is_pure_base: Whether the model is a pure base model (not SFT, not turbo).
            Only pure base models support extended tasks (Extract, Lego, Complete).
            SFT models use the same restricted task/mode set as turbo.
    
    Used by both interactive init and service-mode startup so controls stay consistent.
    """
    # Extended modes (Extract/Lego/Complete) only for pure base models
    if is_pure_base:
        task_choices = TASK_TYPES_BASE
        mode_choices = GENERATION_MODES_BASE
    else:
        task_choices = TASK_TYPES_TURBO
        mode_choices = GENERATION_MODES_TURBO

    if is_turbo:
        return {
            "inference_steps_value": 8,
            "inference_steps_maximum": 20,
            "inference_steps_minimum": 1,
            "guidance_scale_visible": False,
            "use_adg_visible": False,
            "shift_value": 3.0,
            "shift_visible": True,
            "cfg_interval_start_visible": False,
            "cfg_interval_end_visible": False,
            "task_type_choices": task_choices,
            "generation_mode_choices": mode_choices,
        }
    else:
        return {
            "inference_steps_value": 32,
            "inference_steps_maximum": 200,
            "inference_steps_minimum": 1,
            "guidance_scale_visible": True,
            "use_adg_visible": True,
            "shift_value": 3.0,
            "shift_visible": True,
            "cfg_interval_start_visible": True,
            "cfg_interval_end_visible": True,
            "task_type_choices": task_choices,
            "generation_mode_choices": mode_choices,
        }


def get_model_type_ui_settings(is_turbo: bool, current_mode: str = None, is_pure_base: bool = False):
    """Get gr.update() tuple for model-type controls (used by init button / config_path change).
    
    Args:
        is_turbo: Whether the model is a turbo variant.
        current_mode: Current generation mode value to preserve when updating choices.
            Prevents Gradio from resetting the Radio value (and triggering unwanted
            .change events that hide mode-dependent sliders).
        is_pure_base: Whether the model is a pure base model (not SFT, not turbo).
            Only pure base models get extended modes (Extract, Lego, Complete).
    
    Returns tuple of updates for:
    - inference_steps
    - guidance_scale
    - use_adg
    - shift
    - cfg_interval_start
    - cfg_interval_end
    - task_type (hidden, keep value)
    - generation_mode (update choices, preserve current value)
    - init_llm_checkbox (unchecked for pure base models)
    """
    cfg = get_ui_control_config(is_turbo, is_pure_base=is_pure_base)
    new_choices = cfg["generation_mode_choices"]
    # Preserve current mode if it exists in the new choices; otherwise let Gradio pick default
    if current_mode and current_mode in new_choices:
        mode_update = gr.update(choices=new_choices, value=current_mode)
    else:
        mode_update = gr.update(choices=new_choices)
    # Pure base models default to LM not initialized (base extract/lego/complete
    # workflows don't need LM).  Non-base models keep the checkbox unchanged.
    init_llm_update = gr.update(value=False) if is_pure_base else gr.update()
    return (
        gr.update(
            value=cfg["inference_steps_value"],
            maximum=cfg["inference_steps_maximum"],
            minimum=cfg["inference_steps_minimum"],
        ),
        gr.update(visible=cfg["guidance_scale_visible"]),
        gr.update(visible=cfg["use_adg_visible"]),
        gr.update(value=cfg["shift_value"], visible=cfg["shift_visible"]),
        gr.update(visible=cfg["cfg_interval_start_visible"]),
        gr.update(visible=cfg["cfg_interval_end_visible"]),
        gr.update(),  # task_type - no change (hidden, managed by mode)
        mode_update,  # generation_mode choices (with preserved value)
        init_llm_update,  # init_llm_checkbox (unchecked for pure base)
    )


def update_negative_prompt_visibility(init_llm_checked):
    """Update negative prompt visibility: show if Initialize 5Hz LM checkbox is checked"""
    return gr.update(visible=init_llm_checked)


# ============================================================================
# Auto Checkbox Handlers
# ============================================================================

# Default "auto" values per field — these cause the model to auto-infer.
_AUTO_DEFAULTS = {
    "bpm": None,
    "key_scale": "",
    "time_signature": "",
    "vocal_language": "unknown",
    "audio_duration": -1,
}


def on_auto_checkbox_change(auto_checked: bool, field_name: str):
    """Toggle a field between auto (non-interactive, reset to default) and manual.

    Args:
        auto_checked: Whether the Auto checkbox is now checked.
        field_name: One of the keys in _AUTO_DEFAULTS.

    Returns:
        gr.update for the corresponding input component.
    """
    if auto_checked:
        return gr.update(value=_AUTO_DEFAULTS[field_name], interactive=False)
    return gr.update(interactive=True)


def reset_all_auto():
    """Reset all optional-parameter Auto checkboxes to checked.

    Returns:
        Tuple of 10 gr.update objects:
        (bpm_auto, key_auto, timesig_auto, vocal_lang_auto, duration_auto,
         bpm, key_scale, time_signature, vocal_language, audio_duration)
    """
    return (
        gr.update(value=True),   # bpm_auto
        gr.update(value=True),   # key_auto
        gr.update(value=True),   # timesig_auto
        gr.update(value=True),   # vocal_lang_auto
        gr.update(value=True),   # duration_auto
        gr.update(value=_AUTO_DEFAULTS["bpm"], interactive=False),
        gr.update(value=_AUTO_DEFAULTS["key_scale"], interactive=False),
        gr.update(value=_AUTO_DEFAULTS["time_signature"], interactive=False),
        gr.update(value=_AUTO_DEFAULTS["vocal_language"], interactive=False),
        gr.update(value=_AUTO_DEFAULTS["audio_duration"], interactive=False),
    )


def uncheck_auto_for_populated_fields(bpm, key_scale, time_signature, vocal_language, audio_duration):
    """Uncheck Auto checkboxes for fields that were populated by external events.

    Called after sample/analyze/transcribe/load/create_sample/format events
    to make the input fields editable when they have non-default values.

    Args:
        bpm: Current BPM value.
        key_scale: Current key scale value.
        time_signature: Current time signature value.
        vocal_language: Current vocal language value.
        audio_duration: Current audio duration value.

    Returns:
        Tuple of 10 gr.update objects:
        (bpm_auto, key_auto, timesig_auto, vocal_lang_auto, duration_auto,
         bpm_interactive, key_interactive, timesig_interactive,
         vocal_lang_interactive, duration_interactive)
    """
    bpm_has_value = bpm is not None and bpm != _AUTO_DEFAULTS["bpm"]
    key_has_value = bool(key_scale and key_scale != _AUTO_DEFAULTS["key_scale"])
    ts_has_value = bool(time_signature and time_signature != _AUTO_DEFAULTS["time_signature"])
    vl_has_value = vocal_language not in (None, "", _AUTO_DEFAULTS["vocal_language"])
    dur_has_value = (audio_duration is not None
                     and audio_duration != _AUTO_DEFAULTS["audio_duration"]
                     and audio_duration > 0)

    return (
        gr.update(value=not bpm_has_value),        # bpm_auto
        gr.update(value=not key_has_value),         # key_auto
        gr.update(value=not ts_has_value),          # timesig_auto
        gr.update(value=not vl_has_value),          # vocal_lang_auto
        gr.update(value=not dur_has_value),         # duration_auto
        gr.update(interactive=bpm_has_value),       # bpm
        gr.update(interactive=key_has_value),       # key_scale
        gr.update(interactive=ts_has_value),        # time_signature
        gr.update(interactive=vl_has_value),        # vocal_language
        gr.update(interactive=dur_has_value),       # audio_duration
    )


def _has_reference_audio(reference_audio) -> bool:
    """True if reference_audio has a usable value (Gradio Audio returns path string or (path, sr))."""
    if reference_audio is None:
        return False
    if isinstance(reference_audio, str):
        return bool(reference_audio.strip())
    if isinstance(reference_audio, (list, tuple)) and reference_audio:
        return bool(reference_audio[0])
    return False


def update_audio_cover_strength_visibility(task_type_value, init_llm_checked, reference_audio=None):
    """Update audio_cover_strength visibility and label. Show Similarity/Denoise when reference audio is present."""
    has_reference = _has_reference_audio(reference_audio)
    # Show if task is cover, LM is initialized, or reference audio is present (audio-conditioned generation)
    is_visible = (task_type_value == "cover") or init_llm_checked or has_reference
    # Label priority: cover -> LM codes -> Similarity/Denoise (reference audio)
    if task_type_value == "cover":
        label = t("generation.cover_strength_label")
        help_text = t("generation.cover_strength_info")
    elif init_llm_checked:
        label = t("generation.codes_strength_label")
        help_text = t("generation.codes_strength_info")
    elif has_reference:
        label = t("generation.similarity_denoise_label")
        help_text = t("generation.similarity_denoise_info")
    else:
        label = t("generation.cover_strength_label")
        help_text = t("generation.cover_strength_info")
    return gr.update(visible=is_visible, label=label, info=help_text, elem_classes=["has-info-container"])


def convert_src_audio_to_codes_wrapper(dit_handler, src_audio):
    """Wrapper for converting src audio to codes"""
    codes_string = dit_handler.convert_src_audio_to_codes(src_audio)
    return codes_string


def _contains_audio_code_tokens(codes_string: str) -> bool:
    """Return True when a string contains at least one serialized audio-code token."""
    if not isinstance(codes_string, str):
        return False
    return bool(re.search(r"<\|audio_code_\d+\|>", codes_string))


def analyze_src_audio(dit_handler, llm_handler, src_audio, constrained_decoding_debug=False):
    """Analyze source audio: convert to codes, then transcribe to caption/lyrics/metas.

    This is the combined "Analyze" action for Remix/Repaint modes.

    Args:
        dit_handler: DiT handler instance
        llm_handler: LLM handler instance
        src_audio: Path to source audio file
        constrained_decoding_debug: Whether to enable debug logging

    Returns:
        Tuple of (audio_codes, status, caption, lyrics, bpm, duration, keyscale, language, timesignature, is_format_caption)
    """
    # 10-item error tuple: (codes, status, caption, lyrics, bpm, duration, key, lang, timesig, is_format)
    def _err(status: str):
        return ("", status, "", "", None, None, "", "", "", False)

    # Step 1: Convert audio to codes
    if not src_audio:
        status = "No audio file provided."
        gr.Warning(status)
        return _err(status)

    try:
        codes_string = dit_handler.convert_src_audio_to_codes(src_audio)
    except Exception as e:
        status = f"Failed to convert audio to codes: {e}"
        gr.Warning(status)
        return _err(status)

    if not codes_string or not codes_string.strip():
        status = "Audio conversion produced empty codes."
        gr.Warning(status)
        return _err(status)

    if not _contains_audio_code_tokens(codes_string):
        status = "Source file is not valid audio or conversion failed (no audio codes detected)."
        gr.Warning(status)
        return _err(status)

    # Step 2: Transcribe codes to caption/lyrics/metas via LLM
    if not llm_handler.llm_initialized:
        # Return codes but skip transcription
        gr.Warning(t("messages.lm_not_initialized"))
        return (codes_string, t("messages.lm_not_initialized"), "", "", None, None, "", "", "", False)

    result = understand_music(
        llm_handler=llm_handler,
        audio_codes=codes_string,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        if result.error == "LLM not initialized":
            return (codes_string, t("messages.lm_not_initialized"), "", "", None, None, "", "", "", False)
        return (codes_string, result.status_message, "", "", None, None, "", "", "", False)

    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)

    return (
        codes_string,           # text2music_audio_code_string
        result.status_message,  # status_output
        result.caption,         # captions
        result.lyrics,          # lyrics
        result.bpm,             # bpm
        clamped_duration,       # audio_duration
        result.keyscale,        # key_scale
        result.language,        # vocal_language
        result.timesignature,   # time_signature
        True,                   # is_format_caption
    )


def update_instruction_ui(
    dit_handler,
    task_type_value: str, 
    track_name_value: Optional[str], 
    complete_track_classes_value: list, 
    init_llm_checked: bool = False,
    reference_audio=None,
) -> tuple:
    """Update instruction text based on task type.
    
    Visibility of track_name, complete_track_classes, and repainting_group
    is managed by compute_mode_ui_updates (via generation_mode.change).
    This function only regenerates the instruction string.

    Note: init_llm_checked and reference_audio are kept for backward
    compatibility but are no longer used.
    """
    instruction = dit_handler.generate_instruction(
        task_type=task_type_value,
        track_name=track_name_value,
        complete_track_classes=complete_track_classes_value
    )
    
    return instruction  # instruction_display_gen


def transcribe_audio_codes(llm_handler, audio_code_string, constrained_decoding_debug):
    """
    Transcribe audio codes to metadata using LLM understanding.
    If audio_code_string is empty, generate a sample example instead.
    
    This is a Gradio wrapper around the understand_music API in acestep.inference.
    
    Args:
        llm_handler: LLM handler instance
        audio_code_string: String containing audio codes (or empty for example generation)
        constrained_decoding_debug: Whether to enable debug logging for constrained decoding
        
    Returns:
        Tuple of (status_message, caption, lyrics, bpm, duration, keyscale, language, timesignature, is_format_caption)
    """
    # Call the inference API
    result = understand_music(
        llm_handler=llm_handler,
        audio_codes=audio_code_string,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )
    
    # Handle error case with localized message
    if not result.success:
        # Use localized error message for LLM not initialized
        if result.error == "LLM not initialized":
            return t("messages.lm_not_initialized"), "", "", None, None, "", "", "", False
        return result.status_message, "", "", None, None, "", "", "", False
    
    # Clamp duration to GPU memory limit
    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    
    return (
        result.status_message,
        result.caption,
        result.lyrics,
        result.bpm,
        clamped_duration,
        result.keyscale,
        result.language,
        result.timesignature,
        True  # Set is_format_caption to True (from Transcribe/LM understanding)
    )


def update_transcribe_button_text(audio_code_string):
    """
    Update the transcribe button text based on input content.
    If empty: "Generate Example"
    If has content: "Transcribe"
    """
    if not audio_code_string or not audio_code_string.strip():
        return gr.update(value="Generate Example")
    else:
        return gr.update(value="Transcribe")


def reset_format_caption_flag():
    """Reset is_format_caption to False when user manually edits caption/metadata"""
    return False


def update_audio_uploads_accordion(reference_audio, src_audio):
    """Update Audio Uploads accordion open state based on whether audio files are present"""
    has_audio = (reference_audio is not None) or (src_audio is not None)
    return gr.Accordion(open=has_audio)


def handle_instrumental_checkbox(instrumental_checked, current_lyrics, saved_lyrics):
    """
    Handle instrumental checkbox changes.
    When checked: save current lyrics to state, replace with [Instrumental].
    When unchecked: restore saved lyrics from state.

    Returns:
        Tuple of (lyrics, lyrics_before_instrumental_state)
    """
    if instrumental_checked:
        # Save current lyrics before replacing
        return "[Instrumental]", current_lyrics
    else:
        # Restore saved lyrics (or empty if none saved)
        restored = saved_lyrics if saved_lyrics else ""
        return restored, ""


def handle_simple_instrumental_change(is_instrumental: bool):
    """
    Handle simple mode instrumental checkbox changes.
    When checked: set vocal_language to "unknown" and disable editing.
    When unchecked: enable vocal_language editing.
    
    Args:
        is_instrumental: Whether instrumental checkbox is checked
        
    Returns:
        gr.update for simple_vocal_language dropdown
    """
    if is_instrumental:
        return gr.update(value="unknown", interactive=False)
    else:
        return gr.update(interactive=True)


def update_audio_components_visibility(batch_size):
    """Show/hide individual audio components based on batch size (1-8)
    
    Row 1: Components 1-4 (batch_size 1-4)
    Row 2: Components 5-8 (batch_size 5-8)
    """
    # Clamp batch size to 1-8 range for UI
    if batch_size is None:
        batch_size = 1
    else:
        try:
            batch_size = min(max(int(batch_size), 1), 8)
        except (TypeError, ValueError):
            batch_size = 1
    
    # Row 1 columns (1-4)
    updates_row1 = (
        gr.update(visible=True),  # audio_col_1: always visible
        gr.update(visible=batch_size >= 2),  # audio_col_2
        gr.update(visible=batch_size >= 3),  # audio_col_3
        gr.update(visible=batch_size >= 4),  # audio_col_4
    )
    
    # Row 2 container and columns (5-8)
    show_row_5_8 = batch_size >= 5
    updates_row2 = (
        gr.update(visible=show_row_5_8),  # audio_row_5_8 (container)
        gr.update(visible=batch_size >= 5),  # audio_col_5
        gr.update(visible=batch_size >= 6),  # audio_col_6
        gr.update(visible=batch_size >= 7),  # audio_col_7
        gr.update(visible=batch_size >= 8),  # audio_col_8
    )
    
    return updates_row1 + updates_row2


def compute_mode_ui_updates(mode: str, llm_handler=None, previous_mode: str = "Custom"):
    """Compute gr.update() tuple for all mode-dependent UI components.
    
    Shared by handle_generation_mode_change (Radio .change event) and by
    send_audio_to_remix / send_audio_to_repaint (button .click events) so
    that mode-switch UI updates are applied atomically in a single event,
    without relying on chained .change() events.

    Args:
        mode: One of "Simple", "Custom", "Remix", "Repaint",
              "Extract", "Lego", "Complete".
        llm_handler: Optional LLM handler (used for think-checkbox state).
        previous_mode: The mode that was active before this switch.
            Used to clear polluted values when leaving Extract/Lego.

    Returns:
        Tuple of 37 gr.update objects matching the standard mode-change
        output list (see event wiring in events/__init__.py).
        Indices 0-18: original outputs.
        Indices 19-29: Extract/Lego-mode outputs (captions, lyrics, bpm,
        key_scale, time_signature, vocal_language, audio_duration,
        auto_score, autogen_checkbox, auto_lrc, analyze_btn).
        Indices 30-32: dynamic repainting labels (repainting_header_html,
        repainting_start label, repainting_end label).
        Index 33: updated previous_generation_mode state.
        Indices 34-36: mode-specific help button groups
        (remix_help_group, extract_help_group, complete_help_group).
    """
    task_type = MODE_TO_TASK_TYPE.get(mode, "text2music")

    is_simple = (mode == "Simple")
    is_custom = (mode == "Custom")
    is_cover = (mode == "Remix")
    is_repaint = (mode == "Repaint")
    is_extract = (mode == "Extract")
    is_lego = (mode == "Lego")
    is_complete = (mode == "Complete")
    leaving_extract_or_lego = previous_mode in ("Extract", "Lego")
    not_simple = not is_simple

    # --- Visibility rules ---
    show_simple = is_simple
    show_custom_group = not_simple and not is_extract
    show_generate_row = not_simple
    generate_interactive = not_simple
    show_src_audio = is_cover or is_repaint or is_extract or is_lego or is_complete
    show_optional = not_simple and not is_extract and not is_lego
    show_repainting = is_repaint or is_lego
    show_audio_codes = is_custom
    show_track_name = is_lego or is_extract
    show_complete_classes = is_complete

    # Audio cover strength: visible in Custom, Remix, Complete (NOT Extract, NOT Lego)
    show_strength = not is_simple and not is_repaint and not is_extract and not is_lego
    if is_cover:
        strength_label = t("generation.remix_strength_label")
        strength_info = t("generation.remix_strength_info")
    elif is_custom:
        strength_label = t("generation.codes_strength_label")
        strength_info = t("generation.codes_strength_info")
    else:
        strength_label = t("generation.cover_strength_label")
        strength_info = t("generation.cover_strength_info")
    strength_update = gr.update(
        visible=show_strength, label=strength_label, info=strength_info,
    )

    cover_noise_update = gr.update(visible=is_cover)

    # Think checkbox: hidden in Extract/Lego mode
    lm_initialized = llm_handler.llm_initialized if llm_handler else False
    if is_extract or is_lego or is_cover or is_repaint:
        think_update = gr.update(interactive=False, value=False, visible=not (is_extract or is_lego))
    elif not lm_initialized:
        think_update = gr.update(interactive=False, value=False, visible=True)
    else:
        think_update = gr.update(interactive=True, visible=True)

    mode_descriptions = {
        "Simple": t("generation.mode_info_simple"),
        "Custom": t("generation.mode_info_custom"),
        "Remix": t("generation.mode_info_remix"),
        "Repaint": t("generation.mode_info_repaint"),
        "Extract": t("generation.mode_info_extract"),
        "Lego": t("generation.mode_info_lego"),
        "Complete": t("generation.mode_info_complete"),
    }
    mode_help_text = mode_descriptions.get(mode, "")

    show_results = not_simple

    # Generate button label: mode-specific
    if is_extract:
        generate_btn_update = gr.update(
            interactive=generate_interactive,
            value=t("generation.extract_stem_btn"),
        )
    elif is_lego:
        generate_btn_update = gr.update(
            interactive=generate_interactive,
            value=t("generation.add_stem_btn"),
        )
    else:
        generate_btn_update = gr.update(
            interactive=generate_interactive,
            value=t("generation.generate_btn"),
        )

    # --- New outputs for Extract/Lego mode (indices 19-29) ---
    if is_extract:
        # Extract: Reset and hide all caption/lyrics/metadata fields
        captions_update = gr.update(value="", visible=False)
        lyrics_update = gr.update(value="", visible=False)
        bpm_update = gr.update(value=None, interactive=False, visible=False)
        key_scale_update = gr.update(value="", interactive=False, visible=False)
        time_signature_update = gr.update(value="", interactive=False, visible=False)
        vocal_language_update = gr.update(value="unknown", interactive=False, visible=False)
        audio_duration_update = gr.update(value=-1, interactive=False, visible=False)
        # Hide auto_score, autogen, auto_lrc, analyze_btn; disable interaction
        auto_score_update = gr.update(visible=False, value=False, interactive=False)
        autogen_update = gr.update(visible=False, value=False, interactive=False)
        auto_lrc_update = gr.update(visible=False, value=False, interactive=False)
        analyze_btn_update = gr.update(visible=False)
    elif is_lego:
        # Lego: keep caption/lyrics visible; hide metadata & automation controls
        captions_update = gr.update(visible=True, interactive=True)
        lyrics_update = gr.update(visible=True, interactive=True)
        bpm_update = gr.update(value=None, interactive=False, visible=False)
        key_scale_update = gr.update(value="", interactive=False, visible=False)
        time_signature_update = gr.update(value="", interactive=False, visible=False)
        vocal_language_update = gr.update(value="unknown", interactive=False, visible=False)
        audio_duration_update = gr.update(value=-1, interactive=False, visible=False)
        auto_score_update = gr.update(visible=False, value=False, interactive=False)
        autogen_update = gr.update(visible=False, value=False, interactive=False)
        auto_lrc_update = gr.update(visible=False, value=False, interactive=False)
        analyze_btn_update = gr.update(visible=False)
    elif not_simple:
        # Non-Extract, non-Simple: restore visibility and interactivity for
        # fields that Extract mode explicitly hid.  This ensures switching
        # from Extract → Custom/Remix/etc. brings the fields back.
        # When leaving Extract/Lego, also clear polluted values (caption was
        # set to track name, metadata was cleared to blanks, etc.).
        if leaving_extract_or_lego:
            captions_update = gr.update(value="", visible=True, interactive=True)
            lyrics_update = gr.update(value="", visible=True, interactive=True)
            bpm_update = gr.update(value=None, visible=True, interactive=True)
            key_scale_update = gr.update(value="", visible=True, interactive=True)
            time_signature_update = gr.update(value="", visible=True, interactive=True)
            vocal_language_update = gr.update(value="en", visible=True, interactive=True)
            audio_duration_update = gr.update(value=-1, visible=True, interactive=True)
        else:
            captions_update = gr.update(visible=True, interactive=True)
            lyrics_update = gr.update(visible=True, interactive=True)
            bpm_update = gr.update(visible=True, interactive=True)
            key_scale_update = gr.update(visible=True, interactive=True)
            time_signature_update = gr.update(visible=True, interactive=True)
            vocal_language_update = gr.update(visible=True, interactive=True)
            audio_duration_update = gr.update(visible=True, interactive=True)
        auto_score_update = gr.update(visible=True, interactive=True)
        autogen_update = gr.update(visible=True, interactive=True)
        auto_lrc_update = gr.update(visible=True, interactive=True)
        analyze_btn_update = gr.update(visible=True)
    else:
        # Simple mode: normally leave these fields unchanged (no-op) since
        # their visibility is controlled by parent containers.
        # However, when leaving Extract/Lego, clear polluted values so that
        # a subsequent switch to Custom/Remix/etc. starts clean.
        if leaving_extract_or_lego:
            captions_update = gr.update(value="")
            lyrics_update = gr.update(value="")
            bpm_update = gr.update(value=None)
            key_scale_update = gr.update(value="")
            time_signature_update = gr.update(value="")
            vocal_language_update = gr.update(value="en")
            audio_duration_update = gr.update(value=-1)
        else:
            captions_update = gr.update()
            lyrics_update = gr.update()
            bpm_update = gr.update()
            key_scale_update = gr.update()
            time_signature_update = gr.update()
            vocal_language_update = gr.update()
            audio_duration_update = gr.update()
        auto_score_update = gr.update()
        autogen_update = gr.update()
        auto_lrc_update = gr.update()
        analyze_btn_update = gr.update()

    # --- Dynamic repainting / stem area labels (indices 30-32) ---
    if is_lego:
        repainting_header_update = gr.update(
            value=f"<h5>{t('generation.stem_area_controls')}</h5>",
        )
        repainting_start_update = gr.update(label=t("generation.stem_start"))
        repainting_end_update = gr.update(label=t("generation.stem_end"))
    elif is_repaint:
        repainting_header_update = gr.update(
            value=f"<h5>{t('generation.repainting_controls')}</h5>",
        )
        repainting_start_update = gr.update(label=t("generation.repainting_start"))
        repainting_end_update = gr.update(label=t("generation.repainting_end"))
    else:
        # Not visible — no-op
        repainting_header_update = gr.update()
        repainting_start_update = gr.update()
        repainting_end_update = gr.update()

    # --- Auto checkbox updates (indices 37-41) ---
    # When entering Extract/Lego, force all auto checkboxes to checked (fields hidden).
    # When leaving Extract/Lego, also reset to auto since values were cleared.
    if is_extract or is_lego or leaving_extract_or_lego:
        auto_bpm_update = gr.update(value=True)
        auto_key_update = gr.update(value=True)
        auto_timesig_update = gr.update(value=True)
        auto_vocal_lang_update = gr.update(value=True)
        auto_duration_update = gr.update(value=True)
    else:
        auto_bpm_update = gr.update()
        auto_key_update = gr.update()
        auto_timesig_update = gr.update()
        auto_vocal_lang_update = gr.update()
        auto_duration_update = gr.update()

    return (
        gr.update(visible=show_simple),              # 0: simple_mode_group
        gr.update(visible=show_custom_group),         # 1: custom_mode_group
        generate_btn_update,                           # 2: generate_btn
        False,                                         # 3: simple_sample_created
        gr.Accordion(visible=show_optional, open=False),  # 4: optional_params_accordion
        gr.update(value=task_type, elem_classes=["has-info-container"]), # 5: task_type
        gr.update(visible=show_src_audio),             # 6: src_audio_row
        gr.update(visible=show_repainting),            # 7: repainting_group
        gr.update(visible=show_audio_codes),           # 8: text2music_audio_codes_group
        gr.update(visible=show_track_name),            # 9: track_name
        gr.update(visible=show_complete_classes),       # 10: complete_track_classes
        gr.update(visible=show_generate_row),          # 11: generate_btn_row
        gr.update(info=mode_help_text, elem_classes=["has-info-container"]), # 12: generation_mode
        gr.update(visible=show_results),               # 13: results_wrapper
        think_update,                                  # 14: think_checkbox
        gr.update(visible=not_simple),                 # 15: load_file_col
        gr.update(visible=not_simple),                 # 16: load_file
        strength_update,                               # 17: audio_cover_strength
        cover_noise_update,                            # 18: cover_noise_strength
        # --- Extract/Lego-mode outputs (19-29) ---
        captions_update,                               # 19: captions
        lyrics_update,                                 # 20: lyrics
        bpm_update,                                    # 21: bpm
        key_scale_update,                              # 22: key_scale
        time_signature_update,                         # 23: time_signature
        vocal_language_update,                         # 24: vocal_language
        audio_duration_update,                         # 25: audio_duration
        auto_score_update,                             # 26: auto_score
        autogen_update,                                # 27: autogen_checkbox
        auto_lrc_update,                               # 28: auto_lrc
        analyze_btn_update,                            # 29: analyze_btn
        # --- Dynamic repainting/stem labels (30-32) ---
        repainting_header_update,                      # 30: repainting_header_html
        repainting_start_update,                       # 31: repainting_start
        repainting_end_update,                         # 32: repainting_end
        # --- Previous mode state (33) ---
        mode,                                          # 33: previous_generation_mode
        # --- Mode-specific help button groups (34-36) ---
        gr.update(visible=is_cover),                   # 34: remix_help_group
        gr.update(visible=(is_extract or is_lego)),    # 35: extract_help_group
        gr.update(visible=is_complete),                # 36: complete_help_group
        # --- Auto checkbox updates (37-41) ---
        auto_bpm_update,                               # 37: bpm_auto
        auto_key_update,                               # 38: key_auto
        auto_timesig_update,                           # 39: timesig_auto
        auto_vocal_lang_update,                        # 40: vocal_lang_auto
        auto_duration_update,                          # 41: duration_auto
    )


def handle_generation_mode_change(mode: str, previous_mode: str, llm_handler=None):
    """Handle unified generation mode change.
    
    Args:
        mode: One of "Simple", "Custom", "Remix", "Repaint",
              "Extract", "Lego", "Complete".
        previous_mode: The mode that was active before this switch.
        llm_handler: Optional LLM handler.
    
    Returns:
        Tuple of 37 updates for UI components (see output list in event wiring).
    """
    return compute_mode_ui_updates(mode, llm_handler, previous_mode=previous_mode)


def handle_extract_track_name_change(track_name_value: str, mode: str):
    """Auto-fill caption with track name when in Extract mode.
    
    Args:
        track_name_value: Selected track name (e.g., "vocals", "drums").
        mode: Current generation mode.
    
    Returns:
        gr.update for captions component.
    """
    if mode == "Extract" and track_name_value:
        return gr.update(value=track_name_value)
    return gr.update()


def handle_extract_src_audio_change(src_audio_path, mode: str):
    """Auto-fill audio_duration from source audio file in Extract or Lego mode.
    
    Args:
        src_audio_path: Path to the uploaded source audio file.
        mode: Current generation mode.
    
    Returns:
        gr.update for audio_duration component.
    """
    if mode not in ("Extract", "Lego") or not src_audio_path:
        return gr.update()
    try:
        from acestep.training.dataset_builder_modules.audio_io import get_audio_duration
        duration = get_audio_duration(src_audio_path)
        if duration and duration > 0:
            return gr.update(value=float(duration))
    except Exception as e:
        logger.warning(f"Failed to get audio duration for {mode} mode: {e}")
    return gr.update()


def get_generation_mode_choices(is_pure_base: bool = False) -> list:
    """Get the list of generation mode choices based on model type.
    
    Args:
        is_pure_base: Whether the model is a pure base model (not SFT, not turbo).
            Only pure base models get extended modes (Extract, Lego, Complete).
    
    Returns:
        List of mode choice strings
    """
    if is_pure_base:
        return GENERATION_MODES_BASE
    else:
        return GENERATION_MODES_TURBO


def handle_create_sample(
    llm_handler,
    query: str,
    instrumental: bool,
    vocal_language: str,
    lm_temperature: float,
    lm_top_k: int,
    lm_top_p: float,
    constrained_decoding_debug: bool = False,
):
    """
    Handle the Create Sample button click in Simple mode.
    
    Creates a sample from the user's query using the LLM, then populates
    the caption, lyrics, and metadata fields.
    
    Note: cfg_scale and negative_prompt are not supported in create_sample mode.
    
    Args:
        llm_handler: LLM handler instance
        query: User's natural language music description
        instrumental: Whether to generate instrumental music
        vocal_language: Preferred vocal language for constrained decoding
        lm_temperature: LLM temperature for generation
        lm_top_k: LLM top-k sampling
        lm_top_p: LLM top-p sampling
        constrained_decoding_debug: Whether to enable debug logging
        
    Returns:
        Tuple of updates for:
        - captions
        - lyrics
        - bpm
        - audio_duration
        - key_scale
        - vocal_language
        - simple_vocal_language
        - time_signature
        - instrumental_checkbox
        - generate_btn (interactive)
        - simple_sample_created (True)
        - think_checkbox (True)
        - is_format_caption_state (True)
        - status_output
        - generation_mode (switch to "Custom" on success)
    """
    # Check if LLM is initialized
    if not llm_handler.llm_initialized:
        gr.Warning(t("messages.lm_not_initialized"))
        return (
            gr.update(),  # captions - no change
            gr.update(),  # lyrics - no change
            gr.update(),  # bpm - no change
            gr.update(),  # audio_duration - no change
            gr.update(),  # key_scale - no change
            gr.update(),  # vocal_language - no change
            gr.update(),  # simple vocal_language - no change
            gr.update(),  # time_signature - no change
            gr.update(),  # instrumental_checkbox - no change
            gr.update(interactive=False),  # generate_btn - keep disabled
            False,  # simple_sample_created - still False
            gr.update(),  # think_checkbox - no change
            gr.update(),  # is_format_caption_state - no change
            t("messages.lm_not_initialized"),  # status_output
            gr.update(),  # generation_mode - no change (stay in Simple)
        )
    
    # Convert LM parameters
    top_k_value = None if not lm_top_k or lm_top_k == 0 else int(lm_top_k)
    top_p_value = None if not lm_top_p or lm_top_p >= 1.0 else lm_top_p
    
    # Call create_sample API
    # Note: cfg_scale and negative_prompt are not supported in create_sample mode
    result = create_sample(
        llm_handler=llm_handler,
        query=query,
        instrumental=instrumental,
        vocal_language=vocal_language,
        temperature=lm_temperature,
        top_k=top_k_value,
        top_p=top_p_value,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )
    
    # Handle error
    if not result.success:
        gr.Warning(result.status_message or t("messages.sample_creation_failed"))
        return (
            gr.update(),  # captions - no change
            gr.update(),  # lyrics - no change
            gr.update(),  # bpm - no change
            gr.update(),  # audio_duration - no change
            gr.update(),  # key_scale - no change
            gr.update(),  # vocal_language - no change
            gr.update(),  # simple vocal_language - no change
            gr.update(),  # time_signature - no change
            gr.update(),  # instrumental_checkbox - no change
            gr.update(interactive=False),  # generate_btn - keep disabled
            False,  # simple_sample_created - still False
            gr.update(),  # think_checkbox - no change
            gr.update(),  # is_format_caption_state - no change
            result.status_message or t("messages.sample_creation_failed"),  # status_output
            gr.update(),  # generation_mode - no change (stay in Simple)
        )
    
    # Success - populate fields and auto-switch to Custom mode
    gr.Info(t("messages.sample_created"))
    
    # Clamp duration to GPU memory limit
    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    audio_duration_value = clamped_duration if clamped_duration and clamped_duration > 0 else -1
    
    return (
        result.caption,  # captions
        result.lyrics,  # lyrics
        result.bpm,  # bpm
        audio_duration_value,  # audio_duration
        result.keyscale,  # key_scale
        result.language,  # vocal_language
        result.language,  # simple vocal_language
        result.timesignature,  # time_signature
        result.instrumental,  # instrumental_checkbox
        gr.update(interactive=True),  # generate_btn - enable
        True,  # simple_sample_created - True
        True,  # think_checkbox - enable thinking
        True,  # is_format_caption_state - True (LM-generated)
        result.status_message,  # status_output
        gr.update(value="Custom"),  # generation_mode - auto-switch to Custom
    )


def handle_format_sample(
    llm_handler,
    caption: str,
    lyrics: str,
    bpm,
    audio_duration,
    key_scale: str,
    time_signature: str,
    lm_temperature: float,
    lm_top_k: int,
    lm_top_p: float,
    constrained_decoding_debug: bool = False,
):
    """
    Handle the Format button click to format caption and lyrics.
    
    Takes user-provided caption and lyrics, and uses the LLM to generate
    structured music metadata and an enhanced description.
    
    Note: cfg_scale and negative_prompt are not supported in format mode.
    
    Args:
        llm_handler: LLM handler instance
        caption: User's caption/description
        lyrics: User's lyrics
        bpm: User-provided BPM (optional, for constrained decoding)
        audio_duration: User-provided duration (optional, for constrained decoding)
        key_scale: User-provided key scale (optional, for constrained decoding)
        time_signature: User-provided time signature (optional, for constrained decoding)
        lm_temperature: LLM temperature for generation
        lm_top_k: LLM top-k sampling
        lm_top_p: LLM top-p sampling
        constrained_decoding_debug: Whether to enable debug logging
        
    Returns:
        Tuple of updates for:
        - captions
        - lyrics
        - bpm
        - audio_duration
        - key_scale
        - vocal_language
        - time_signature
        - is_format_caption_state
        - status_output
    """
    # Check if LLM is initialized
    if not llm_handler.llm_initialized:
        gr.Warning(t("messages.lm_not_initialized"))
        return (
            gr.update(),  # captions - no change
            gr.update(),  # lyrics - no change
            gr.update(),  # bpm - no change
            gr.update(),  # audio_duration - no change
            gr.update(),  # key_scale - no change
            gr.update(),  # vocal_language - no change
            gr.update(),  # time_signature - no change
            gr.update(),  # is_format_caption_state - no change
            t("messages.lm_not_initialized"),  # status_output
        )
    
    # Build user_metadata from provided values for constrained decoding
    user_metadata = {}
    if bpm is not None and bpm > 0:
        user_metadata['bpm'] = int(bpm)
    if audio_duration is not None and float(audio_duration) > 0:
        user_metadata['duration'] = int(audio_duration)
    if key_scale and key_scale.strip():
        user_metadata['keyscale'] = key_scale.strip()
    if time_signature and time_signature.strip():
        user_metadata['timesignature'] = time_signature.strip()
    
    # Only pass user_metadata if we have at least one field
    user_metadata_to_pass = user_metadata if user_metadata else None
    
    # Convert LM parameters
    top_k_value = None if not lm_top_k or lm_top_k == 0 else int(lm_top_k)
    top_p_value = None if not lm_top_p or lm_top_p >= 1.0 else lm_top_p
    
    # Call format_sample API
    result = format_sample(
        llm_handler=llm_handler,
        caption=caption,
        lyrics=lyrics,
        user_metadata=user_metadata_to_pass,
        temperature=lm_temperature,
        top_k=top_k_value,
        top_p=top_p_value,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )
    
    # Handle error
    if not result.success:
        gr.Warning(result.status_message or t("messages.format_failed"))
        return (
            gr.update(),  # captions - no change
            gr.update(),  # lyrics - no change
            gr.update(),  # bpm - no change
            gr.update(),  # audio_duration - no change
            gr.update(),  # key_scale - no change
            gr.update(),  # vocal_language - no change
            gr.update(),  # time_signature - no change
            gr.update(),  # is_format_caption_state - no change
            result.status_message or t("messages.format_failed"),  # status_output
        )
    
    # Success - populate fields
    gr.Info(t("messages.format_success"))
    
    # Clamp duration to GPU memory limit
    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    audio_duration_value = clamped_duration if clamped_duration and clamped_duration > 0 else -1
    
    return (
        result.caption,  # captions
        result.lyrics,  # lyrics
        result.bpm,  # bpm
        audio_duration_value,  # audio_duration
        result.keyscale,  # key_scale
        result.language,  # vocal_language
        result.timesignature,  # time_signature
        True,  # is_format_caption_state - True (LM-formatted)
        result.status_message,  # status_output
    )


def handle_format_caption(
    llm_handler,
    caption: str,
    lyrics: str,
    bpm,
    audio_duration,
    key_scale: str,
    time_signature: str,
    lm_temperature: float,
    lm_top_k: int,
    lm_top_p: float,
    constrained_decoding_debug: bool = False,
):
    """Format only the caption using the LLM. Lyrics are passed through unchanged.
    
    Returns:
        Tuple of updates for:
        - captions (updated)
        - bpm
        - audio_duration
        - key_scale
        - vocal_language
        - time_signature
        - is_format_caption_state
        - status_output
    """
    if not llm_handler.llm_initialized:
        gr.Warning(t("messages.lm_not_initialized"))
        return (
            gr.update(),  # captions
            gr.update(),  # bpm
            gr.update(),  # audio_duration
            gr.update(),  # key_scale
            gr.update(),  # vocal_language
            gr.update(),  # time_signature
            gr.update(),  # is_format_caption_state
            t("messages.lm_not_initialized"),  # status_output
        )

    user_metadata = {}
    if bpm is not None and bpm > 0:
        user_metadata['bpm'] = int(bpm)
    if audio_duration is not None and float(audio_duration) > 0:
        user_metadata['duration'] = int(audio_duration)
    if key_scale and key_scale.strip():
        user_metadata['keyscale'] = key_scale.strip()
    if time_signature and time_signature.strip():
        user_metadata['timesignature'] = time_signature.strip()
    user_metadata_to_pass = user_metadata if user_metadata else None

    top_k_value = None if not lm_top_k or lm_top_k == 0 else int(lm_top_k)
    top_p_value = None if not lm_top_p or lm_top_p >= 1.0 else lm_top_p

    result = format_sample(
        llm_handler=llm_handler,
        caption=caption,
        lyrics=lyrics,
        user_metadata=user_metadata_to_pass,
        temperature=lm_temperature,
        top_k=top_k_value,
        top_p=top_p_value,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        gr.Warning(result.status_message or t("messages.format_failed"))
        return (
            gr.update(),  # captions
            gr.update(),  # bpm
            gr.update(),  # audio_duration
            gr.update(),  # key_scale
            gr.update(),  # vocal_language
            gr.update(),  # time_signature
            gr.update(),  # is_format_caption_state
            result.status_message or t("messages.format_failed"),  # status_output
        )

    gr.Info(t("messages.format_success"))
    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    audio_duration_value = clamped_duration if clamped_duration and clamped_duration > 0 else -1

    # Strip surrounding quotes that LLM may add
    cleaned_caption = result.caption.strip("'\"") if result.caption else result.caption

    return (
        cleaned_caption,  # captions — updated
        result.bpm,  # bpm
        audio_duration_value,  # audio_duration
        result.keyscale,  # key_scale
        result.language,  # vocal_language
        result.timesignature,  # time_signature
        True,  # is_format_caption_state
        result.status_message,  # status_output
    )


def handle_format_lyrics(
    llm_handler,
    caption: str,
    lyrics: str,
    bpm,
    audio_duration,
    key_scale: str,
    time_signature: str,
    lm_temperature: float,
    lm_top_k: int,
    lm_top_p: float,
    constrained_decoding_debug: bool = False,
):
    """Format only the lyrics using the LLM. Caption is passed through unchanged.
    
    Returns:
        Tuple of updates for:
        - lyrics (updated)
        - bpm
        - audio_duration
        - key_scale
        - vocal_language
        - time_signature
        - is_format_caption_state
        - status_output
    """
    if not llm_handler.llm_initialized:
        gr.Warning(t("messages.lm_not_initialized"))
        return (
            gr.update(),  # lyrics
            gr.update(),  # bpm
            gr.update(),  # audio_duration
            gr.update(),  # key_scale
            gr.update(),  # vocal_language
            gr.update(),  # time_signature
            gr.update(),  # is_format_caption_state
            t("messages.lm_not_initialized"),  # status_output
        )

    user_metadata = {}
    if bpm is not None and bpm > 0:
        user_metadata['bpm'] = int(bpm)
    if audio_duration is not None and float(audio_duration) > 0:
        user_metadata['duration'] = int(audio_duration)
    if key_scale and key_scale.strip():
        user_metadata['keyscale'] = key_scale.strip()
    if time_signature and time_signature.strip():
        user_metadata['timesignature'] = time_signature.strip()
    user_metadata_to_pass = user_metadata if user_metadata else None

    top_k_value = None if not lm_top_k or lm_top_k == 0 else int(lm_top_k)
    top_p_value = None if not lm_top_p or lm_top_p >= 1.0 else lm_top_p

    result = format_sample(
        llm_handler=llm_handler,
        caption=caption,
        lyrics=lyrics,
        user_metadata=user_metadata_to_pass,
        temperature=lm_temperature,
        top_k=top_k_value,
        top_p=top_p_value,
        use_constrained_decoding=True,
        constrained_decoding_debug=constrained_decoding_debug,
    )

    if not result.success:
        gr.Warning(result.status_message or t("messages.format_failed"))
        return (
            gr.update(),  # lyrics
            gr.update(),  # bpm
            gr.update(),  # audio_duration
            gr.update(),  # key_scale
            gr.update(),  # vocal_language
            gr.update(),  # time_signature
            gr.update(),  # is_format_caption_state
            result.status_message or t("messages.format_failed"),  # status_output
        )

    gr.Info(t("messages.format_success"))
    clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
    audio_duration_value = clamped_duration if clamped_duration and clamped_duration > 0 else -1

    # Strip surrounding quotes that LLM may add
    cleaned_lyrics = result.lyrics.strip("'\"") if result.lyrics else result.lyrics

    return (
        cleaned_lyrics,  # lyrics — updated
        result.bpm,  # bpm
        audio_duration_value,  # audio_duration
        result.keyscale,  # key_scale
        result.language,  # vocal_language
        result.timesignature,  # time_signature
        True,  # is_format_caption_state
        result.status_message,  # status_output
    )
