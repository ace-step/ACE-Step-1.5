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
from acestep.ui.gradio.events.results.generation_info import DEFAULT_RESULTS_DIR


def load_metadata(file_obj, llm_handler=None):
    """Load generation parameters from a JSON file.

    Args:
        file_obj: Uploaded file object.
        llm_handler: LLM handler instance (optional, for GPU duration limit check).
    """
    if file_obj is None:
        gr.Warning(t("messages.no_file_selected"))
        return [None] * 43 + [False]

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
        audio_format = str(metadata.get('audio_format', 'flac')).strip().lower()
        if audio_format not in {'flac', 'mp3', 'opus', 'aac', 'wav', 'wav32'}:
            audio_format = 'flac'
        mp3_bitrate = str(metadata.get('mp3_bitrate', '128k')).strip().lower()
        if mp3_bitrate not in {'128k', '192k', '256k', '320k'}:
            mp3_bitrate = '128k'
        try:
            mp3_sample_rate = int(metadata.get('mp3_sample_rate', 48000))
        except (TypeError, ValueError):
            mp3_sample_rate = 48000
        if mp3_sample_rate not in {44100, 48000}:
            mp3_sample_rate = 48000
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
        song_name = metadata.get('song_name', '')
        try:
            retake_variance = float(metadata.get('retake_variance', 0.0) or 0.0)
        except (TypeError, ValueError):
            retake_variance = 0.0
        retake_seed_value = metadata.get('retake_seed_value', metadata.get('retake_seed', ''))
        retake_seed = "" if retake_seed_value is None else str(retake_seed_value)

        is_mp3 = audio_format == "mp3"

        gr.Info(t("messages.params_loaded", filename=os.path.basename(filepath)))

        _MP3_BITRATE_CHOICES = [("128 kbps", "128k"), ("192 kbps", "192k"), ("256 kbps", "256k"), ("320 kbps", "320k")]
        _MP3_SAMPLE_RATE_CHOICES = [("48 kHz", 48000), ("44.1 kHz", 44100)]

        return (
            task_type, captions, lyrics, vocal_language, bpm, key_scale, time_signature,
            audio_duration, batch_size, inference_steps, guidance_scale, seed, random_seed,
            use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method,
            custom_timesteps,
            audio_format, gr.update(visible=is_mp3),
            gr.update(choices=_MP3_BITRATE_CHOICES, value=mp3_bitrate, visible=is_mp3),
            gr.update(choices=_MP3_SAMPLE_RATE_CHOICES, value=mp3_sample_rate, visible=is_mp3),
            lm_temperature, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
            use_cot_metas, use_cot_caption, use_cot_language, audio_cover_strength,
            cover_noise_strength, think, audio_codes, repainting_start, repainting_end,
            track_name, complete_track_classes, instrumental, song_name,
            retake_variance, retake_seed,
            True  # is_format_caption
        )

    except json.JSONDecodeError as e:
        gr.Warning(t("messages.invalid_json", error=str(e)))
        return [None] * 43 + [False]
    except Exception as e:
        gr.Warning(t("messages.load_error", error=str(e)))
        return [None] * 43 + [False]


_SAVE_DEFAULTS = {
    "vocal_language": "unknown",
    "bpm": None,
    "keyscale": "",
    "timesignature": "",
    "duration": -1,
    "batch_size": 2,
    "guidance_scale": 7.0,
    "use_adg": False,
    "cfg_interval_start": 0.0,
    "cfg_interval_end": 1.0,
    "shift": 3.0,
    "infer_method": "ode",
    "timesteps": "",
    "audio_format": "flac",
    "mp3_bitrate": "128k",
    "mp3_sample_rate": 48000,
    "lm_temperature": 0.85,
    "lm_cfg_scale": 2.0,
    "lm_top_k": 0,
    "lm_top_p": 0.9,
    "lm_negative_prompt": "NO USER INPUT",
    "use_cot_metas": True,
    "use_cot_caption": True,
    "use_cot_language": True,
    "audio_cover_strength": 1.0,
    "cover_noise_strength": 0.0,
    "repainting_start": 0.0,
    "repainting_end": -1,
    "track_name": None,
    "complete_track_classes": [],
    "instrumental": False,
}


def save_project(
    task_type, captions, lyrics, vocal_language, bpm, key_scale, time_signature,
    audio_duration, batch_size_input, inference_steps, guidance_scale, seed,
    random_seed_checkbox, use_adg, cfg_interval_start, cfg_interval_end, shift,
    infer_method, custom_timesteps, audio_format, mp3_bitrate, mp3_sample_rate,
    lm_temperature, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
    use_cot_metas, use_cot_caption, use_cot_language, audio_cover_strength,
    cover_noise_strength, think_checkbox, text2music_audio_code_string,
    repainting_start, repainting_end, track_name, complete_track_classes,
    instrumental_checkbox, song_name,
):
    """Save current generation parameters to a JSON file, omitting default values.

    Always includes caption and lyrics. All other fields are written only when
    they differ from their known defaults, keeping saved files compact.

    Args:
        All generation UI component values (see _SAVE_PROJECT_INPUT_KEYS in wiring).
        song_name: Optional project name used as the filename base.

    Returns:
        Absolute path to the written JSON temp file, for Gradio File output.
    """
    try:
        return _save_project_impl(
            task_type, captions, lyrics, vocal_language, bpm, key_scale, time_signature,
            audio_duration, batch_size_input, inference_steps, guidance_scale, seed,
            random_seed_checkbox, use_adg, cfg_interval_start, cfg_interval_end, shift,
            infer_method, custom_timesteps, audio_format, mp3_bitrate, mp3_sample_rate,
            lm_temperature, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
            use_cot_metas, use_cot_caption, use_cot_language, audio_cover_strength,
            cover_noise_strength, think_checkbox, text2music_audio_code_string,
            repainting_start, repainting_end, track_name, complete_track_classes,
            instrumental_checkbox, song_name,
        )
    except Exception as e:
        gr.Warning(t("messages.save_error", error=str(e)))
        return gr.update(visible=False)


