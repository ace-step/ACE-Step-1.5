"""
Generation Input Handlers Module
Contains event handlers and helper functions related to generation inputs
"""
import os
import json
import random
import glob
import gradio as gr
from typing import Optional, List, Tuple
from acestep.constants import (
    TASK_TYPES_TURBO,
    TASK_TYPES_BASE,
)
from acestep.gradio_ui.i18n import t
from acestep.inference import understand_music, create_sample, format_sample
from acestep.gpu_config import get_global_gpu_config


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
        return [None] * 36 + [False]  # Return None for all fields, False for is_format_caption
    
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
        inference_steps = metadata.get('inference_steps', 8)
        guidance_scale = metadata.get('guidance_scale', 7.0)
        seed = metadata.get('seed', '-1')
        random_seed = False  # Always set to False when loading to enable reproducibility with saved seed
        use_adg = metadata.get('use_adg', False)
        cfg_interval_start = metadata.get('cfg_interval_start', 0.0)
        cfg_interval_end = metadata.get('cfg_interval_end', 1.0)
        audio_format = metadata.get('audio_format', 'mp3')
        lm_temperature = metadata.get('lm_temperature', 0.85)
        lm_cfg_scale = metadata.get('lm_cfg_scale', 2.0)
        lm_top_k = metadata.get('lm_top_k', 0)
        lm_top_p = metadata.get('lm_top_p', 0.9)
        lm_negative_prompt = metadata.get('lm_negative_prompt', 'NO USER INPUT')
        use_cot_metas = metadata.get('use_cot_metas', True)  # Added: read use_cot_metas
        use_cot_caption = metadata.get('use_cot_caption', True)
        use_cot_language = metadata.get('use_cot_language', True)
        audio_cover_strength = metadata.get('audio_cover_strength', 1.0)
        think = metadata.get('thinking', True)  # Fixed: read 'thinking' not 'think'
        audio_codes = metadata.get('audio_codes', '')
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
            think, audio_codes, repainting_start, repainting_end,
            track_name, complete_track_classes, instrumental,
            True  # Set is_format_caption to True when loading from file
        )
        
    except json.JSONDecodeError as e:
        gr.Warning(t("messages.invalid_json", error=str(e)))
        return [None] * 36 + [False]
    except Exception as e:
        gr.Warning(t("messages.load_error", error=str(e)))
        return [None] * 36 + [False]


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


def update_model_type_settings(config_path):
    """Update UI settings based on model type (fallback when handler not initialized yet)
    
    Note: This is used as a fallback when the user changes config_path dropdown 
    before initializing the model. The actual settings are determined by the 
    handler's is_turbo_model() method after initialization.
    """
    if config_path is None:
        config_path = ""
    config_path_lower = config_path.lower()
    
    # Determine is_turbo based on config_path string
    # This is a heuristic fallback - actual model type is determined after loading
    if "turbo" in config_path_lower:
        is_turbo = True
    elif "base" in config_path_lower:
        is_turbo = False
    else:
        # Default to turbo settings for unknown model types
        is_turbo = True
    
    return get_model_type_ui_settings(is_turbo)


