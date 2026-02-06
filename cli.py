import argparse
import re
import ast
import os
import sys
import toml
from pathlib import Path
from typing import List, Optional, Tuple

# Load environment variables from .env or .env.example (if available)
try:
    from dotenv import load_dotenv
    _current_file = os.path.abspath(__file__)
    _project_root = os.path.dirname(_current_file)
    _env_path = os.path.join(_project_root, '.env')
    _env_example_path = os.path.join(_project_root, '.env.example')

    if os.path.exists(_env_path):
        load_dotenv(_env_path)
        print(f"Loaded configuration from {_env_path}")
    elif os.path.exists(_env_example_path):
        load_dotenv(_env_example_path)
        print(f"Loaded configuration from {_env_example_path} (fallback)")
except ImportError:
    pass

# Clear proxy settings that may affect network behavior
for _proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    os.environ.pop(_proxy_var, None)

def _configure_logging(
    level: Optional[str] = None,
    suppress_audio_tokens: Optional[bool] = None,
) -> None:
    try:
        from loguru import logger
    except Exception:
        return

    if suppress_audio_tokens is None:
        suppress_audio_tokens = os.environ.get("ACE_STEP_SUPPRESS_AUDIO_TOKENS", "1") not in {"0", "false", "False"}
    if level is None:
        level = "INFO"
    level = str(level).upper()

    def _log_filter(record) -> bool:
        message = record.get("message", "")
        # Suppress duplicate DiT prompt logs (we print a single final prompt in cli.py)
        if (
            "DiT TEXT ENCODER INPUT" in message
            or "text_prompt:" in message
            or (message.strip() and set(message.strip()) == {"="})
        ):
            return False
        if not suppress_audio_tokens:
            return True
        return "<|audio_code_" not in message

    logger.remove()
    logger.add(sys.stderr, level=level, filter=_log_filter)


_configure_logging()

from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music, create_sample, format_sample
from acestep.constants import DEFAULT_DIT_INSTRUCTION, TASK_INSTRUCTIONS
from acestep.gpu_config import get_gpu_config, set_global_gpu_config, GPUConfig, GPU_TIER_CONFIGS
import torch


TRACK_CHOICES = [
    "vocals",
    "backing_vocals",
    "drums",
    "bass",
    "guitar",
    "keyboard",
    "percussion",
    "strings",
    "synth",
    "fx",
    "brass",
    "woodwinds",
]


def _get_project_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _parse_description_hints(description: str) -> tuple[Optional[str], bool]:
    import re

    if not description:
        return None, False

    description_lower = description.lower().strip()

    language_mapping = {
        'english': 'en', 'en': 'en',
        'chinese': 'zh', '中文': 'zh', 'zh': 'zh', 'mandarin': 'zh',
        'japanese': 'ja', '日本語': 'ja', 'ja': 'ja',
        'korean': 'ko', '한국어': 'ko', 'ko': 'ko',
        'spanish': 'es', 'español': 'es', 'es': 'es',
        'french': 'fr', 'français': 'fr', 'fr': 'fr',
        'german': 'de', 'deutsch': 'de', 'de': 'de',
        'italian': 'it', 'italiano': 'it', 'it': 'it',
        'portuguese': 'pt', 'português': 'pt', 'pt': 'pt',
        'russian': 'ru', 'русский': 'ru', 'ru': 'ru',
        'bengali': 'bn', 'bn': 'bn',
        'hindi': 'hi', 'hi': 'hi',
        'arabic': 'ar', 'ar': 'ar',
        'thai': 'th', 'th': 'th',
        'vietnamese': 'vi', 'vi': 'vi',
        'indonesian': 'id', 'id': 'id',
        'turkish': 'tr', 'tr': 'tr',
        'dutch': 'nl', 'nl': 'nl',
        'polish': 'pl', 'pl': 'pl',
    }

    detected_language = None
    for lang_name, lang_code in language_mapping.items():
        if len(lang_name) <= 2:
            pattern = r'(?:^|\s|[.,;:!?])' + re.escape(lang_name) + r'(?:$|\s|[.,;:!?])'
        else:
            pattern = r'\b' + re.escape(lang_name) + r'\b'
        if re.search(pattern, description_lower):
            detected_language = lang_code
            break

    is_instrumental = False
    if 'instrumental' in description_lower:
        is_instrumental = True
    elif 'pure music' in description_lower or 'pure instrument' in description_lower:
        is_instrumental = True
    elif description_lower.endswith(' solo') or description_lower == 'solo':
        is_instrumental = True

    return detected_language, is_instrumental


def _prompt_non_empty(prompt: str) -> str:
    value = input(prompt).strip()
    while not value:
        value = input(prompt).strip()
    return value


def _prompt_with_default(prompt: str, default: Optional[str] = None, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default not in (None, "") else ""
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default not in (None, ""):
            return str(default)
        if not required:
            return ""
        print("This value is required. Please try again.")


def _prompt_bool(prompt: str, default: bool) -> bool:
    default_str = "y" if default else "n"
    while True:
        value = input(f"{prompt} (y/n) [default: {default_str}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes", "1", "true"}:
            return True
        if value in {"n", "no", "0", "false"}:
            return False
        print("Please enter 'y' or 'n'.")


def _prompt_choice_from_list(
    prompt: str,
    options: List[str],
    default: Optional[str] = None,
    allow_custom: bool = True,
    custom_validator=None,
    custom_error: Optional[str] = None,
) -> Optional[str]:
    if not options:
        return default
    print("\n" + prompt)
    for idx, option in enumerate(options, start=1):
        print(f"{idx}. {option}")
    default_display = default if default not in (None, "") else "auto"
    while True:
        choice = input(f"Choose a model (number or name) [default: {default_display}]: ").strip()
        if not choice:
            return None if default_display == "auto" else default
        if choice.lower() == "auto":
            return None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1]
            print("Invalid selection. Please choose a valid number.")
            continue
        if allow_custom:
            if custom_validator and not custom_validator(choice):
                print(custom_error or "Invalid selection. Please try again.")
                continue
            if choice not in options:
                print("Unknown model. Using as-is.")
            return choice
        print("Please choose a valid option.")


def _edit_formatted_prompt_via_file(formatted_prompt: str, instruction_path: str) -> str:
    """Write formatted prompt to file, wait for user edits, then read back."""
    try:
        with open(instruction_path, "w", encoding="utf-8") as f:
            f.write(formatted_prompt)
    except Exception as e:
        print(f"WARNING: Failed to write {instruction_path}: {e}")
        return formatted_prompt

    print("\n--- Final Draft Saved ---")
    print(f"Saved to {instruction_path}")
    print("Edit the file now. Press Enter when ready to continue.")
    input()

    try:
        with open(instruction_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"WARNING: Failed to read {instruction_path}: {e}")
        return formatted_prompt