def _save_project_impl(
    task_type, captions, lyrics, vocal_language, bpm, key_scale, time_signature,
    audio_duration, batch_size_input, inference_steps, guidance_scale, seed,
    random_seed_checkbox, use_adg, cfg_interval_start, cfg_interval_end, shift,
    infer_method, custom_timesteps, audio_format, mp3_bitrate, mp3_sample_rate,
    lm_temperature, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
    use_cot_metas, use_cot_caption, use_cot_language, audio_cover_strength,
    cover_noise_strength, think_checkbox, text2music_audio_code_string,
    repainting_start, repainting_end, track_name, complete_track_classes,
    instrumental_checkbox, song_name,
):
    import datetime

    def _ne(value, default_key):
        return value != _SAVE_DEFAULTS[default_key]

    data = {}

    if task_type and task_type != "text2music":
        data["task_type"] = task_type
    if captions:
        data["caption"] = captions
    if lyrics:
        data["lyrics"] = lyrics

    if _ne(vocal_language, "vocal_language"):
        data["vocal_language"] = vocal_language
    if bpm is not None and _ne(bpm, "bpm"):
        data["bpm"] = bpm
    if key_scale and _ne(key_scale, "keyscale"):
        data["keyscale"] = key_scale
    if time_signature and _ne(time_signature, "timesignature"):
        data["timesignature"] = time_signature
    if _ne(audio_duration, "duration"):
        data["duration"] = audio_duration
    if _ne(batch_size_input, "batch_size"):
        data["batch_size"] = batch_size_input

    # Always save inference_steps — default varies by model
    data["inference_steps"] = inference_steps

    if _ne(guidance_scale, "guidance_scale"):
        data["guidance_scale"] = guidance_scale
    if not random_seed_checkbox and seed and str(seed) != "-1":
        data["seed"] = seed
    if _ne(use_adg, "use_adg"):
        data["use_adg"] = use_adg
    if _ne(cfg_interval_start, "cfg_interval_start"):
        data["cfg_interval_start"] = cfg_interval_start
    if _ne(cfg_interval_end, "cfg_interval_end"):
        data["cfg_interval_end"] = cfg_interval_end
    if _ne(shift, "shift"):
        data["shift"] = shift
    if _ne(infer_method, "infer_method"):
        data["infer_method"] = infer_method
    if custom_timesteps and _ne(custom_timesteps, "timesteps"):
        data["timesteps"] = custom_timesteps
    if _ne(audio_format, "audio_format"):
        data["audio_format"] = audio_format
    if audio_format == "mp3":
        if _ne(mp3_bitrate, "mp3_bitrate"):
            data["mp3_bitrate"] = mp3_bitrate
        if _ne(mp3_sample_rate, "mp3_sample_rate"):
            data["mp3_sample_rate"] = mp3_sample_rate
    if _ne(lm_temperature, "lm_temperature"):
        data["lm_temperature"] = lm_temperature
    if _ne(lm_cfg_scale, "lm_cfg_scale"):
        data["lm_cfg_scale"] = lm_cfg_scale
    if _ne(lm_top_k, "lm_top_k"):
        data["lm_top_k"] = lm_top_k
    if _ne(lm_top_p, "lm_top_p"):
        data["lm_top_p"] = lm_top_p
    if _ne(lm_negative_prompt, "lm_negative_prompt"):
        data["lm_negative_prompt"] = lm_negative_prompt
    if _ne(use_cot_metas, "use_cot_metas"):
        data["use_cot_metas"] = use_cot_metas
    if _ne(use_cot_caption, "use_cot_caption"):
        data["use_cot_caption"] = use_cot_caption
    if _ne(use_cot_language, "use_cot_language"):
        data["use_cot_language"] = use_cot_language
    if _ne(audio_cover_strength, "audio_cover_strength"):
        data["audio_cover_strength"] = audio_cover_strength
    if _ne(cover_noise_strength, "cover_noise_strength"):
        data["cover_noise_strength"] = cover_noise_strength
    data["thinking"] = bool(think_checkbox)
    if text2music_audio_code_string and text2music_audio_code_string.strip():
        data["audio_codes"] = text2music_audio_code_string
    if _ne(repainting_start, "repainting_start"):
        data["repainting_start"] = repainting_start
    if _ne(repainting_end, "repainting_end"):
        data["repainting_end"] = repainting_end
    if track_name and _ne(track_name, "track_name"):
        data["track_name"] = track_name
    if complete_track_classes and _ne(complete_track_classes, "complete_track_classes"):
        data["complete_track_classes"] = complete_track_classes
    if _ne(instrumental_checkbox, "instrumental"):
        data["instrumental"] = instrumental_checkbox
    if song_name and song_name.strip():
        data["song_name"] = song_name.strip()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = (song_name or "").strip()
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in base)[:80].strip("_. ")
    safe = safe or "project"
    filename = f"{safe}_{timestamp}.json"

    projects_dir = os.path.join(DEFAULT_RESULTS_DIR, "projects")
    os.makedirs(projects_dir, exist_ok=True)
    filepath = os.path.join(projects_dir, filename)
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, filepath)

    gr.Info(t("messages.project_saved", filename=filename))
    return gr.update(value=filepath, visible=True)


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
