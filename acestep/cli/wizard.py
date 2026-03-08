"""Interactive configuration wizard for ACE-Step CLI, extracted from cli.py."""

import os
import sys
from typing import Optional

import toml

from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig
from acestep.constants import DEFAULT_DIT_INSTRUCTION

from acestep.cli.prompts import (
    _prompt_non_empty,
    _prompt_with_default,
    _prompt_bool,
    _prompt_choice_from_list,
    _prompt_int,
    _prompt_float,
    _prompt_existing_file,
    _edit_formatted_prompt_via_file,
    _install_prompt_edit_hook,
)
from acestep.cli.parsers import (
    _parse_description_hints,
    _extract_caption_lyrics_from_formatted_prompt,
    _extract_instruction_from_formatted_prompt,
    _extract_cot_metadata_from_formatted_prompt,
    _parse_number,
    _parse_timesteps_input,
    _parse_bool,
    _expand_audio_path,
)


def run_wizard(args, configure_only: bool = False, default_config_path: Optional[str] = None,
               params_defaults: Optional[GenerationParams] = None,
               config_defaults: Optional[GenerationConfig] = None):
    """
    Runs an interactive wizard to set generation parameters.
    """
    # Lazy imports to avoid circular dependencies with the top-level cli module.
    from cli import (
        _default_instruction_for_task,
        _summarize_lyrics,
        _print_final_parameters,
        _build_meta_dict,
        _print_dit_prompt,
        TRACK_CHOICES,
        _apply_optional_defaults,
    )

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
            args.batch_size if args.batch_size is not None else 2,
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