def _extract_caption_lyrics_from_formatted_prompt(formatted_prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort extraction of caption/lyrics from a formatted prompt string."""
    matches = list(re.finditer(r"# Caption\n(.*?)\n+# Lyric\n(.*)", formatted_prompt, re.DOTALL))
    if not matches:
        return None, None

    caption = matches[-1].group(1).strip()
    lyrics = matches[-1].group(2)

    # Trim lyrics if chat-template markers appear after the user message.
    cut_markers = ["<|eot_id|>", "<|start_header_id|>", "<|assistant|>", "<|user|>", "<|system|>"]
    cut_at = len(lyrics)
    for marker in cut_markers:
        pos = lyrics.find(marker)
        if pos != -1:
            cut_at = min(cut_at, pos)
    lyrics = lyrics[:cut_at].rstrip()

    return caption or None, lyrics or None


def _extract_instruction_from_formatted_prompt(formatted_prompt: str) -> Optional[str]:
    """Best-effort extraction of instruction text from a formatted prompt string."""
    match = re.search(r"# Instruction\n(.*?)\n\n", formatted_prompt, re.DOTALL)
    if not match:
        return None
    instruction = match.group(1).strip()
    return instruction or None


def _extract_cot_metadata_from_formatted_prompt(formatted_prompt: str) -> dict:
    """Best-effort extraction of COT metadata from a formatted prompt string."""
    matches = list(re.finditer(r"<think>\n(.*?)\n</think>", formatted_prompt, re.DOTALL))
    if not matches:
        return {}
    block = matches[-1].group(1)
    metadata = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key:
            metadata[key] = value
    return metadata


def _parse_number(value: str) -> Optional[float]:
    try:
        match = re.search(r"[-+]?\d*\.?\d+", value)
        if not match:
            return None
        return float(match.group(0))
    except Exception:
        return None


def _parse_timesteps_input(value) -> Optional[List[float]]:
    if value is None:
        return None
    if isinstance(value, list):
        if all(isinstance(t, (int, float)) for t in value):
            return [float(t) for t in value]
        return None
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("[") or raw.startswith("("):
        try:
            parsed = ast.literal_eval(raw)
        except Exception:
            return None
        if isinstance(parsed, list) and all(isinstance(t, (int, float)) for t in parsed):
            return [float(t) for t in parsed]
        return None
    try:
        return [float(t.strip()) for t in raw.split(",") if t.strip()]
    except Exception:
        return None


def _install_prompt_edit_hook(
    llm_handler: LLMHandler,
    instruction_path: str,
    preloaded_prompt: Optional[str] = None,
) -> None:
    """Intercept formatted prompt generation to allow user editing before audio tokens."""
    original = llm_handler.build_formatted_prompt_with_cot
    cache = {}

    def wrapped(caption, lyrics, cot_text, is_negative_prompt=False, negative_prompt="NO USER INPUT"):
        prompt = original(
            caption,
            lyrics,
            cot_text,
            is_negative_prompt=is_negative_prompt,
            negative_prompt=negative_prompt,
        )
        if is_negative_prompt:
            conditional_prompt = original(
                caption,
                lyrics,
                cot_text,
                is_negative_prompt=False,
                negative_prompt=negative_prompt,
            )
            cached = cache.get(conditional_prompt)
            if cached and (cached.get("edited_caption") or cached.get("edited_lyrics")):
                edited_caption = cached.get("edited_caption") or caption
                edited_lyrics = cached.get("edited_lyrics") or lyrics
                return original(
                    edited_caption,
                    edited_lyrics,
                    cot_text,
                    is_negative_prompt=True,
                    negative_prompt=negative_prompt,
                )
            return prompt
        cached = cache.get(prompt)
        if cached:
            return cached["edited_prompt"]
        if getattr(llm_handler, "_skip_prompt_edit", False):
            cache[prompt] = {
                "edited_prompt": prompt,
                "edited_caption": None,
                "edited_lyrics": None,
            }
            return prompt
        if preloaded_prompt is not None:
            edited = preloaded_prompt
        else:
            edited = _edit_formatted_prompt_via_file(prompt, instruction_path)
        edited_caption, edited_lyrics = _extract_caption_lyrics_from_formatted_prompt(edited)
        if edited != prompt:
            print("INFO: Using edited draft for audio-token prompt.")
            if edited_caption or edited_lyrics:
                llm_handler._edited_caption = edited_caption
                llm_handler._edited_lyrics = edited_lyrics
            edited_instruction = _extract_instruction_from_formatted_prompt(edited)
            if edited_instruction:
                llm_handler._edited_instruction = edited_instruction
            edited_metas = _extract_cot_metadata_from_formatted_prompt(edited)
            if edited_metas:
                llm_handler._edited_metas = edited_metas
        cache[prompt] = {
            "edited_prompt": edited,
            "edited_caption": edited_caption,
            "edited_lyrics": edited_lyrics,
        }
        return edited

    llm_handler.build_formatted_prompt_with_cot = wrapped


def _prompt_int(prompt: str, default: Optional[int] = None, min_value: Optional[int] = None,
                max_value: Optional[int] = None) -> Optional[int]:
    default_display = "auto" if default is None else default
    while True:
        value = input(f"{prompt} [{default_display}]: ").strip()
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            print("Invalid input. Please enter an integer.")
            continue
        if min_value is not None and parsed < min_value:
            print(f"Please enter a value >= {min_value}.")
            continue
        if max_value is not None and parsed > max_value:
            print(f"Please enter a value <= {max_value}.")
            continue
        return parsed


def _prompt_float(prompt: str, default: Optional[float] = None, min_value: Optional[float] = None,
                  max_value: Optional[float] = None) -> Optional[float]:
    default_display = "auto" if default is None else default
    while True:
        value = input(f"{prompt} [{default_display}]: ").strip()
        if not value:
            return default
        try:
            parsed = float(value)
        except ValueError:
            print("Invalid input. Please enter a number.")
            continue
        if min_value is not None and parsed < min_value:
            print(f"Please enter a value >= {min_value}.")
            continue
        if max_value is not None and parsed > max_value:
            print(f"Please enter a value <= {max_value}.")
            continue
        return parsed


def _prompt_existing_file(prompt: str, default: Optional[str] = None) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        path = input(f"{prompt}{suffix}: ").strip()
        if not path and default:
            path = default
        if os.path.isfile(path):
            return _expand_audio_path(path)
        print("Invalid file path. Please try again.")


def _expand_audio_path(path_str: Optional[str]) -> Optional[str]:
    if not path_str or not isinstance(path_str, str):
        return path_str
    try:
        return Path(path_str).expanduser().resolve(strict=False).as_posix()
    except Exception:
        return Path(path_str).expanduser().absolute().as_posix()


def _parse_bool(value: str) -> bool:
    return str(value).lower() in {"true", "1", "yes", "y"}


def _resolve_device(device: str) -> str:
    if device == "auto":
        if hasattr(torch, 'xpu') and torch.xpu.is_available():
            return "xpu"
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return device


def _get_mps_wired_limit_mb() -> Optional[int]:
    """Best-effort read of iogpu.wired_limit_mb on macOS (may be unavailable)."""
    try:
        import subprocess
        out = subprocess.check_output(["sysctl", "iogpu.wired_limit_mb"], text=True).strip()
        # Expected: "iogpu.wired_limit_mb: 12345"
        parts = out.split(":")
        if len(parts) == 2:
            value = parts[1].strip()
            return int(value)
    except Exception:
        pass
    return None


def _default_instruction_for_task(task_type: str, tracks: Optional[List[str]] = None) -> str:
    if task_type == "lego":
        track = tracks[0] if tracks else "guitar"
        return TASK_INSTRUCTIONS["lego"].format(TRACK_NAME=track.upper())
    if task_type == "extract":
        track = tracks[0] if tracks else "vocals"
        return TASK_INSTRUCTIONS["extract"].format(TRACK_NAME=track.upper())
    if task_type == "complete":
        tracks_list = ", ".join(tracks) if tracks else "drums, bass, guitar"
        return TASK_INSTRUCTIONS["complete"].format(TRACK_CLASSES=tracks_list)
    return DEFAULT_DIT_INSTRUCTION


def _apply_optional_defaults(args, params_defaults: GenerationParams, config_defaults: GenerationConfig) -> None:
    optional_defaults = {
        "duration": params_defaults.duration,
        "bpm": params_defaults.bpm,
        "keyscale": params_defaults.keyscale,
        "timesignature": params_defaults.timesignature,
        "vocal_language": params_defaults.vocal_language,
        "inference_steps": params_defaults.inference_steps,
        "seed": params_defaults.seed,
        "guidance_scale": params_defaults.guidance_scale,
        "use_adg": params_defaults.use_adg,
        "cfg_interval_start": params_defaults.cfg_interval_start,
        "cfg_interval_end": params_defaults.cfg_interval_end,
        "shift": 3.0,
        "infer_method": params_defaults.infer_method,
        "timesteps": None,
        "repainting_start": params_defaults.repainting_start,
        "repainting_end": params_defaults.repainting_end,
        "audio_cover_strength": params_defaults.audio_cover_strength,
        "thinking": params_defaults.thinking,
        "lm_temperature": params_defaults.lm_temperature,
        "lm_cfg_scale": params_defaults.lm_cfg_scale,
        "lm_top_k": params_defaults.lm_top_k,
        "lm_top_p": params_defaults.lm_top_p,
        "lm_negative_prompt": params_defaults.lm_negative_prompt,
        "use_cot_metas": params_defaults.use_cot_metas,
        "use_cot_caption": params_defaults.use_cot_caption,
        "use_cot_lyrics": params_defaults.use_cot_lyrics,
        "use_cot_language": params_defaults.use_cot_language,
        "use_constrained_decoding": params_defaults.use_constrained_decoding,
        "batch_size": config_defaults.batch_size,
        "allow_lm_batch": config_defaults.allow_lm_batch,
        "use_random_seed": config_defaults.use_random_seed,
        "seeds": config_defaults.seeds,
        "lm_batch_chunk_size": config_defaults.lm_batch_chunk_size,
        "constrained_decoding_debug": config_defaults.constrained_decoding_debug,
        "audio_format": config_defaults.audio_format,
        "sample_mode": False,
        "sample_query": "",
        "use_format": False,
    }

    for key, default_value in optional_defaults.items():
        if getattr(args, key, None) is None:
            setattr(args, key, default_value)


def _summarize_lyrics(lyrics: Optional[str]) -> str:
    if not lyrics:
        return "none"
    if isinstance(lyrics, str):
        stripped = lyrics.strip()
        if not stripped:
            return "none"
        if os.path.isfile(stripped):
            return f"file: {os.path.basename(stripped)}"
        if len(stripped) <= 60:
            return stripped.replace("\n", " ")
        return f"text ({len(stripped)} chars)"
    return "provided"


def _print_final_parameters(
    args,
    params: GenerationParams,
    config: GenerationConfig,
    params_defaults: GenerationParams,
    config_defaults: GenerationConfig,
    compact: bool,
    resolved_device: Optional[str] = None,
) -> None:
    if not compact:
        print("\n--- Final Parameters (Args) ---")
        for k in sorted(vars(args).keys()):
            print(f"{k}: {getattr(args, k)}")
        print("------------------------------")
        print("\n--- Final Parameters (GenerationParams) ---")
        for k in sorted(vars(params).keys()):
            print(f"{k}: {getattr(params, k)}")
        print("-------------------------------------------")
        print("\n--- Final Parameters (GenerationConfig) ---")
        for k in sorted(vars(config).keys()):
            print(f"{k}: {getattr(config, k)}")
        print("-------------------------------------------\n")
        return

    device_display = args.device
    if resolved_device and resolved_device != args.device:
        device_display = f"{args.device} -> {resolved_device}"

    print("\n--- Final Parameters (Summary) ---")
    print(f"task_type: {params.task_type}")
    print(f"caption: {params.caption or 'none'}")
    print(f"lyrics: {_summarize_lyrics(params.lyrics)}")
    print(f"duration: {params.duration}s")
    print(f"outputs: {config.batch_size}")
    if params.bpm not in (None, params_defaults.bpm):
        print(f"bpm: {params.bpm}")
    if params.keyscale not in (None, params_defaults.keyscale):
        print(f"keyscale: {params.keyscale}")
    if params.timesignature not in (None, params_defaults.timesignature):
        print(f"timesignature: {params.timesignature}")
    print(f"instrumental: {params.instrumental}")
    print(f"thinking: {params.thinking}")
    print(f"lm_model: {args.lm_model_path or 'auto'}")
    print(f"dit_model: {args.config_path or 'auto'}")
    print(f"backend: {args.backend}")
    print(f"device: {device_display}")
    print(f"audio_format: {config.audio_format}")
    print(f"save_dir: {args.save_dir}")
    if config.seeds:
        print(f"seeds: {config.seeds}")
    else:
        print(f"seed: {params.seed} (random={config.use_random_seed})")
    print("-------------------------------\n")


def _build_meta_dict(params: GenerationParams) -> Optional[dict]:
    meta = {}
    if params.bpm is not None:
        meta["bpm"] = params.bpm
    if params.timesignature:
        meta["timesignature"] = params.timesignature
    if params.keyscale:
        meta["keyscale"] = params.keyscale
    if params.duration is not None:
        meta["duration"] = params.duration
    return meta or None


def _print_dit_prompt(dit_handler: "AceStepHandler", params: GenerationParams) -> None:
    meta = _build_meta_dict(params)
    caption_input, lyrics_input = dit_handler.build_dit_inputs(
        task=params.task_type,
        instruction=params.instruction,
        caption=params.caption or "",
        lyrics=params.lyrics or "",
        metas=meta,
        vocal_language=params.vocal_language or "unknown",
    )
    print("\n--- Final DiT Prompt (Caption Branch) ---")
    print(caption_input)
    print("\n--- Final DiT Prompt (Lyrics Branch) ---")
    print(lyrics_input)
    print("----------------------------------------\n")


def run_wizard(args, configure_only: bool = False, default_config_path: Optional[str] = None,
               params_defaults: Optional[GenerationParams] = None,
               config_defaults: Optional[GenerationConfig] = None):
    """
    Runs an interactive wizard to set generation parameters.
    """
    print("Welcome to the ACE-Step Music Generation Wizard!")
    print("This will guide you through creating your music.")
    print("Press Ctrl+C at any time to exit.")
    print("Note: Required models will be auto-downloaded if missing.")
    print("-" * 30)

    try:
        # Task selection
        print("\n--- Task Type ---")
        print("1. text2music - generate music from text/lyrics.")
        print("2. cover     - transform existing audio into a new style.")
        print("3. repaint   - regenerate a specific time segment of audio.")
        print("4. lego      - generate a specific instrument track in context.")
        print("5. extract   - isolate a specific instrument track from a mix.")
        print("6. complete  - complete/extend partial tracks with new instruments.")
        task_map = {
            "1": "text2music",
            "2": "cover",
            "3": "repaint",
            "4": "lego",
            "5": "extract",
            "6": "complete",
        }
        current_task = args.task_type or "text2music"
        task_default = next((k for k, v in task_map.items() if v == current_task), "1")
        task_choice = input(f"Choose a task (1-6) [default: {task_default}]: ").strip()
        if not task_choice:
            task_choice = task_default
        args.task_type = task_map.get(task_choice, "text2music")
        if args.task_type in {"lego", "extract", "complete"}:
            print("Note: This task requires a base DiT model (acestep-v15-base). It will be auto-downloaded if missing.")

        # Model selection (DiT)
        dit_handler = AceStepHandler()
        available_dit_models = dit_handler.get_available_acestep_v15_models()
        base_only = args.task_type in {"lego", "extract", "complete"}
        if base_only and available_dit_models:
            available_dit_models = [m for m in available_dit_models if "base" in m.lower()]

        if base_only and args.config_path and "base" not in str(args.config_path).lower():
            args.config_path = None

        if base_only:
            if available_dit_models:
                if args.config_path in available_dit_models:
                    selected = args.config_path
                else:
                    selected = available_dit_models[0]
                args.config_path = selected
                print(f"\nNote: This task requires a base model. Using: {selected}")
            else:
                print("\nNote: This task requires a base model (e.g., 'acestep-v15-base'). It will be auto-downloaded if missing.")
        elif available_dit_models:
            selected = _prompt_choice_from_list(
                "--- Available DiT Models ---",
                available_dit_models,
                default=args.config_path,
                allow_custom=True,
            )
            if selected is not None:
                args.config_path = selected
        else:
            print("\nNote: No local DiT models found. The main model will be auto-downloaded during initialization.")

        # Model selection (LM)
        llm_handler = LLMHandler()
        available_lm_models = llm_handler.get_available_5hz_lm_models()
        if available_lm_models:
            selected_lm = _prompt_choice_from_list(
                "--- Available LM Models ---",
                available_lm_models,
                default=args.lm_model_path,
                allow_custom=True,
            )
            if selected_lm is not None:
                args.lm_model_path = selected_lm
        else:
            print("\nNote: No local LM models found. If LM features are enabled, a default LM will be auto-downloaded.")

        # Task-specific inputs
        if args.task_type in {"cover", "repaint", "lego", "extract", "complete"}:
            args.src_audio = _prompt_existing_file("Enter path to source audio file", default=args.src_audio)

        if args.task_type == "repaint":
            args.repainting_start = _prompt_float(
                "Repaint start time in seconds", args.repainting_start
            )
            args.repainting_end = _prompt_float(
                "Repaint end time in seconds", args.repainting_end
            )

        if args.task_type in {"lego", "extract"}:
            print("\nAvailable tracks:")
            print(", ".join(TRACK_CHOICES))
            track_default = args.lego_track if args.task_type == "lego" else args.extract_track
            track = _prompt_with_default("Choose a track", track_default, required=True)
            if track not in TRACK_CHOICES:
                print("Unknown track. Using as-is.")
            if args.task_type == "lego":
                args.lego_track = track
            else:
                args.extract_track = track
            if not args.instruction or args.instruction == DEFAULT_DIT_INSTRUCTION:
                args.instruction = _default_instruction_for_task(args.task_type, [track])
            args.instruction = _prompt_with_default("Instruction", args.instruction, required=True)

        if args.task_type == "complete":
            print("\nAvailable tracks:")
            print(", ".join(TRACK_CHOICES))
            tracks_raw = _prompt_with_default("Choose tracks (comma-separated)", args.complete_tracks, required=True)
            tracks = [t.strip() for t in tracks_raw.split(",") if t.strip()]
            args.complete_tracks = ",".join(tracks)
            if not args.instruction or args.instruction == DEFAULT_DIT_INSTRUCTION:
                args.instruction = _default_instruction_for_task(args.task_type, tracks)
            args.instruction = _prompt_with_default("Instruction", args.instruction, required=True)

        if args.task_type in {"cover", "repaint", "lego", "complete"}:
            args.caption = _prompt_with_default(
                "Enter a music description (e.g., 'upbeat electronic dance music')",
                args.caption,
                required=True,
            )
        elif args.task_type == "text2music":
            args.sample_mode = _prompt_bool("Use Simple Mode (auto-generate caption/lyrics via LM)", args.sample_mode)
            if args.sample_mode:
                args.sample_query = _prompt_with_default(
                    "Describe the music you want (for auto-generation)",
                    args.sample_query,
                    required=False,
                )
            if not args.sample_mode:
                caption = _prompt_with_default(
                    "Enter a music description (optional if you provide lyrics)",
                    args.caption,
                    required=False,
                )
                if caption:
                    args.caption = caption

        # Lyrics
        if args.task_type in {"text2music", "cover", "repaint", "lego", "complete"} and not args.sample_mode:
            print("\n--- Lyrics Options ---")
            print("1. Instrumental (no lyrics).")
            print("2. Generate lyrics automatically.")
            print("3. Provide path to a .txt file.")
            print("4. Paste lyrics directly.")

            if args.instrumental or args.lyrics == "[Instrumental]":
                default_choice = "1"
            elif args.use_cot_lyrics:
                default_choice = "2"
            elif args.lyrics and isinstance(args.lyrics, str) and os.path.isfile(args.lyrics):
                default_choice = "3"
            elif args.lyrics:
                default_choice = "4"
            else:
                default_choice = "1"
            choice = input(f"Your choice (1-4) [default: {default_choice}]: ").strip()
            if not choice:
                choice = default_choice

            if choice == "1":  # Instrumental
                args.instrumental = True
                args.lyrics = "[Instrumental]"
                args.use_cot_lyrics = False
                print("Instrumental music will be generated.")
            elif choice == "2":  # Generate lyrics automatically
                args.use_cot_lyrics = True
                args.lyrics = ""
                args.instrumental = False
                print("Lyrics will be generated automatically.")
            elif choice == "3":
                args.instrumental = False
                args.use_cot_lyrics = False
                default_lyrics_path = args.lyrics if isinstance(args.lyrics, str) and os.path.isfile(args.lyrics) else None
                while True:
                    lyrics_path = _prompt_existing_file("Please enter the path to your .txt lyrics file", default_lyrics_path)
                    if lyrics_path.endswith('.txt'):
                        args.lyrics = lyrics_path
                        print(f"Lyrics will be loaded from: {lyrics_path}")
                        break
                    print("Invalid file path or not a .txt file. Please try again.")
            elif choice == "4":
                args.instrumental = False
                args.use_cot_lyrics = False
                default_lyrics = args.lyrics if isinstance(args.lyrics, str) and args.lyrics and not os.path.isfile(args.lyrics) else None
                args.lyrics = _prompt_with_default("Paste lyrics (single line or use \\n)", default_lyrics, required=True)

            if not args.instrumental:
                lang = _prompt_with_default(
                    "Vocal language (e.g., 'en', 'zh', 'unknown')",
                    args.vocal_language,
                    required=False
                ).lower()
                if lang:
                    args.vocal_language = lang

            if args.use_cot_lyrics:
                if not args.caption:
                    args.caption = _prompt_non_empty("Enter a music description for lyric generation: ")
                if not args.thinking:
                    print("INFO: Automatic lyric generation requires the LM handler. Enabling LM 'thinking'.")
                    args.thinking = True

        args.batch_size = _prompt_int(
            "Number of outputs (audio clips) to generate",
            args.batch_size if args.batch_size is not None else 1,
            min_value=1,
        )

        advanced = input("\nConfigure advanced parameters? (y/n) [default: n]: ").lower()
        if advanced == 'y':
            if args.task_type == "text2music" and not args.sample_mode:
                args.use_format = _prompt_bool("Use format_sample to enhance caption/lyrics", args.use_format)
            print("\n--- Optional Metadata ---")
            args.duration = _prompt_float("Duration in seconds (10-600)", args.duration, min_value=10, max_value=600)
            args.bpm = _prompt_int("BPM (30-300, empty for auto)", args.bpm, min_value=30, max_value=300)
            args.keyscale = _prompt_with_default("Keyscale (e.g., 'C Major', empty for auto)", args.keyscale)
            args.timesignature = _prompt_with_default("Time signature (e.g., '4/4', empty for auto)", args.timesignature)
            args.vocal_language = _prompt_with_default("Vocal language (e.g., 'en', 'zh', 'unknown')", args.vocal_language)

            print("\n--- Advanced DiT Settings ---")
            args.seed = _prompt_int("Random seed (-1 for random)", args.seed)
            args.inference_steps = _prompt_int("Inference steps", args.inference_steps, min_value=1)
            if args.config_path and 'base' in args.config_path:
                args.guidance_scale = _prompt_float("Guidance scale (for base models)", args.guidance_scale)
                args.use_adg = _prompt_bool("Enable Adaptive Dual Guidance (ADG)", args.use_adg)
                args.cfg_interval_start = _prompt_float("CFG interval start (0.0-1.0)", args.cfg_interval_start, 0.0, 1.0)
                args.cfg_interval_end = _prompt_float("CFG interval end (0.0-1.0)", args.cfg_interval_end, 0.0, 1.0)
            args.shift = _prompt_float("Timestep shift (1.0-5.0)", args.shift, 1.0, 5.0)
            args.infer_method = _prompt_with_default("Inference method (ode/sde)", args.infer_method)
            timesteps_input = _prompt_with_default(
                "Custom timesteps list (e.g., [0.97, 0.5, 0])",
                args.timesteps,
                required=False,
            )
            if timesteps_input:
                args.timesteps = timesteps_input

            if args.task_type == "cover":
                args.audio_cover_strength = _prompt_float(
                    "Audio cover strength (0.0-1.0)", args.audio_cover_strength, 0.0, 1.0
                )

            print("\n--- Advanced LM Settings ---")
            args.thinking = _prompt_bool("Enable LM 'thinking'", args.thinking)
            args.lm_temperature = _prompt_float("LM temperature (0.0-2.0)", args.lm_temperature, 0.0, 2.0)
            args.lm_cfg_scale = _prompt_float("LM CFG scale", args.lm_cfg_scale)
            args.lm_top_k = _prompt_int("LM top-k (0 disables)", args.lm_top_k, min_value=0)
            args.lm_top_p = _prompt_float("LM top-p (0.0-1.0)", args.lm_top_p, 0.0, 1.0)
            args.lm_negative_prompt = _prompt_with_default("LM negative prompt", args.lm_negative_prompt)
            args.use_cot_metas = _prompt_bool("Use CoT for metadata", args.use_cot_metas)
            args.use_cot_caption = _prompt_bool("Use CoT for caption refinement", args.use_cot_caption)
            args.use_cot_lyrics = _prompt_bool("Use CoT for lyrics generation", args.use_cot_lyrics)
            args.use_cot_language = _prompt_bool("Use CoT for language detection", args.use_cot_language)
            args.use_constrained_decoding = _prompt_bool("Use constrained decoding", args.use_constrained_decoding)

            print("\n--- Output Settings ---")
            args.save_dir = _prompt_with_default("Save directory", args.save_dir)
            args.audio_format = _prompt_with_default("Audio format (mp3/wav/flac)", args.audio_format)
            # Batch size already captured above.
            args.use_random_seed = _prompt_bool("Use random seed per batch", args.use_random_seed)
            seeds_input = _prompt_with_default(
                "Custom seeds (comma/space separated, leave empty for random)",
                "",
                required=False,
            )
            if seeds_input:
                seeds = [s for s in seeds_input.replace(",", " ").split() if s.strip()]
                try:
                    args.seeds = [int(s) for s in seeds]
                except ValueError:
                    print("Invalid seeds input. Ignoring custom seeds.")
            args.allow_lm_batch = _prompt_bool("Allow LM batch processing", args.allow_lm_batch)
            args.lm_batch_chunk_size = _prompt_int("LM batch chunk size", args.lm_batch_chunk_size, min_value=1)
            args.constrained_decoding_debug = _prompt_bool("Constrained decoding debug", args.constrained_decoding_debug)
        else:
            if params_defaults and config_defaults:
                _apply_optional_defaults(args, params_defaults, config_defaults)

        # Ensure LM thinking is enabled when lyric generation is requested.
        if args.use_cot_lyrics and not args.thinking:
            print("INFO: Automatic lyric generation requires the LM handler. Enabling LM 'thinking'.")
            args.thinking = True

        print("\n--- Summary ---")
        print(f"Task: {args.task_type}")
        if args.caption:
            print(f"Description: {args.caption}")
        if args.task_type in {"lego", "extract", "complete"}:
            print(f"Instruction: {args.instruction}")
        if args.src_audio:
            print(f"Source audio: {args.src_audio}")
        print(f"Duration: {args.duration}s")
        print(f"Outputs: {args.batch_size}")
        if args.instrumental:
            print("Lyrics: Instrumental")
        elif args.use_cot_lyrics:
            print(f"Lyrics: Auto-generated ({args.vocal_language})")
        elif args.lyrics and os.path.isfile(args.lyrics):
             print(f"Lyrics: Provided from file ({args.lyrics})")
        elif args.lyrics:
             print(f"Lyrics: Provided as text")

        print("-" * 30)
        if not configure_only:
            confirm = input("Start generation with these settings? (y/n) [default: y]: ").lower()
            if confirm == 'n':
                print("Generation cancelled.")
                sys.exit(0)

        default_filename = default_config_path or "config.toml"
        config_filename = input(f"\nEnter filename to save configuration [{default_filename}]: ")
        if not config_filename:
            config_filename = default_filename
        if not config_filename.endswith(".toml"):
            config_filename += ".toml"

        try:
            config_to_save = {
                k: v for k, v in vars(args).items()
                if k not in ['config'] and not k.startswith('_')
            }
            with open(config_filename, 'w') as f:
                toml.dump(config_to_save, f)
            print(f"Configuration saved to {config_filename}")
            print(f"You can reuse it next time with: python cli.py -c {config_filename}")
        except Exception as e:
            print(f"Error saving configuration: {e}. Please try again.")

    except (KeyboardInterrupt, EOFError):
        print("\nWizard cancelled. Exiting.")
        sys.exit(0)

    return args, not configure_only


def main():
    """
    Main function to run ACE-Step music generation from the command line.
    """
    gpu_config = get_gpu_config()
    # Override tier thresholds in CLI without modifying gpu_config.py.
    # For MPS, use iogpu.wired_limit_mb as a proxy for memory when available.
    mem_gib = None
    if gpu_config.gpu_memory_gb > 0:
        mem_gib = gpu_config.gpu_memory_gb
    else:
        mps_available = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        if mps_available:
            wired_limit_mb = _get_mps_wired_limit_mb()
            if wired_limit_mb is not None and wired_limit_mb > 0:
                mem_gib = wired_limit_mb / 1024.0
    if mem_gib is not None and mem_gib > 0:
        if mem_gib <= 24:
            effective_tier = "tier1"
        elif mem_gib <= 32:
            effective_tier = "tier2"
        elif mem_gib <= 40:
            effective_tier = "tier3"
        elif mem_gib <= 48:
            effective_tier = "tier4"
        elif mem_gib <= 56:
            effective_tier = "tier5"
        elif mem_gib <= 64:
            effective_tier = "tier6"
        else:
            effective_tier = "unlimited"
        if effective_tier != gpu_config.tier:
            tier_config = GPU_TIER_CONFIGS[effective_tier]
            gpu_config = GPUConfig(
                tier=effective_tier,
                gpu_memory_gb=mem_gib,
                max_duration_with_lm=tier_config["max_duration_with_lm"],
                max_duration_without_lm=tier_config["max_duration_without_lm"],
                max_batch_size_with_lm=tier_config["max_batch_size_with_lm"],
                max_batch_size_without_lm=tier_config["max_batch_size_without_lm"],
                init_lm_default=tier_config["init_lm_default"],
                available_lm_models=tier_config["available_lm_models"],
                lm_memory_gb=tier_config["lm_memory_gb"],
            )
    set_global_gpu_config(gpu_config)

    auto_offload = gpu_config.gpu_memory_gb > 0 and gpu_config.gpu_memory_gb < 16
    print(f"\n{'='*60}")
    print("GPU Configuration Detected:")
    print(f"{'='*60}")
    print(f"  GPU Memory: {gpu_config.gpu_memory_gb:.2f} GiB")
    print(f"  Configuration Tier: {gpu_config.tier}")
    print(f"  Max Duration (with LM): {gpu_config.max_duration_with_lm}s ({gpu_config.max_duration_with_lm // 60} min)")
    print(f"  Max Duration (without LM): {gpu_config.max_duration_without_lm}s ({gpu_config.max_duration_without_lm // 60} min)")
    print(f"  Max Batch Size (with LM): {gpu_config.max_batch_size_with_lm}")
    print(f"  Max Batch Size (without LM): {gpu_config.max_batch_size_without_lm}")
    print(f"  Default LM Init: {gpu_config.init_lm_default}")
    print(f"  Available LM Models: {gpu_config.available_lm_models or 'None'}")
    mps_available = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    if mps_available and gpu_config.gpu_memory_gb <= 0:
        wired_limit_mb = _get_mps_wired_limit_mb()
        if wired_limit_mb is not None:
            print(f"  MPS Available: True (wired limit: {wired_limit_mb} MB)")
        else:
            print("  MPS Available: True (wired limit: unknown)")
        print("  Note: MPS memory is not reported here; tier may be inaccurate.")
    elif mps_available and gpu_config.gpu_memory_gb > 0:
        wired_limit_mb = _get_mps_wired_limit_mb()
        if wired_limit_mb is not None:
            print(f"  MPS Available: True (wired limit: {wired_limit_mb} MB)")
            print("  Note: Tiering uses MPS wired limit as a proxy for GPU memory.")
        else:
            print("  MPS Available: True (wired limit: unknown)")
            print("  Note: Tiering uses MPS wired limit when available.")
    print(f"{'='*60}\n")

    if auto_offload:
        print("Auto-enabling CPU offload (GPU < 16GB)")
    elif gpu_config.gpu_memory_gb > 0:
        print("CPU offload disabled by default (GPU >= 16GB)")
    elif mps_available:
        print("MPS detected, running on Apple GPU")
    else:
        print("No GPU detected, running on CPU")

    params_defaults = GenerationParams()
    config_defaults = GenerationConfig()

    parser = argparse.ArgumentParser(
        description="ACE-Step 1.5: Music generation (wizard/config only).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-c", "--config", type=str, help="Path to a TOML configuration file to load.")
    parser.add_argument("--configure", action="store_true", help="Run wizard to save configuration without generating.")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level for internal modules (TRACE/DEBUG/INFO/WARNING/ERROR/CRITICAL).",
    )
    cli_args = parser.parse_args()

    _configure_logging(level=cli_args.log_level)

    default_batch_size = 1 if not cli_args.config else config_defaults.batch_size
    defaults = {
        "project_root": _get_project_root(),
        "config_path": None,
        "checkpoint_dir": os.path.join(_get_project_root(), "checkpoints"),
        "lm_model_path": None,
        "backend": "vllm",
        "device": "auto",
        "use_flash_attention": None,
        "offload_to_cpu": auto_offload,
        "offload_dit_to_cpu": False,
        "save_dir": "output",
        "audio_format": config_defaults.audio_format,
        "caption": "",
        "prompt": "",
        "lyrics": None,
        "duration": params_defaults.duration,
        "instrumental": False,
        "bpm": params_defaults.bpm,
        "keyscale": params_defaults.keyscale,
        "timesignature": params_defaults.timesignature,
        "vocal_language": params_defaults.vocal_language,
        "task_type": params_defaults.task_type,
        "instruction": params_defaults.instruction,
        "reference_audio": params_defaults.reference_audio,
        "src_audio": params_defaults.src_audio,
        "repainting_start": params_defaults.repainting_start,
        "repainting_end": params_defaults.repainting_end,
        "audio_cover_strength": params_defaults.audio_cover_strength,
        "lego_track": "",
        "extract_track": "",
        "complete_tracks": "",
        "sample_mode": False,
        "sample_query": "",
        "use_format": False,
        "inference_steps": params_defaults.inference_steps,
        "seed": params_defaults.seed,
        "guidance_scale": params_defaults.guidance_scale,
        "use_adg": params_defaults.use_adg,
        "shift": 3.0,
        "infer_method": params_defaults.infer_method,
        "timesteps": None,
        "thinking": gpu_config.init_lm_default,
        "lm_temperature": params_defaults.lm_temperature,
        "lm_cfg_scale": params_defaults.lm_cfg_scale,
        "lm_top_k": params_defaults.lm_top_k,
        "lm_top_p": params_defaults.lm_top_p,
        "use_cot_metas": params_defaults.use_cot_metas,
        "use_cot_caption": params_defaults.use_cot_caption,
        "use_cot_lyrics": params_defaults.use_cot_lyrics,
        "use_cot_language": params_defaults.use_cot_language,
        "use_constrained_decoding": params_defaults.use_constrained_decoding,
        "batch_size": default_batch_size,
        "seeds": None,
        "use_random_seed": config_defaults.use_random_seed,
        "allow_lm_batch": config_defaults.allow_lm_batch,
        "lm_batch_chunk_size": config_defaults.lm_batch_chunk_size,
        "constrained_decoding_debug": config_defaults.constrained_decoding_debug,
        "audio_codes": "",
        "cfg_interval_start": params_defaults.cfg_interval_start,
        "cfg_interval_end": params_defaults.cfg_interval_end,
        "lm_negative_prompt": params_defaults.lm_negative_prompt,
        "log_level": cli_args.log_level,
    }

    args = argparse.Namespace(**defaults)
    args.config = None
    if cli_args.config:
        if not os.path.exists(cli_args.config):
            parser.error(f"Config file not found: {cli_args.config}")
        try:
            with open(cli_args.config, 'r') as f:
                config_from_file = toml.load(f)
            print(f"Configuration loaded from {cli_args.config}")
        except Exception as e:
            parser.error(f"Error loading TOML config file {cli_args.config}: {e}")
        for key, value in config_from_file.items():
            setattr(args, key, value)
        args.config = cli_args.config

    if cli_args.configure:
        args, _ = run_wizard(
            args,
            configure_only=True,
            default_config_path=cli_args.config,
            params_defaults=params_defaults,
            config_defaults=config_defaults,
        )
        print("Configuration complete. Exiting without generation.")
        sys.exit(0)

    if not cli_args.config:
        args, should_generate = run_wizard(
            args,
            configure_only=False,
            default_config_path=None,
            params_defaults=params_defaults,
            config_defaults=config_defaults,
        )
        if not should_generate:
            print("Configuration complete. Exiting without generation.")
            sys.exit(0)

    # --- Post-parsing Setup ---
    if args.use_cot_lyrics and not args.thinking:
        print("INFO: Automatic lyric generation requires the LM handler. Forcing --thinking=True.")
        args.thinking = True
    
    if not args.project_root:
        args.project_root = _get_project_root()
    else:
        args.project_root = os.path.abspath(os.path.expanduser(str(args.project_root)))

    if args.checkpoint_dir:
        args.checkpoint_dir = os.path.expanduser(str(args.checkpoint_dir))
        if not os.path.isabs(args.checkpoint_dir):
            args.checkpoint_dir = os.path.join(args.project_root, args.checkpoint_dir)

    if args.src_audio:
        args.src_audio = _expand_audio_path(args.src_audio)
    if args.reference_audio:
        args.reference_audio = _expand_audio_path(args.reference_audio)

    device = _resolve_device(args.device)

    # --- Argument Post-processing ---
    try:
        timesteps = _parse_timesteps_input(args.timesteps)
        if args.timesteps and timesteps is None:
            raise ValueError("Timesteps must be a list of numbers or a comma-separated string.")
    except ValueError as e:
        parser.error(f"Invalid format for timesteps. Expected a list of numbers (e.g., '[1.0, 0.5, 0.0]' or '0.97,0.5,0'). Error: {e}")

    if args.seeds:
        args.batch_size = len(args.seeds)
        args.use_random_seed = False
        args.seed = -1

    if args.instrumental and not args.lyrics:
        args.lyrics = "[Instrumental]"
    elif isinstance(args.lyrics, str) and args.lyrics.strip().lower() in {"[inst]", "[instrumental]"}:
        args.instrumental = True

    # --- Task-specific validation and instruction helpers ---
    if args.task_type in {"cover", "repaint", "lego", "extract", "complete"}:
        if not args.src_audio:
            parser.error(f"--src_audio is required for task_type '{args.task_type}'.")

    if args.task_type in {"cover", "repaint", "lego", "complete"}:
        if not args.caption:
            parser.error(f"--caption is required for task_type '{args.task_type}'.")

    if args.task_type == "text2music":
        if not args.caption and not args.lyrics:
            if not args.sample_mode and not args.sample_query:
                parser.error("--caption or --lyrics is required for text2music.")
        if args.use_cot_lyrics and not args.caption:
            parser.error("--use_cot_lyrics requires --caption for lyric generation.")
        if args.sample_mode or args.sample_query:
            args.sample_mode = True
    else:
        if args.sample_mode or args.sample_query:
            parser.error("--sample_mode/sample_query are only supported for task_type 'text2music'.")

    if args.sample_mode and args.use_cot_lyrics:
        print("INFO: sample_mode enabled. Disabling --use_cot_lyrics.")
        args.use_cot_lyrics = False

    # Auto-select instruction based on task_type if user didn't provide a custom instruction.
    # Align with api_server behavior and TASK_INSTRUCTIONS defaults.
    if args.instruction == DEFAULT_DIT_INSTRUCTION and args.task_type in TASK_INSTRUCTIONS:
        if args.task_type in {"text2music", "cover", "repaint"}:
            args.instruction = TASK_INSTRUCTIONS[args.task_type]

    # Base-model-only task enforcement
    base_only_tasks = {"lego", "extract", "complete"}
    if args.task_type in base_only_tasks and args.config_path:
        if "base" not in str(args.config_path).lower():
            parser.error(f"task_type '{args.task_type}' requires a base model config (e.g., 'acestep-v15-base').")

    if args.task_type == "repaint":
        if args.repainting_end != -1 and args.repainting_end <= args.repainting_start:
            parser.error("--repainting_end must be greater than --repainting_start (or -1).")

    if args.task_type in {"lego", "extract", "complete"}:
        has_custom_instruction = bool(args.instruction and args.instruction.strip() and args.instruction.strip() != params_defaults.instruction)
        if not has_custom_instruction:
            if args.task_type == "lego":
                if not args.lego_track:
                    parser.error("--instruction or --lego_track is required for lego task.")
                args.instruction = _default_instruction_for_task("lego", [args.lego_track.strip()])
            elif args.task_type == "extract":
                if not args.extract_track:
                    parser.error("--instruction or --extract_track is required for extract task.")
                args.instruction = _default_instruction_for_task("extract", [args.extract_track.strip()])
            elif args.task_type == "complete":
                if not args.complete_tracks:
                    parser.error("--instruction or --complete_tracks is required for complete task.")
                tracks = [t.strip() for t in args.complete_tracks.split(",") if t.strip()]
                if not tracks:
                    parser.error("--complete_tracks must contain at least one track.")
                args.instruction = _default_instruction_for_task("complete", tracks)
    
    # Handle lyrics argument
    lyrics_arg = args.lyrics
    if isinstance(lyrics_arg, str) and lyrics_arg:
        lyrics_arg = os.path.expanduser(lyrics_arg)
        if not os.path.isabs(lyrics_arg):
            # Resolve relative lyrics path against config file location first, then project_root.
            resolved = None
            if args.config:
                config_dir = os.path.dirname(os.path.abspath(args.config))
                candidate = os.path.join(config_dir, lyrics_arg)
                if os.path.isfile(candidate):
                    resolved = candidate
            if resolved is None and args.project_root:
                candidate = os.path.join(os.path.abspath(args.project_root), lyrics_arg)
                if os.path.isfile(candidate):
                    resolved = candidate
            if resolved is not None:
                lyrics_arg = resolved

    if lyrics_arg is not None:
        if lyrics_arg == "generate":
            args.use_cot_lyrics = True
            args.lyrics = ""
            print("Lyrics generation enabled.")
        elif os.path.isfile(lyrics_arg):
            print(f"INFO: Attempting to load lyrics from file: {lyrics_arg}")
            try:
                with open(lyrics_arg, 'r', encoding='utf-8') as f:
                    args.lyrics = f.read()
                print(f"Lyrics loaded from file: {lyrics_arg}")
            except Exception as e:
                parser.error(f"Could not read lyrics file {lyrics_arg}. Error: {e}")
        # else: lyrics is a string, use as is.

    # --- Handler Initialization ---
    if args.backend == "pyTorch":
        args.backend = "pt"

    print("Initializing ACE-Step handlers...")
    dit_handler = AceStepHandler()
    llm_handler = LLMHandler()

    base_only_tasks = {"lego", "extract", "complete"}
    skip_lm_tasks = {"cover", "repaint"}
    requires_lm = (
        args.task_type not in skip_lm_tasks and (
            args.thinking
            or args.sample_mode
            or bool(args.sample_query and str(args.sample_query).strip())
            or args.use_format
            or args.use_cot_metas
            or args.use_cot_caption
            or args.use_cot_lyrics
            or args.use_cot_language
        )
    )

    if args.config_path is None:
        available_models = dit_handler.get_available_acestep_v15_models()
        if args.task_type in base_only_tasks and available_models:
            available_models = [m for m in available_models if "base" in m.lower()]
        if not available_models:
            print("No DiT models found. Downloading main model (acestep-v15-turbo + core components)...")
            from acestep.model_downloader import ensure_main_model, get_checkpoints_dir
            checkpoints_dir = get_checkpoints_dir()
            success, msg = ensure_main_model(checkpoints_dir)
            print(msg)
            if not success:
                parser.error(f"Failed to download main model: {msg}")
            available_models = dit_handler.get_available_acestep_v15_models()
            if args.task_type in base_only_tasks and available_models:
                available_models = [m for m in available_models if "base" in m.lower()]
        if args.task_type in base_only_tasks and not available_models:
            print("Base-only task selected. Downloading base DiT model (acestep-v15-base)...")
            from acestep.model_downloader import ensure_dit_model, get_checkpoints_dir
            checkpoints_dir = get_checkpoints_dir()
            success, msg = ensure_dit_model("acestep-v15-base", checkpoints_dir)
            print(msg)
            if not success:
                parser.error(f"Failed to download base DiT model: {msg}")
            available_models = dit_handler.get_available_acestep_v15_models()
            if available_models:
                available_models = [m for m in available_models if "base" in m.lower()]
        if available_models:
            if args.task_type in {"lego", "extract", "complete"}:
                preferred = "acestep-v15-base"
            else:
                preferred = "acestep-v15-turbo"
            args.config_path = preferred if preferred in available_models else available_models[0]
            print(f"Auto-selected config_path: {args.config_path}")
        else:
            parser.error("No available DiT models found. Please specify --config_path.")
    if args.task_type in {"lego", "extract", "complete"} and "base" not in str(args.config_path).lower():
        parser.error(f"task_type '{args.task_type}' requires a base model config (e.g., 'acestep-v15-base').")

    # Ensure required DiT/main models are present for the selected task/model.
    from acestep.model_downloader import (
        ensure_main_model,
        ensure_dit_model,
        get_checkpoints_dir,
        check_main_model_exists,
        check_model_exists,
        SUBMODEL_REGISTRY,
    )
    checkpoints_dir = get_checkpoints_dir()
    if not check_main_model_exists(checkpoints_dir):
        print("Main model components not found. Downloading main model...")
        success, msg = ensure_main_model(checkpoints_dir)
        print(msg)
        if not success:
            parser.error(f"Failed to download main model: {msg}")
    if args.config_path:
        config_name = str(args.config_path)
        known_models = {"acestep-v15-turbo"} | set(SUBMODEL_REGISTRY.keys())
        if check_model_exists(config_name, checkpoints_dir):
            pass
        elif config_name in known_models:
            success, msg = ensure_dit_model(config_name, checkpoints_dir)
            if not success:
                parser.error(f"Failed to download DiT model '{config_name}': {msg}")
        else:
            print(f"Warning: DiT model '{config_name}' not found locally and not in registry. Skipping auto-download.")

    use_flash_attention = args.use_flash_attention
    if use_flash_attention is None:
        use_flash_attention = dit_handler.is_flash_attention_available()

    print(f"Initializing DiT handler with model: {args.config_path}")
    dit_handler.initialize_service(
        project_root=args.project_root,
        config_path=args.config_path,
        device=device,
        use_flash_attention=use_flash_attention,
        compile_model=False,
        offload_to_cpu=args.offload_to_cpu,
        offload_dit_to_cpu=args.offload_dit_to_cpu,
    )

    if requires_lm:
        from acestep.model_downloader import ensure_lm_model
        if args.lm_model_path is None:
            available_lm_models = llm_handler.get_available_5hz_lm_models()
            if available_lm_models:
                args.lm_model_path = available_lm_models[0]
                print(f"Using default LM model: {args.lm_model_path}")
            else:
                success, msg = ensure_lm_model(checkpoints_dir=checkpoints_dir)
                print(msg)
                if not success:
                    parser.error("No LM models available. Please specify --lm_model_path or disable --thinking.")
                available_lm_models = llm_handler.get_available_5hz_lm_models()
                if not available_lm_models:
                    parser.error("No LM models available after download. Please specify --lm_model_path or disable --thinking.")
                args.lm_model_path = available_lm_models[0]
                print(f"Using default LM model: {args.lm_model_path}")
        else:
            lm_model_path = str(args.lm_model_path)
            if os.path.isabs(lm_model_path) and os.path.exists(lm_model_path):
                pass
            elif check_model_exists(lm_model_path, checkpoints_dir):
                pass
            elif lm_model_path in SUBMODEL_REGISTRY:
                success, msg = ensure_lm_model(lm_model_path, checkpoints_dir=checkpoints_dir)
                print(msg)
                if not success:
                    parser.error(f"Failed to download LM model '{lm_model_path}': {msg}")
            else:
                parser.error(f"LM model '{lm_model_path}' not found locally and not in registry. Please provide a valid --lm_model_path.")

        print(f"Initializing LM handler with model: {args.lm_model_path}")
        llm_handler.initialize(
            checkpoint_dir=args.checkpoint_dir,
            lm_model_path=args.lm_model_path,
            backend=args.backend,
            device=device,
            offload_to_cpu=args.offload_to_cpu,
            dtype=dit_handler.dtype,
        )
    else:
        if args.task_type in skip_lm_tasks:
            print(f"LM is not required for task_type '{args.task_type}'. Skipping LM handler initialization.")
        else:
            print("LM 'thinking' is disabled. Skipping LM handler initialization.")

    print("Handlers initialized.")

    format_has_duration = False

    # --- Sample Mode / Description-based Auto-Generation ---
    if args.sample_mode or (args.sample_query and str(args.sample_query).strip()):
        if not llm_handler.llm_initialized:
            parser.error("--sample_mode/sample_query requires the LM handler, but it's not initialized.")

        sample_query = args.sample_query if args.sample_query and str(args.sample_query).strip() else "NO USER INPUT"
        parsed_language, parsed_instrumental = _parse_description_hints(sample_query)

        if args.vocal_language and args.vocal_language not in ("en", "unknown", ""):
            sample_language = args.vocal_language
        else:
            sample_language = parsed_language

        print("\nINFO: Creating sample via 'create_sample'...")
        sample_result = create_sample(
            llm_handler=llm_handler,
            query=sample_query,
            instrumental=parsed_instrumental,
            vocal_language=sample_language,
            temperature=args.lm_temperature,
            top_k=args.lm_top_k,
            top_p=args.lm_top_p,
        )

        if sample_result.success:
            args.caption = sample_result.caption
            args.lyrics = sample_result.lyrics
            args.instrumental = bool(sample_result.instrumental)
            if args.bpm is None:
                args.bpm = sample_result.bpm
            if not args.keyscale:
                args.keyscale = sample_result.keyscale
            if not args.timesignature:
                args.timesignature = sample_result.timesignature
            if args.duration <= 0:
                args.duration = sample_result.duration
            if args.vocal_language in ("unknown", "", None):
                args.vocal_language = sample_result.language
            args.sample_mode = True
            print("✓ Sample created. Using generated parameters.")
        else:
            parser.error(f"create_sample failed: {sample_result.error or sample_result.status_message}")

    # --- Format caption/lyrics if requested ---
    if args.use_format and (args.caption or args.lyrics):
        if not llm_handler.llm_initialized:
            parser.error("--use_format requires the LM handler, but it's not initialized.")

        user_metadata_for_format = {}
        if args.bpm is not None:
            user_metadata_for_format["bpm"] = args.bpm
        if args.duration is not None and float(args.duration) > 0:
            user_metadata_for_format["duration"] = float(args.duration)
        if args.keyscale:
            user_metadata_for_format["keyscale"] = args.keyscale
        if args.timesignature:
            user_metadata_for_format["timesignature"] = args.timesignature
        if args.vocal_language and args.vocal_language != "unknown":
            user_metadata_for_format["language"] = args.vocal_language

        print("\nINFO: Formatting caption/lyrics via 'format_sample'...")
        format_result = format_sample(
            llm_handler=llm_handler,
            caption=args.caption or "",
            lyrics=args.lyrics or "",
            user_metadata=user_metadata_for_format if user_metadata_for_format else None,
            temperature=args.lm_temperature,
            top_k=args.lm_top_k,
            top_p=args.lm_top_p,
        )

        if format_result.success:
            args.caption = format_result.caption or args.caption
            args.lyrics = format_result.lyrics or args.lyrics
            if format_result.duration:
                args.duration = format_result.duration
                format_has_duration = True
            if format_result.bpm:
                args.bpm = format_result.bpm
            if format_result.keyscale:
                args.keyscale = format_result.keyscale
            if format_result.timesignature:
                args.timesignature = format_result.timesignature
            print("✓ Format complete.")
        else:
            parser.error(f"format_sample failed: {format_result.error or format_result.status_message}")

    # --- Auto-generate Lyrics if Requested ---
    if args.use_cot_lyrics:
        if not llm_handler.llm_initialized:
             parser.error("--use_cot_lyrics requires the LM handler, but it's not initialized. Ensure --thinking is enabled.")

        print("\nINFO: Generating lyrics and metadata via 'create_sample'...")
        sample_result = create_sample(
            llm_handler=llm_handler,
            query=args.caption,
            instrumental=False,
            vocal_language=args.vocal_language if args.vocal_language != 'unknown' else None,
            temperature=args.lm_temperature,
            top_k=args.lm_top_k,
            top_p=args.lm_top_p,
        )

        if sample_result.success:
            print("✓ Automatic sample creation successful. Using generated parameters:")
            # Update args with values from create_sample, respecting user-provided values
            args.caption = sample_result.caption
            args.lyrics = sample_result.lyrics
            if args.bpm is None: args.bpm = sample_result.bpm
            if not args.keyscale: args.keyscale = sample_result.keyscale
            if not args.timesignature: args.timesignature = sample_result.timesignature
            if args.duration <= 0: args.duration = sample_result.duration
            if args.vocal_language == 'unknown': args.vocal_language = sample_result.language

            print(f"  - Caption: {args.caption}")
            lyrics_preview = args.lyrics[:150].strip().replace("\n", " ")
            print(f"  - Lyrics: '{lyrics_preview}...'")
            print(f"  - Metadata: BPM={args.bpm}, Key='{args.keyscale}', Lang='{args.vocal_language}'")

            # Disable subsequent CoT steps to avoid redundancy and save time
            args.use_cot_metas = False
            args.use_cot_caption = False
        else:
            print(f"⚠️ WARNING: Automatic lyric generation via 'create_sample' failed: {sample_result.error}")
            print("         Proceeding with an instrumental track instead.")
            args.lyrics = "[Instrumental]"
            args.instrumental = True

        # Flag has served its purpose, disable it to avoid issues with GenerationParams
        args.use_cot_lyrics = False

    if args.sample_mode or format_has_duration:
        args.use_cot_metas = False

    # --- Prompt Editing Hook for LLM Audio Tokens ---
    if args.thinking and args.task_type not in skip_lm_tasks:
        instruction_path = os.path.join(
            os.path.abspath(args.project_root) if args.project_root else os.getcwd(),
            "instruction.txt",
        )
        preloaded_prompt = None
        use_instruction_file = False
        if args.config and os.path.exists(instruction_path):
            use_instruction_file = True
            try:
                with open(instruction_path, "r", encoding="utf-8") as f:
                    preloaded_prompt = f.read()
            except Exception as e:
                print(f"WARNING: Failed to read {instruction_path}: {e}")
                preloaded_prompt = None
                use_instruction_file = False
        if use_instruction_file:
            print(f"INFO: Found {instruction_path}. Using it without editing.")
            if preloaded_prompt is not None and preloaded_prompt.strip():
                parsed_caption, parsed_lyrics = _extract_caption_lyrics_from_formatted_prompt(preloaded_prompt)
                parsed_instruction = _extract_instruction_from_formatted_prompt(preloaded_prompt)
                parsed_metas = _extract_cot_metadata_from_formatted_prompt(preloaded_prompt)
                if parsed_caption:
                    args.caption = parsed_caption
                if parsed_lyrics:
                    args.lyrics = parsed_lyrics
                if parsed_instruction:
                    args.instruction = parsed_instruction
                if parsed_metas:
                    bpm_value = parsed_metas.get("bpm")
                    if bpm_value:
                        parsed = _parse_number(bpm_value)
                        if parsed is not None:
                            args.bpm = int(parsed)
                    duration_value = parsed_metas.get("duration")
                    if duration_value:
                        parsed = _parse_number(duration_value)
                        if parsed is not None:
                            args.duration = float(parsed)
                    keyscale_value = parsed_metas.get("keyscale")
                    if keyscale_value:
                        args.keyscale = keyscale_value
                    timesignature_value = parsed_metas.get("timesignature")
                    if timesignature_value:
                        args.timesignature = timesignature_value
                    language_value = parsed_metas.get("language") or parsed_metas.get("vocal_language")
                    if language_value:
                        args.vocal_language = language_value
        elif preloaded_prompt is not None and not preloaded_prompt.strip():
            preloaded_prompt = None
        _install_prompt_edit_hook(llm_handler, instruction_path, preloaded_prompt=preloaded_prompt)

    # --- Configure Generation ---
    params = GenerationParams(
        task_type=args.task_type,
        instruction=args.instruction,
        reference_audio=args.reference_audio,
        src_audio=args.src_audio,
        audio_codes=args.audio_codes,
        caption=args.caption,
        lyrics=args.lyrics,
        instrumental=args.instrumental,
        vocal_language=args.vocal_language,
        bpm=args.bpm,
        keyscale=args.keyscale,
        timesignature=args.timesignature,
        duration=args.duration,
        inference_steps=args.inference_steps,
        seed=args.seed,
        guidance_scale=args.guidance_scale,
        use_adg=args.use_adg,
        cfg_interval_start=args.cfg_interval_start,
        cfg_interval_end=args.cfg_interval_end,
        shift=args.shift,
        infer_method=args.infer_method,
        timesteps=timesteps,
        repainting_start=args.repainting_start,
        repainting_end=args.repainting_end,
        audio_cover_strength=args.audio_cover_strength,
        thinking=args.thinking,
        lm_temperature=args.lm_temperature,
        lm_cfg_scale=args.lm_cfg_scale,
        lm_top_k=args.lm_top_k,
        lm_top_p=args.lm_top_p,
        lm_negative_prompt=args.lm_negative_prompt,
        use_cot_metas=args.use_cot_metas,
        use_cot_caption=args.use_cot_caption,
        use_cot_lyrics=args.use_cot_lyrics,
        use_cot_language=args.use_cot_language,
        use_constrained_decoding=args.use_constrained_decoding
    )

    config = GenerationConfig(
        batch_size=args.batch_size,
        allow_lm_batch=args.allow_lm_batch,
        use_random_seed=args.use_random_seed,
        seeds=args.seeds,
        lm_batch_chunk_size=args.lm_batch_chunk_size,
        constrained_decoding_debug=args.constrained_decoding_debug,
        audio_format=args.audio_format
    )

    # --- Generate Music ---
    log_level = getattr(args, "log_level", "INFO")
    log_level_upper = str(log_level).upper()
    compact_logs = log_level_upper != "DEBUG"
    _print_final_parameters(
        args,
        params,
        config,
        params_defaults,
        config_defaults,
        compact=compact_logs,
        resolved_device=device,
    )

    print("\n--- Starting Generation ---")
    print(f"Caption: \"{params.caption}\"")
    print(f"Duration: {params.duration}s | Outputs: {config.batch_size}")
    if config.seeds:
        print(f"Custom Seeds: {config.seeds}")
    print("---------------------------\n")

    manual_edit_pipeline = (
        args.thinking
        and args.task_type not in skip_lm_tasks
        and not (params.audio_codes and str(params.audio_codes).strip())
    )

    lm_time_costs = None
    if manual_edit_pipeline:
        top_k_value = None if not params.lm_top_k or params.lm_top_k == 0 else int(params.lm_top_k)
        top_p_value = None if not params.lm_top_p or params.lm_top_p >= 1.0 else params.lm_top_p

        actual_batch_size = config.batch_size if config.batch_size is not None else 1
        seed_for_generation = ""
        if config.seeds is not None:
            if isinstance(config.seeds, list) and len(config.seeds) > 0:
                seed_for_generation = ",".join(str(s) for s in config.seeds)
            elif isinstance(config.seeds, int):
                seed_for_generation = str(config.seeds)
        actual_seed_list, _ = dit_handler.prepare_seeds(actual_batch_size, seed_for_generation, config.use_random_seed)

        original_target_duration = params.duration
        original_bpm = params.bpm
        original_keyscale = params.keyscale
        original_timesignature = params.timesignature
        original_vocal_language = params.vocal_language
        lm_result = None
        lm_metadata = {}
        edited_caption = None
        edited_lyrics = None
        edited_instruction = None
        edited_metas = {}
        lm_time_costs = {
            "phase1_time": 0.0,
            "phase2_time": 0.0,
            "total_time": 0.0,
        }
        for attempt in range(2):
            user_metadata = {}
            if params.bpm is not None:
                try:
                    bpm_value = float(params.bpm)
                    if bpm_value > 0:
                        user_metadata["bpm"] = int(bpm_value)
                except (ValueError, TypeError):
                    pass
            if params.keyscale and params.keyscale.strip() and params.keyscale.strip().lower() not in ["n/a", ""]:
                user_metadata["keyscale"] = params.keyscale.strip()
            if params.timesignature and params.timesignature.strip() and params.timesignature.strip().lower() not in ["n/a", ""]:
                user_metadata["timesignature"] = params.timesignature.strip()
            if params.duration is not None:
                try:
                    duration_value = float(params.duration)
                    if duration_value > 0:
                        user_metadata["duration"] = int(duration_value)
                except (ValueError, TypeError):
                    pass
            user_metadata_to_pass = user_metadata if user_metadata else None

            lm_result = llm_handler.generate_with_stop_condition(
                caption=params.caption or "",
                lyrics=params.lyrics or "",
                infer_type="llm_dit",
                temperature=params.lm_temperature,
                cfg_scale=params.lm_cfg_scale,
                negative_prompt=params.lm_negative_prompt,
                top_k=top_k_value,
                top_p=top_p_value,
                target_duration=params.duration,
                user_metadata=user_metadata_to_pass,
                use_cot_caption=params.use_cot_caption,
                use_cot_language=params.use_cot_language,
                use_cot_metas=params.use_cot_metas,
                use_constrained_decoding=params.use_constrained_decoding,
                constrained_decoding_debug=config.constrained_decoding_debug,
                batch_size=actual_batch_size,
                seeds=actual_seed_list,
            )
            lm_extra_time = (lm_result.get("extra_outputs") or {}).get("time_costs", {})
            if lm_extra_time:
                lm_time_costs["phase1_time"] += float(lm_extra_time.get("phase1_time", 0.0) or 0.0)
                lm_time_costs["phase2_time"] += float(lm_extra_time.get("phase2_time", 0.0) or 0.0)
                lm_time_costs["total_time"] += float(
                    lm_extra_time.get(
                        "total_time",
                        (lm_extra_time.get("phase1_time", 0.0) or 0.0)
                        + (lm_extra_time.get("phase2_time", 0.0) or 0.0),
                    )
                    or 0.0
                )

            if not lm_result.get("success", False):
                error_msg = lm_result.get("error", "Unknown LM error")
                print(f"\n❌ Generation failed: {error_msg}")
                print(f"   Status: {lm_result.get('error', '')}")
                return

            if actual_batch_size > 1:
                lm_metadata = (lm_result.get("metadata") or [{}])[0]
                audio_codes = lm_result.get("audio_codes", [])
            else:
                lm_metadata = lm_result.get("metadata", {}) or {}
                audio_codes = lm_result.get("audio_codes", "")

            if audio_codes:
                params.audio_codes = audio_codes
            else:
                print("WARNING: LM did not return audio codes; proceeding without codes.")

            edited_caption = getattr(llm_handler, "_edited_caption", None)
            edited_lyrics = getattr(llm_handler, "_edited_lyrics", None)
            edited_instruction = getattr(llm_handler, "_edited_instruction", None)
            edited_metas = getattr(llm_handler, "_edited_metas", {})

            parsed_duration = None
            parsed_bpm = None
            parsed_keyscale = None
            parsed_timesignature = None
            parsed_language = None
            if edited_metas:
                bpm_value = edited_metas.get("bpm")
                if bpm_value:
                    parsed = _parse_number(bpm_value)
                    if parsed is not None and parsed > 0:
                        parsed_bpm = int(parsed)
                duration_value = edited_metas.get("duration")
                if duration_value:
                    parsed = _parse_number(duration_value)
                    if parsed is not None and parsed > 0:
                        parsed_duration = float(parsed)
                keyscale_value = edited_metas.get("keyscale")
                if keyscale_value:
                    parsed_keyscale = keyscale_value
                timesignature_value = edited_metas.get("timesignature")
                if timesignature_value:
                    parsed_timesignature = timesignature_value
                language_value = edited_metas.get("language") or edited_metas.get("vocal_language")
                if language_value:
                    parsed_language = language_value

            if attempt == 0:
                duration_changed = parsed_duration is not None and (
                    original_target_duration is None
                    or float(original_target_duration) <= 0
                    or abs(float(original_target_duration) - parsed_duration) > 1e-6
                )
                bpm_changed = parsed_bpm is not None and parsed_bpm != original_bpm
                keyscale_changed = parsed_keyscale is not None and parsed_keyscale != original_keyscale
                timesignature_changed = parsed_timesignature is not None and parsed_timesignature != original_timesignature
                language_changed = parsed_language is not None and parsed_language != original_vocal_language
                if duration_changed or bpm_changed or keyscale_changed or timesignature_changed or language_changed:
                    if duration_changed:
                        params.duration = parsed_duration
                    if bpm_changed:
                        params.bpm = parsed_bpm
                    if keyscale_changed:
                        params.keyscale = parsed_keyscale
                    if timesignature_changed:
                        params.timesignature = parsed_timesignature
                    if language_changed:
                        params.vocal_language = parsed_language
                    print("INFO: Edited metadata detected. Regenerating audio codes with updated values.")
                    llm_handler._skip_prompt_edit = True
                    continue
            break

        if edited_caption:
            params.caption = edited_caption
        elif params.use_cot_caption and lm_metadata.get("caption"):
            params.caption = lm_metadata.get("caption")
        if edited_lyrics:
            params.lyrics = edited_lyrics

        if edited_instruction:
            params.instruction = edited_instruction

        if edited_metas:
            bpm_value = edited_metas.get("bpm")
            if bpm_value:
                parsed = _parse_number(bpm_value)
                if parsed is not None:
                    params.bpm = int(parsed)
            duration_value = edited_metas.get("duration")
            if duration_value:
                parsed = _parse_number(duration_value)
                if parsed is not None:
                    params.duration = float(parsed)
            keyscale_value = edited_metas.get("keyscale")
            if keyscale_value:
                params.keyscale = keyscale_value
            timesignature_value = edited_metas.get("timesignature")
            if timesignature_value:
                params.timesignature = timesignature_value
            language_value = edited_metas.get("language") or edited_metas.get("vocal_language")
            if language_value:
                params.vocal_language = language_value
        else:
            if params.bpm is None and lm_metadata.get("bpm") not in (None, "N/A", ""):
                parsed = _parse_number(str(lm_metadata.get("bpm")))
                if parsed is not None:
                    params.bpm = int(parsed)
            if not params.keyscale and lm_metadata.get("keyscale"):
                params.keyscale = lm_metadata.get("keyscale")
            if not params.timesignature and lm_metadata.get("timesignature"):
                params.timesignature = lm_metadata.get("timesignature")
            if params.duration is None and lm_metadata.get("duration") not in (None, "N/A", ""):
                parsed = _parse_number(str(lm_metadata.get("duration")))
                if parsed is not None:
                    params.duration = float(parsed)
            if params.vocal_language in (None, "", "unknown"):
                language_value = lm_metadata.get("vocal_language") or lm_metadata.get("language")
                if language_value:
                    params.vocal_language = language_value

        params.thinking = False
        params.use_cot_caption = False
        params.use_cot_language = False
        params.use_cot_metas = False
        if hasattr(llm_handler, "_skip_prompt_edit"):
            llm_handler._skip_prompt_edit = False

        if log_level_upper in {"INFO", "DEBUG"}:
            _print_dit_prompt(dit_handler, params)
        print("Running DiT generation with edited prompt and cached audio codes...")
        result = generate_music(dit_handler, llm_handler, params, config, save_dir=args.save_dir)
    else:
        if log_level_upper in {"INFO", "DEBUG"}:
            _print_dit_prompt(dit_handler, params)
        result = generate_music(dit_handler, llm_handler, params, config, save_dir=args.save_dir)

    # --- Process Results ---
    if result.success:
        print(f"\n✅ Generation successful! {len(result.audios)} audio(s) saved in '{args.save_dir}/'")
        for i, audio in enumerate(result.audios):
            print(f"  [{i+1}] Path: {audio['path']} | Seed: {audio['params']['seed']}")
        
        time_costs = result.extra_outputs.get("time_costs", {})
        if manual_edit_pipeline and lm_time_costs and time_costs is not None:
            if not isinstance(time_costs, dict):
                time_costs = {}
                result.extra_outputs["time_costs"] = time_costs
            if lm_time_costs["total_time"] > 0.0:
                time_costs["lm_phase1_time"] = lm_time_costs["phase1_time"]
                time_costs["lm_phase2_time"] = lm_time_costs["phase2_time"]
                time_costs["lm_total_time"] = lm_time_costs["total_time"]
                dit_total = float(time_costs.get("dit_total_time_cost", 0.0) or 0.0)
                time_costs["pipeline_total_time"] = time_costs["lm_total_time"] + dit_total
        if time_costs:
            print("\n--- Performance ---")
            total_time = time_costs.get('pipeline_total_time', 0)
            print(f"Total time: {total_time:.2f}s")
            if args.thinking:
                lm1_time = time_costs.get('lm_phase1_time', 0)
                lm2_time = time_costs.get('lm_phase2_time', 0)
                print(f"  - LM time: {lm1_time + lm2_time:.2f}s")
            dit_time = time_costs.get('dit_total_time_cost', 0)
            print(f"  - DiT time: {dit_time:.2f}s")
            print("-------------------\n")

    else:
        print(f"\n❌ Generation failed: {result.error}")
        print(f"   Status: {result.status_message}")


if __name__ == "__main__":
    main()
