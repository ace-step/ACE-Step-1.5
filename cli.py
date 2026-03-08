import argparse
import os
import sys
import toml
from typing import List, Optional

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
from acestep.gpu_config import get_gpu_config, set_global_gpu_config, is_mps_platform, resolve_device
import torch

# Re-export prompt helpers, parsers, and wizard from cli subpackage
from acestep.cli.prompts import (  # noqa: F401
    _prompt_non_empty,
    _prompt_with_default,
    _prompt_bool,
    _prompt_choice_from_list,
    _prompt_int,
    _prompt_float,
    _prompt_existing_file,
    _expand_audio_path,
    _edit_formatted_prompt_via_file,
    _install_prompt_edit_hook,
)
from acestep.cli.parsers import (  # noqa: F401
    _parse_description_hints,
    _extract_caption_lyrics_from_formatted_prompt,
    _extract_instruction_from_formatted_prompt,
    _extract_cot_metadata_from_formatted_prompt,
    _parse_number,
    _parse_timesteps_input,
    _parse_bool,
)
from acestep.cli.wizard import run_wizard  # noqa: F401


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




def _resolve_device(device: str) -> str:
    return resolve_device(device)


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




def main():
    """
    Main function to run ACE-Step music generation from the command line.
    """

    gpu_config = get_gpu_config()
    set_global_gpu_config(gpu_config)
    mps_available = is_mps_platform()
    # Mac (Apple Silicon) uses unified memory — offloading provides no benefit
    auto_offload = (not mps_available) and gpu_config.gpu_memory_gb > 0 and gpu_config.gpu_memory_gb < 16
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
        "--backend",
        type=str,
        default=None,
        choices=["vllm", "pt", "mlx"],
        help="5Hz LM backend. Auto-detected if not specified: 'mlx' on Apple Silicon, 'vllm' on CUDA, 'pt' otherwise.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level for internal modules (TRACE/DEBUG/INFO/WARNING/ERROR/CRITICAL).",
    )
    cli_args = parser.parse_args()

    _configure_logging(level=cli_args.log_level)

    default_batch_size = 1 if not cli_args.config else config_defaults.batch_size

    # Auto-detect MLX on Apple Silicon, fall back to vllm
    if mps_available:
        try:
            import mlx.core  # noqa: F401
            default_backend = "mlx"
            print("Apple Silicon detected with MLX available. Using MLX backend.")
        except ImportError:
            default_backend = "vllm"
    else:
        default_backend = "vllm"

    defaults = {
        "project_root": _get_project_root(),
        "config_path": None,
        "checkpoint_dir": os.path.join(_get_project_root(), "checkpoints"),
        "lm_model_path": None,
        "backend": default_backend,
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

    # CLI --backend overrides config file and auto-detection
    if cli_args.backend is not None:
        args.backend = cli_args.backend

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
    if args.backend not in {"vllm", "pt", "mlx"}:
        args.backend = "vllm"

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
        use_flash_attention = dit_handler.is_flash_attention_available(device)

    compile_model = os.environ.get("ACESTEP_COMPILE_MODEL", "").strip().lower() in {
        "1", "true", "yes", "y", "on",
    }

    print(f"Initializing DiT handler with model: {args.config_path}")
    dit_handler.initialize_service(
        project_root=args.project_root,
        config_path=args.config_path,
        device=device,
        use_flash_attention=use_flash_attention,
        compile_model=compile_model,
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
            dtype=None,
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
        if preloaded_prompt is not None and not preloaded_prompt.strip():
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
            # Only include caption and language in user_metadata on
            # regeneration attempts.  On the first attempt the LM should
            # generate/expand these via CoT (matching inference.py behaviour).
            if attempt > 0:
                if params.caption and params.caption.strip():
                    user_metadata["caption"] = params.caption.strip()
                if params.vocal_language and params.vocal_language not in ("", "unknown"):
                    user_metadata["language"] = params.vocal_language
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
                    # Carry forward the expanded caption so the second
                    # attempt's <think> block (and user_metadata) use it
                    # instead of the short original caption.
                    edited_caption_for_regen = edited_metas.get("caption") if edited_metas else None
                    if edited_caption_for_regen and edited_caption_for_regen.strip():
                        params.caption = edited_caption_for_regen
                    print("INFO: Edited metadata detected. Regenerating audio codes with updated values.")
                    llm_handler._skip_prompt_edit = True
                    continue
            break

        edited_meta_caption = edited_metas.get("caption") if edited_metas else None
        if edited_meta_caption and edited_meta_caption.strip():
            params.caption = edited_meta_caption
        elif edited_caption:
            params.caption = edited_caption
        elif params.use_cot_caption and lm_metadata.get("caption"):
            params.caption = lm_metadata.get("caption")

        if edited_lyrics:
            params.lyrics = edited_lyrics
        elif not params.lyrics and lm_metadata.get("lyrics"):
            params.lyrics = lm_metadata.get("lyrics")

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

        # use_cot_language: override vocal_language with LM detection unless
        # the user explicitly edited the language in the think block.
        if params.use_cot_language:
            edited_lang = (edited_metas.get("language") or edited_metas.get("vocal_language")) if edited_metas else None
            if not edited_lang:
                lm_lang = lm_metadata.get("vocal_language") or lm_metadata.get("language")
                if lm_lang:
                    params.vocal_language = lm_lang

        # Populate cot_* fields for downstream reporting (mirrors inference.py)
        if lm_metadata:
            if original_bpm is None:
                params.cot_bpm = params.bpm
            if not original_keyscale:
                params.cot_keyscale = params.keyscale
            if not original_timesignature:
                params.cot_timesignature = params.timesignature
            if original_target_duration is None or float(original_target_duration) <= 0:
                params.cot_duration = params.duration
            if original_vocal_language in (None, "", "unknown"):
                params.cot_vocal_language = params.vocal_language
            if not params.caption:
                params.cot_caption = lm_metadata.get("caption", "")
            if not params.lyrics:
                params.cot_lyrics = lm_metadata.get("lyrics", "")

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