def init_service_wrapper(dit_handler, llm_handler, checkpoint, config_path, device, init_llm, lm_model_path, backend, use_flash_attention, offload_to_cpu, offload_dit_to_cpu, compile_model, quantization):
    """Wrapper for service initialization, returns status, button state, accordion state, and model type settings"""
    # Convert quantization checkbox to value (int8_weight_only if checked, None if not)
    quant_value = "int8_weight_only" if quantization else None
    
    # Initialize DiT handler
    status, enable = dit_handler.initialize_service(
        checkpoint, config_path, device,
        use_flash_attention=use_flash_attention, compile_model=compile_model, 
        offload_to_cpu=offload_to_cpu, offload_dit_to_cpu=offload_dit_to_cpu,
        quantization=quant_value
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
            device=device,
            offload_to_cpu=offload_to_cpu,
            dtype=dit_handler.dtype,
            disable_cuda_graphs=True,
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
    
    # Get model type settings based on actual loaded model
    is_turbo = dit_handler.is_turbo_model()
    model_type_settings = get_model_type_ui_settings(is_turbo)
    
    return (
        status, 
        gr.update(interactive=enable), 
        accordion_state,
        *model_type_settings
    )


def get_model_type_ui_settings(is_turbo: bool):
    """Get UI settings based on whether the model is turbo or base"""
    if is_turbo:
        # Turbo model: max 20 steps, default 8, show shift with default 3.0, only show text2music/repaint/cover
        return (
            gr.update(value=8, maximum=20, minimum=1),  # inference_steps
            gr.update(visible=False),  # guidance_scale
            gr.update(visible=False),  # use_adg
            gr.update(value=3.0, visible=True),  # shift (show with default 3.0)
            gr.update(visible=False),  # cfg_interval_start
            gr.update(visible=False),  # cfg_interval_end
            gr.update(choices=TASK_TYPES_TURBO),  # task_type
        )
    else:
        # Base model: max 200 steps, default 32, show CFG/ADG/shift, show all task types
        return (
            gr.update(value=32, maximum=200, minimum=1),  # inference_steps
            gr.update(visible=True),  # guidance_scale
            gr.update(visible=True),  # use_adg
            gr.update(value=3.0, visible=True),  # shift (effective for base, default 3.0)
            gr.update(visible=True),  # cfg_interval_start
            gr.update(visible=True),  # cfg_interval_end
            gr.update(choices=TASK_TYPES_BASE),  # task_type
        )


def update_negative_prompt_visibility(init_llm_checked):
    """Update negative prompt visibility: show if Initialize 5Hz LM checkbox is checked"""
    return gr.update(visible=init_llm_checked)


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
        info = t("generation.cover_strength_info")
    elif init_llm_checked:
        label = t("generation.codes_strength_label")
        info = t("generation.codes_strength_info")
    elif has_reference:
        label = t("generation.similarity_denoise_label")
        info = t("generation.similarity_denoise_info")
    else:
        label = t("generation.cover_strength_label")
        info = t("generation.cover_strength_info")
    return gr.update(visible=is_visible, label=label, info=info)


def convert_src_audio_to_codes_wrapper(dit_handler, src_audio):
    """Wrapper for converting src audio to codes"""
    codes_string = dit_handler.convert_src_audio_to_codes(src_audio)
    return codes_string


def update_instruction_ui(
    dit_handler,
    task_type_value: str, 
    track_name_value: Optional[str], 
    complete_track_classes_value: list, 
    audio_codes_content: str = "",
    init_llm_checked: bool = False,
    reference_audio=None,
) -> tuple:
    """Update instruction and UI visibility based on task type."""
    instruction = dit_handler.generate_instruction(
        task_type=task_type_value,
        track_name=track_name_value,
        complete_track_classes=complete_track_classes_value
    )
    
    # Show track_name for lego and extract
    track_name_visible = task_type_value in ["lego", "extract"]
    # Show complete_track_classes for complete
    complete_visible = task_type_value == "complete"
    # Show audio_cover_strength for cover, LM initialized, or reference audio present
    has_reference = _has_reference_audio(reference_audio)
    audio_cover_strength_visible = (task_type_value == "cover") or init_llm_checked or has_reference
    # Label priority: cover -> LM codes -> Similarity/Denoise (reference audio)
    if task_type_value == "cover":
        audio_cover_strength_label = t("generation.cover_strength_label")
        audio_cover_strength_info = t("generation.cover_strength_info")
    elif init_llm_checked:
        audio_cover_strength_label = t("generation.codes_strength_label")
        audio_cover_strength_info = t("generation.codes_strength_info")
    elif has_reference:
        audio_cover_strength_label = t("generation.similarity_denoise_label")
        audio_cover_strength_info = t("generation.similarity_denoise_info")
    else:
        audio_cover_strength_label = t("generation.cover_strength_label")
        audio_cover_strength_info = t("generation.cover_strength_info")
    # Show repainting controls for repaint and lego
    repainting_visible = task_type_value in ["repaint", "lego"]
    # Show text2music_audio_codes if task is text2music OR if it has content
    # This allows it to stay visible even if user switches task type but has codes
    has_audio_codes = audio_codes_content and str(audio_codes_content).strip()
    text2music_audio_codes_visible = task_type_value == "text2music" or has_audio_codes
    
    return (
        instruction,  # instruction_display_gen
        gr.update(visible=track_name_visible),  # track_name
        gr.update(visible=complete_visible),  # complete_track_classes
        gr.update(visible=audio_cover_strength_visible, label=audio_cover_strength_label, info=audio_cover_strength_info),  # audio_cover_strength
        gr.update(visible=repainting_visible),  # repainting_group
        gr.update(visible=text2music_audio_codes_visible),  # text2music_audio_codes_group
    )


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


def handle_instrumental_checkbox(instrumental_checked, current_lyrics):
    """
    Handle instrumental checkbox changes.
    When checked: if no lyrics, fill with [Instrumental]
    When unchecked: if lyrics is [Instrumental], clear it
    """
    if instrumental_checked:
        # If checked and no lyrics, fill with [Instrumental]
        if not current_lyrics or not current_lyrics.strip():
            return "[Instrumental]"
        else:
            # Has lyrics, don't change
            return current_lyrics
    else:
        # If unchecked and lyrics is exactly [Instrumental], clear it
        if current_lyrics and current_lyrics.strip() == "[Instrumental]":
            return ""
        else:
            # Has other lyrics, don't change
            return current_lyrics


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
    batch_size = min(max(int(batch_size), 1), 8)
    
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


def handle_generation_mode_change(mode: str):
    """
    Handle generation mode change between Simple and Custom modes.
    
    In Simple mode:
    - Show simple mode group (query input, instrumental checkbox, create button)
    - Collapse caption and lyrics accordions
    - Hide optional parameters accordion
    - Disable generate button until sample is created
    
    In Custom mode:
    - Hide simple mode group
    - Expand caption and lyrics accordions
    - Show optional parameters accordion
    - Enable generate button
    
    Args:
        mode: "simple" or "custom"
        
    Returns:
        Tuple of updates for:
        - simple_mode_group (visibility)
        - caption_accordion (open state)
        - lyrics_accordion (open state)
        - generate_btn (interactive state)
        - simple_sample_created (reset state)
        - optional_params_accordion (visibility)
    """
    is_simple = mode == "simple"
    
    return (
        gr.update(visible=is_simple),  # simple_mode_group
        gr.Accordion(open=not is_simple),  # caption_accordion - collapsed in simple, open in custom
        gr.Accordion(open=not is_simple),  # lyrics_accordion - collapsed in simple, open in custom
        gr.update(interactive=not is_simple),  # generate_btn - disabled in simple until sample created
        False,  # simple_sample_created - reset to False on mode change
        gr.Accordion(open=not is_simple),  # optional_params_accordion - hidden in simple mode
    )


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
        - time_signature
        - instrumental_checkbox
        - caption_accordion (open)
        - lyrics_accordion (open)
        - generate_btn (interactive)
        - simple_sample_created (True)
        - think_checkbox (True)
        - is_format_caption_state (True)
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
            gr.update(),  # instrumental_checkbox - no change
            gr.update(),  # caption_accordion - no change
            gr.update(),  # lyrics_accordion - no change
            gr.update(interactive=False),  # generate_btn - keep disabled
            False,  # simple_sample_created - still False
            gr.update(),  # think_checkbox - no change
            gr.update(),  # is_format_caption_state - no change
            t("messages.lm_not_initialized"),  # status_output
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
            gr.update(),  # caption_accordion - no change
            gr.update(),  # lyrics_accordion - no change
            gr.update(interactive=False),  # generate_btn - keep disabled
            False,  # simple_sample_created - still False
            gr.update(),  # think_checkbox - no change
            gr.update(),  # is_format_caption_state - no change
            result.status_message or t("messages.sample_creation_failed"),  # status_output
        )
    
    # Success - populate fields
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
        gr.Accordion(open=True),  # caption_accordion - expand
        gr.Accordion(open=True),  # lyrics_accordion - expand
        gr.update(interactive=True),  # generate_btn - enable
        True,  # simple_sample_created - True
        True,  # think_checkbox - enable thinking
        True,  # is_format_caption_state - True (LM-generated)
        result.status_message,  # status_output
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

