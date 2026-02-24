"""Metadata loading and example sampling for generation handlers.

Contains functions for loading generation parameters from JSON files
and sampling random examples from the examples directory.
"""

import os
import json
import random
import glob
import gradio as gr
from typing import Optional

from acestep.ui.gradio.i18n import t
from acestep.gpu_config import get_global_gpu_config
from acestep.inference import understand_music
from .validation import clamp_duration_to_gpu_limit


def load_metadata(file_obj, llm_handler=None):
    """Load generation parameters from a JSON file.

    Args:
        file_obj: Uploaded file object.
        llm_handler: LLM handler instance (optional, for GPU duration limit check).
    """
    if file_obj is None:
        gr.Warning(t("messages.no_file_selected"))
        return [None] * 37 + [False]

    try:
        if hasattr(file_obj, 'name'):
            filepath = file_obj.name
        else:
            filepath = file_obj

        with open(filepath, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        task_type = metadata.get('task_type', 'text2music')
        captions = metadata.get('caption', '')
        lyrics = metadata.get('lyrics', '')
        vocal_language = metadata.get('vocal_language', 'unknown')

        bpm_value = metadata.get('bpm')
        if bpm_value is not None and bpm_value != "N/A":
            try:
                bpm = int(bpm_value) if bpm_value else None
            except Exception:
                bpm = None
        else:
            bpm = None

        key_scale = metadata.get('keyscale', '')
        time_signature = metadata.get('timesignature', '')

        duration_value = metadata.get('duration', -1)
        if duration_value is not None and duration_value != "N/A":
            try:
                audio_duration = float(duration_value)
                audio_duration = clamp_duration_to_gpu_limit(audio_duration, llm_handler)
            except Exception:
                audio_duration = -1
        else:
            audio_duration = -1

        batch_size = metadata.get('batch_size', 2)
        gpu_config = get_global_gpu_config()
        lm_initialized = llm_handler.llm_initialized if llm_handler else False
        max_batch_size = gpu_config.max_batch_size_with_lm if lm_initialized else gpu_config.max_batch_size_without_lm
        batch_size = min(int(batch_size), max_batch_size)
        inference_steps = metadata.get('inference_steps', 8)
        guidance_scale = metadata.get('guidance_scale', 7.0)
        seed = metadata.get('seed', '-1')
        random_seed = False
        use_adg = metadata.get('use_adg', False)
        cfg_interval_start = metadata.get('cfg_interval_start', 0.0)
        cfg_interval_end = metadata.get('cfg_interval_end', 1.0)
        audio_format = metadata.get('audio_format', 'flac')
        lm_temperature = metadata.get('lm_temperature', 0.85)
        lm_cfg_scale = metadata.get('lm_cfg_scale', 2.0)
        lm_top_k = metadata.get('lm_top_k', 0)
        lm_top_p = metadata.get('lm_top_p', 0.9)
        lm_negative_prompt = metadata.get('lm_negative_prompt', 'NO USER INPUT')
        use_cot_metas = metadata.get('use_cot_metas', True)
        use_cot_caption = metadata.get('use_cot_caption', True)
        use_cot_language = metadata.get('use_cot_language', True)
        audio_cover_strength = metadata.get('audio_cover_strength', 1.0)
        cover_noise_strength = metadata.get('cover_noise_strength', 0.0)
        think = metadata.get('thinking', True)
        lm_ok = llm_handler.llm_initialized if llm_handler else False
        if think and not lm_ok:
            think = False
            gr.Warning(t("messages.think_requires_lm"))
        audio_codes = metadata.get('audio_codes', '')
        if think and audio_codes and audio_codes.strip():
            think = False
        repainting_start = metadata.get('repainting_start', 0.0)
        repainting_end = metadata.get('repainting_end', -1)
        track_name = metadata.get('track_name')
        complete_track_classes = metadata.get('complete_track_classes', [])
        shift = metadata.get('shift', 3.0)
        infer_method = metadata.get('infer_method', 'ode')
        custom_timesteps = metadata.get('timesteps', '')
        if custom_timesteps is None:
            custom_timesteps = ''
        instrumental = metadata.get('instrumental', False)

        gr.Info(t("messages.params_loaded", filename=os.path.basename(filepath)))

        return (
            task_type, captions, lyrics, vocal_language, bpm, key_scale, time_signature,
            audio_duration, batch_size, inference_steps, guidance_scale, seed, random_seed,
            use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method,
            custom_timesteps,
            audio_format, lm_temperature, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
            use_cot_metas, use_cot_caption, use_cot_language, audio_cover_strength,
            cover_noise_strength, think, audio_codes, repainting_start, repainting_end,
            track_name, complete_track_classes, instrumental,
            True  # is_format_caption
        )

    except json.JSONDecodeError as e:
        gr.Warning(t("messages.invalid_json", error=str(e)))
        return [None] * 37 + [False]
    except Exception as e:
        gr.Warning(t("messages.load_error", error=str(e)))
        return [None] * 37 + [False]


def _get_project_root() -> str:
    """Return the project root directory (5 levels up from this file)."""
    current_file = os.path.abspath(__file__)
    # This file is in acestep/ui/gradio/events/generation/
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(current_file))))))


def load_random_example(task_type: str, llm_handler=None):
    """Load a random example from the task-specific examples directory.

    Args:
        task_type: The task type (e.g., "text2music").
        llm_handler: LLM handler instance (optional, for GPU duration limit check).

    Returns:
        Tuple of (caption, lyrics, think, bpm, duration, keyscale, language, timesignature).
    """
    try:
        project_root = _get_project_root()
        examples_dir = os.path.join(project_root, "examples", task_type)

        if not os.path.exists(examples_dir):
            gr.Warning(f"Examples directory not found: examples/{task_type}/")
            return "", "", True, None, None, "", "", ""

        json_files = glob.glob(os.path.join(examples_dir, "*.json"))
        if not json_files:
            gr.Warning(f"No JSON files found in examples/{task_type}/")
            return "", "", True, None, None, "", "", ""

        selected_file = random.choice(json_files)

        try:
            with open(selected_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            caption_value = data.get('caption', data.get('prompt', ''))
            if not isinstance(caption_value, str):
                caption_value = str(caption_value) if caption_value else ''

            lyrics_value = data.get('lyrics', '')
            if not isinstance(lyrics_value, str):
                lyrics_value = str(lyrics_value) if lyrics_value else ''

            think_value = data.get('think', True)
            if not isinstance(think_value, bool):
                think_value = True
            lm_ok = llm_handler.llm_initialized if llm_handler else False
            if think_value and not lm_ok:
                think_value = False
                gr.Warning(t("messages.think_requires_lm"))

            bpm_value: Optional[int] = None
            if 'bpm' in data and data['bpm'] not in [None, "N/A", ""]:
                try:
                    bpm_value = int(data['bpm'])
                except (ValueError, TypeError):
                    pass

            duration_value = None
            if 'duration' in data and data['duration'] not in [None, "N/A", ""]:
                try:
                    duration_value = float(data['duration'])
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
            return (caption_value, lyrics_value, think_value, bpm_value,
                    duration_value, keyscale_value, language_value, timesignature_value)

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
    """Smart sample: use LM if initialized, else fall back to examples directory.

    Args:
        llm_handler: LLM handler instance.
        task_type: The task type (e.g., "text2music").
        constrained_decoding_debug: Whether to enable debug logging.

    Returns:
        Tuple of (caption, lyrics, think, bpm, duration, keyscale, language, timesignature).
    """
    if llm_handler.llm_initialized:
        try:
            result = understand_music(
                llm_handler=llm_handler,
                audio_codes="NO USER INPUT",
                temperature=0.85,
                use_constrained_decoding=True,
                constrained_decoding_debug=constrained_decoding_debug,
            )
            if result.success:
                gr.Info(t("messages.lm_generated"))
                clamped_duration = clamp_duration_to_gpu_limit(result.duration, llm_handler)
                return (
                    result.caption, result.lyrics, True,
                    result.bpm, clamped_duration, result.keyscale,
                    result.language, result.timesignature,
                )
            else:
                gr.Warning(t("messages.lm_fallback"))
                return load_random_example(task_type)
        except Exception:
            gr.Warning(t("messages.lm_fallback"))
            return load_random_example(task_type)
    else:
        return load_random_example(task_type)


def load_random_simple_description():
    """Load a random description from the simple_mode examples directory.

    Returns:
        Tuple of (description, instrumental, vocal_language).
    """
    try:
        project_root = _get_project_root()
        examples_dir = os.path.join(project_root, "examples", "simple_mode")

        if not os.path.exists(examples_dir):
            gr.Warning(t("messages.simple_examples_not_found"))
            return gr.update(), gr.update(), gr.update()

        json_files = glob.glob(os.path.join(examples_dir, "*.json"))
        if not json_files:
            gr.Warning(t("messages.simple_examples_empty"))
            return gr.update(), gr.update(), gr.update()

        selected_file = random.choice(json_files)

        try:
            with open(selected_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            description = data.get('description', '')
            instrumental = data.get('instrumental', False)
            vocal_language = data.get('vocal_language', 'unknown')
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
