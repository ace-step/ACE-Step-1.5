"""Step-flow event wiring for the simplified UI."""

import gc
import os
import random
from typing import Any

import gradio as gr
import torch
from loguru import logger

from acestep.gpu_config import (
    find_best_lm_model_on_disk,
    get_global_gpu_config,
    resolve_lm_backend,
)
from acestep.inference import create_sample
from acestep.ui.gradio.interfaces.simple_ui import _step_indicator_html
from acestep.ui.gradio.events.results.batch_management_helpers import (
    _apply_param_defaults,
    _build_saved_params,
)
from acestep.ui.gradio.events.results.batch_queue import (
    store_batch_in_queue,
)
from acestep.ui.gradio.events.results.generation_progress import (
    generate_with_progress,
)
from acestep.ui.gradio.events.generation.validation import clamp_duration_to_gpu_limit
from acestep.ui.gradio.i18n import t

_RANDOM_STYLES = [
    "A happy pop song with piano and drums",
    "A chill lo-fi beat with smooth guitar",
    "An energetic rock anthem with electric guitar",
    "A jazzy piano ballad with saxophone",
    "A peaceful ambient track with soft pads",
    "An upbeat funk song with bass and horns",
    "A soulful R&B track with smooth vocals",
    "An acoustic folk song with gentle strumming",
    "A cinematic orchestral piece with strings",
    "A driving electronic dance track with synths",
    "A dreamy synthwave track with retro vibes",
    "A melancholic piano piece with strings",
    "An uplifting orchestral film score",
    "A groovy disco track with funky bass",
]


def _format_duration(seconds: float) -> str:
    """Format seconds to human-readable duration string."""
    if seconds <= 0:
        return ""
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"


def _build_metadata_html(duration: float, fmt: str) -> str:
    """Build an HTML metadata string for a result card."""
    dur = _format_duration(duration)
    parts = [p for p in [dur, fmt.upper()] if p]
    return f'<span class="simple-meta-text">{" · ".join(parts)}</span>' if parts else ""


def _build_status_html(message: str, is_success: bool) -> str:
    cls = "success" if is_success else "info"
    return (
        f'<div class="simple-gen-status {cls}">'
        f"  {message}"
        f"</div>"
    )


def _resolve_simple_lyrics(lyrics: str, instrumental: bool) -> str:
    """Return the generator lyrics value for the selected vocal mode."""
    return "[Instrumental]" if instrumental else (lyrics or "")


def _instrumental_lyrics_update(instrumental: bool) -> dict:
    """Disable manual lyrics while instrumental generation is selected."""
    return gr.update(interactive=not instrumental)


def _completion_message() -> str:
    """Return a translated completion message with an English fallback."""
    message = t("messages.generation_complete")
    return "Generation complete" if message == "messages.generation_complete" else message


def _ignore_progress(*args: Any, **kwargs: Any) -> None:
    """Suppress native Gradio progress when the Simple UI renders its own status."""


def _navigate_to(target: int, current_step: int) -> tuple:
    """Navigate to a step — returns visibility updates for each column.

    Args:
        target: Step number to navigate to (1-5).
        current_step: Previous step number (unused, for state tracking).

    Returns:
        Tuple of (step_number, indicator_html, col1_vis, col2_vis, col3_vis, col4_vis, col5_vis).
    """
    _ = current_step
    step_vis = [gr.update(visible=(i + 1 == target)) for i in range(5)]
    indicator = _step_indicator_html(target)
    return (target, gr.update(value=indicator), *step_vis)


def _go_random() -> tuple[str, str, str | None]:
    """Generate a random style. Returns style, lyrics, audio (unchanged)."""
    return random.choice(_RANDOM_STYLES)


def _init_llm_for_simple_ui(
    llm_handler: Any = None,
    dit_handler: Any = None,
) -> str:
    """Initialize DiT service and LLM in the background.

    Called when the Simple UI becomes active so models are ready
    by the time the user reaches the Create Music button.

    Args:
        llm_handler: LLM handler to initialize (optional).
        dit_handler: DiT handler to initialize (optional).

    Returns:
        Status message (empty string on success).
    """
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    )))
    gpu_config = get_global_gpu_config()

    # ── Initialize DiT service ──
    if dit_handler:
        try:
            available = dit_handler.get_available_acestep_v15_models()
            config_path = (
                "acestep-v15-xl-turbo"
                if "acestep-v15-xl-turbo" in available
                else ("acestep-v15-turbo" if "acestep-v15-turbo" in available
                      else (available[0] if available else "acestep-v15-turbo"))
            )
            dit_offload = gpu_config.offload_dit_to_cpu_default
            status, success = dit_handler.initialize_service(
                project_root=project_root,
                config_path=config_path,
                device="auto",
                use_flash_attention=False,
                compile_model=False,
                offload_to_cpu=gpu_config.offload_to_cpu_default,
                offload_dit_to_cpu=dit_offload,
                quantization=None,
                use_mlx_dit=True,
                vae_checkpoint=None,
            )
            if success:
                logger.info(f"Simple UI: DiT initialized ({config_path})")
            else:
                logger.warning(f"Simple UI DiT init failed: {status}")
                return status
        except Exception as e:
            logger.warning(f"Simple UI DiT auto-init error: {e}")
            return str(e)

    # ── Initialize LLM ──
    if not llm_handler or llm_handler.llm_initialized:
        return ""
    try:
        all_models = llm_handler.get_available_5hz_lm_models()
        lm_model = find_best_lm_model_on_disk(
            gpu_config.recommended_lm_model, all_models
        )
        backend = resolve_lm_backend(
            gpu_config.recommended_backend, gpu_config
        )
        checkpoint_dir = os.path.join(project_root, "checkpoints")
        if lm_model:
            status, success = llm_handler.initialize(
                checkpoint_dir=checkpoint_dir,
                lm_model_path=lm_model,
                backend=backend,
                device="auto",
                offload_to_cpu=gpu_config.offload_to_cpu_default,
            )
            if success:
                logger.info(f"Simple UI: LLM initialized ({lm_model}, {backend})")
                return ""
            logger.warning(f"Simple UI LLM init failed: {status}")
            return status
        logger.warning("Simple UI: no LM model found for auto-init")
        return "No LM model available"
    except Exception as e:
        logger.warning(f"Simple UI LLM auto-init error: {e}")
        return str(e)


def _start_generation() -> tuple:
    """Non-generator setup: navigate to step 4 (Creating...)."""
    return (
        gr.skip(),  # 0: audio_1
        gr.skip(),  # 1: audio_2
        gr.update(value=_step_indicator_html(4)),  # 2: step indicator
        gr.update(visible=False),  # 3: step 3 hidden
        gr.update(visible=True),  # 4: step 4 visible
        gr.update(visible=False),  # 5: step 5 hidden
        gr.update(value='<div class="simple-progress-status">Preparing...</div>'),  # 6: progress text
        gr.skip(),  # 7: gen info
        gr.skip(),  # 8: metadata 1
        gr.skip(),  # 9: metadata 2
        gr.skip(), gr.skip(), gr.skip(), gr.skip(),  # 10-13: batch state
    )


def _simple_generate_wrapper(
    dit_handler: Any,
    llm_handler: Any,
    song_style: str,
    lyrics: str,
    instrumental: bool,
    src_audio: str | None,
    current_batch_index: int,
    total_batches: int,
    batch_queue: dict,
    generation_params_state: dict,
):
    """Generate music and stream progress through steps 4 and 5."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Fallback: if background init didn't finish, initialize DiT + LLM now
    _init_llm_for_simple_ui(llm_handler, dit_handler)

    task_type = "cover" if src_audio else "text2music"
    captions = song_style or ""
    final_lyrics = _resolve_simple_lyrics(lyrics, instrumental)
    audio_duration_val = -1

    if song_style and not final_lyrics and llm_handler and llm_handler.llm_initialized:
        yield (
            gr.skip(),  # 0: audio_1
            gr.skip(),  # 1: audio_2
            gr.skip(),  # 2: step indicator
            gr.skip(),  # 3: step 3 (no change)
            gr.skip(),  # 4: step 4 (no change)
            gr.skip(),  # 5: step 5 (no change)
            gr.update(value='<div class="simple-progress-status">Generating lyrics...</div>'),  # 6
            gr.skip(), gr.skip(), gr.skip(),  # 7-9: gen_info, metadata_1, metadata_2
            gr.skip(), gr.skip(), gr.skip(), gr.skip(),  # 10-13: batch state
        )
        result = create_sample(
            llm_handler=llm_handler,
            query=song_style,
            instrumental=instrumental or ("instrumental" in song_style.lower()),
            vocal_language="unknown",
            temperature=0.85,
            top_k=0,
            top_p=0.9,
            use_constrained_decoding=True,
            constrained_decoding_debug=False,
        )
        if result.success:
            captions = result.caption or song_style
            final_lyrics = result.lyrics or ""
            clamped = clamp_duration_to_gpu_limit(result.duration, llm_handler)
            audio_duration_val = clamped if clamped and clamped > 0 else -1
        else:
            logger.warning(f"Sample creation failed: {result.status_message}")

    yield (
        gr.skip(),  # 0: audio_1
        gr.skip(),  # 1: audio_2
        gr.skip(),  # 2: step indicator
        gr.skip(),  # 3: step 3
        gr.skip(),  # 4: step 4
        gr.skip(),  # 5: step 5
        gr.update(value='<div class="simple-progress-status">Creating your music...</div>'),  # 6
        gr.skip(), gr.skip(), gr.skip(),  # 7-9: gen_info, metadata_1, metadata_2
        gr.skip(), gr.skip(), gr.skip(), gr.skip(),  # 10-13: batch state
    )

    params: dict[str, Any] = {}
    _apply_param_defaults(params)
    params.update({
        "captions": captions,
        "lyrics": final_lyrics,
        "src_audio": src_audio,
        "task_type": task_type,
        "audio_format": "flac",
        "mp3_bitrate": "128k",
        "mp3_sample_rate": 48000,
        "think_checkbox": True,
        "auto_score": False,
        "auto_lrc": False,
        "audio_duration": audio_duration_val,
        "batch_size_input": 2,
    })
    if src_audio:
        params["audio_cover_strength"] = 1.0

    # If LLM is not initialized, disable all LM-dependent features
    if not llm_handler or not llm_handler.llm_initialized:
        params["think_checkbox"] = False
        params["use_cot_metas"] = False
        params["use_cot_caption"] = False
        params["use_cot_language"] = False

    logger.info(
        f"Simple UI → generate_with_progress: "
        f"captions={params['captions'][:80]!r}, "
        f"lyrics={params['lyrics'][:80]!r}, "
        f"lm_negative_prompt={params['lm_negative_prompt']!r}, "
        f"think={params['think_checkbox']}, "
        f"task_type={params['task_type']}"
    )

    gen = generate_with_progress(
        dit_handler, llm_handler,
        params["captions"], params["lyrics"], params["bpm"],
        params["key_scale"], params["time_signature"], params["vocal_language"],
        params["inference_steps"], params["guidance_scale"],
        params["random_seed_checkbox"], params["seed"],
        params["reference_audio"], params["audio_duration"],
        params["batch_size_input"], params["src_audio"],
        params["text2music_audio_code_string"],
        params["repainting_start"], params["repainting_end"],
        params["instruction_display_gen"],
        params["audio_cover_strength"], params["cover_noise_strength"],
        params["task_type"],
        params["no_fsq"], params["use_adg"],
        params["cfg_interval_start"], params["cfg_interval_end"],
        params["shift"], params["infer_method"], params["sampler_mode"],
        params["velocity_norm_threshold"], params["velocity_ema_factor"],
        params["dcw_enabled"], params["dcw_mode"],
        params["dcw_scaler"], params["dcw_high_scaler"], params["dcw_wavelet"],
        params["custom_timesteps"],
        params["audio_format"], params["mp3_bitrate"], params["mp3_sample_rate"],
        params["lm_temperature"],
        params["think_checkbox"], params["lm_cfg_scale"],
        params["lm_top_k"], params["lm_top_p"], params["lm_negative_prompt"],
        params["use_cot_metas"], params["use_cot_caption"], params["use_cot_language"],
        False,  # is_format_caption
        params["constrained_decoding_debug"],
        params["allow_lm_batch"], params["auto_score"], params["auto_lrc"],
        params["score_scale"], params["lm_batch_chunk_size"],
        params["enable_normalization"], params["normalization_db"],
        params["fade_in_duration"], params["fade_out_duration"],
        params["latent_shift"], params["latent_rescale"],
        params["repaint_mode"], params["repaint_strength"],
        params["retake_variance"], params["retake_seed"],
        progress=_ignore_progress,
    )

    # Forward intermediate yields so Gradio 6 streams audio updates live
    final_result = None
    for partial in gen:
        final_result = partial
        yield (
            partial[0] if len(partial) > 0 else gr.skip(),   # 0: audio_1
            partial[1] if len(partial) > 1 else gr.skip(),   # 1: audio_2
            gr.skip(),                                         # 2: step indicator
            gr.skip(),                                         # 3: step 3
            gr.skip(),                                         # 4: step 4
            gr.skip(),                                         # 5: step 5
            gr.update(value='<div class="simple-progress-status">'
                     f'{partial[10] if len(partial) > 10 else "Creating..."}'
                     '</div>'),                                # 6: progress
            gr.skip(),                                         # 7: gen info
            gr.skip(),                                         # 8: metadata 1
            gr.skip(),                                         # 9: metadata 2
            gr.skip(), gr.skip(), gr.skip(), gr.skip(),        # 10-13: batch state
        )

    if final_result is None:
        yield (
            gr.update(value=None),  # 0: audio_1
            gr.update(value=None),  # 1: audio_2
            gr.update(value=_step_indicator_html(5)),  # 2
            gr.update(visible=False),  # 3: step 3 hide
            gr.update(visible=False),  # 4: step 4 hide
            gr.update(visible=True),  # 5: step 5 show
            gr.skip(),  # 6: progress
            gr.update(value=_build_status_html("Generation failed. Please try again.", False)),  # 7
            gr.skip(), gr.skip(),  # 8-9: metadata_1, metadata_2
            current_batch_index, total_batches, batch_queue, generation_params_state,  # 10-13
        )
        return

    all_audio_paths = final_result[8] if len(final_result) > 8 else None
    generation_info_text = final_result[9] if len(final_result) > 9 else ""
    gen_status_message = final_result[10] if len(final_result) > 10 else ""
    if all_audio_paths is None:
        err_msg = gen_status_message or generation_info_text or "Generation produced no output"
        logger.warning(f"Simple UI: generation result had no audio paths. Status: {gen_status_message}")
        yield (
            gr.update(value=None),  # 0: audio_1
            gr.update(value=None),  # 1: audio_2
            gr.update(value=_step_indicator_html(5)),  # 2
            gr.update(visible=False),  # 3: step 3 hide
            gr.update(visible=False),  # 4: step 4 hide
            gr.update(visible=True),  # 5: step 5 show
            gr.skip(),  # 6: progress
            gr.update(value=_build_status_html(str(err_msg), False)),  # 7
            gr.skip(), gr.skip(),  # 8-9: metadata_1, metadata_2
            current_batch_index, total_batches, batch_queue, generation_params_state,  # 10-13
        )
        return

    saved_params = _build_saved_params(
        params["captions"], params["lyrics"], params["bpm"],
        params["key_scale"], params["time_signature"], params["vocal_language"],
        params["inference_steps"], params["guidance_scale"],
        params["random_seed_checkbox"], params["seed"],
        params["reference_audio"], params["audio_duration"],
        params["batch_size_input"], params["src_audio"],
        params["text2music_audio_code_string"],
        params["repainting_start"], params["repainting_end"],
        params["instruction_display_gen"],
        params["audio_cover_strength"], params["cover_noise_strength"],
        params["task_type"],
        params["no_fsq"], params["use_adg"],
        params["cfg_interval_start"], params["cfg_interval_end"],
        params["shift"], params["infer_method"], params["sampler_mode"],
        params["velocity_norm_threshold"], params["velocity_ema_factor"],
        params["dcw_enabled"], params["dcw_mode"],
        params["dcw_scaler"], params["dcw_high_scaler"], params["dcw_wavelet"],
        params["audio_format"], params["mp3_bitrate"], params["mp3_sample_rate"],
        params["lm_temperature"],
        params["think_checkbox"], params["lm_cfg_scale"],
        params["lm_top_k"], params["lm_top_p"], params["lm_negative_prompt"],
        params["use_cot_metas"], params["use_cot_caption"], params["use_cot_language"],
        params["constrained_decoding_debug"], params["allow_lm_batch"],
        params["auto_score"], params["auto_lrc"],
        params["score_scale"], params["lm_batch_chunk_size"],
        params["track_name"], params["complete_track_classes"],
        params["enable_normalization"], params["normalization_db"],
        params["fade_in_duration"], params["fade_out_duration"],
        params["latent_shift"], params["latent_rescale"],
        repaint_mode=params["repaint_mode"],
        repaint_strength=params["repaint_strength"],
        retake_variance=params["retake_variance"],
        retake_seed=params["retake_seed"],
    )

    batch_queue = store_batch_in_queue(
        batch_queue, current_batch_index,
        all_audio_paths, generation_info_text,
        final_result[11] if len(final_result) > 11 else "",
        scores=[""] * 8,
        codes=[""] * 8,
        allow_lm_batch=False,
        batch_size=2,
        generation_params=saved_params,
        status="completed",
    )

    total_batches = max(total_batches, current_batch_index + 1)

    # all_audio_paths alternates [audio, json, audio, json, ...]
    # Use every-other index to skip JSON sidecar paths
    audio_paths_list = all_audio_paths if isinstance(all_audio_paths, list) else []
    audio_1 = audio_paths_list[0] if len(audio_paths_list) >= 1 else None
    audio_2 = audio_paths_list[2] if len(audio_paths_list) >= 3 else None

    meta_1 = _build_metadata_html(0, params["audio_format"])
    meta_2 = _build_metadata_html(0, params["audio_format"])

    gen_status = _build_status_html(_completion_message(), True)

    yield (
        gr.update(value=audio_1),  # 0
        gr.update(value=audio_2),  # 1
        gr.update(value=_step_indicator_html(5)),  # 2
        gr.update(visible=False),  # 3: step 3 hide
        gr.update(visible=False),  # 4: step 4 hide
        gr.update(visible=True),  # 5: step 5 show
        gr.skip(),  # 6: progress
        gr.update(value=gen_status),  # 7
        gr.update(value=meta_1),  # 8
        gr.update(value=meta_2),  # 9
        current_batch_index,  # 10
        total_batches,  # 11
        batch_queue,  # 12
        saved_params,  # 13
    )


def _save_audio_js() -> str:
    """Return JS for downloading audio."""
    return """(audio) => {
        if (!audio) return;
        let target = '';
        let filename = 'audio';
        if (typeof audio === 'object') {
            target = audio.url || audio.data || audio.path || audio.name || '';
            filename = audio.orig_name || audio.name || audio.path || filename;
        } else {
            target = audio;
            filename = audio;
        }
        if (!target) return;
        if (target.startsWith('/tmp/') || target.startsWith('/home/')) {
            target = '/gradio_api/file=' + encodeURI(target);
        }
        let a = document.createElement('a');
        a.href = target;
        a.download = filename.split(/[\\/]/).pop().split('?')[0] || 'audio';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }"""


def register_simple_ui_handlers(
    demo: Any,
    dit_handler: Any,
    llm_handler: Any,
    simple_section: dict[str, Any],
    results_section: dict[str, Any],
    advanced_column: Any = None,
    simple_mode_state: Any = None,
) -> None:
    """Register all event handlers for the stepped simple UI.

    Args:
        demo: Root Gradio demo.
        dit_handler: DiT handler.
        llm_handler: LLM handler.
        simple_section: Simple UI component map.
        results_section: Results section component map.
        advanced_column: Advanced column component (for mode switch).
        simple_mode_state: Mode state component (for mode switch).
    """
    gs = simple_section

    # ── Navigation outputs ──
    _nav_outputs = [
        gs["simple_state_current_step"],
        gs["simple_step_indicator"],
        gs["simple_step_1"],
        gs["simple_step_2"],
        gs["simple_step_3"],
        gs["simple_step_4"],
        gs["simple_step_5"],
    ]

    # ── Step 1 → Step 2 ──
    gs["simple_step1_continue_btn"].click(
        fn=lambda state: _navigate_to(2, state),
        inputs=[gs["simple_state_current_step"]],
        outputs=_nav_outputs,
    )

    # ── Step 2 Back ──
    gs["simple_step2_back_btn"].click(
        fn=lambda state: _navigate_to(1, state),
        inputs=[gs["simple_state_current_step"]],
        outputs=_nav_outputs,
    )

    # ── Step 2 → Step 3 ──
    gs["simple_step2_continue_btn"].click(
        fn=lambda state: _navigate_to(3, state),
        inputs=[gs["simple_state_current_step"]],
        outputs=_nav_outputs,
    )
    gs["simple_instrumental"].change(
        fn=_instrumental_lyrics_update,
        inputs=[gs["simple_instrumental"]],
        outputs=[gs["simple_lyrics"]],
    )

    # ── Step 3 Back ──
    gs["simple_step3_back_btn"].click(
        fn=lambda state: _navigate_to(2, state),
        inputs=[gs["simple_state_current_step"]],
        outputs=_nav_outputs,
    )

    # ── Hamburger toggle ──
    gs["simple_hamburger_btn"].click(
        fn=lambda state: (
            gr.update(visible=not state),
            not state,
        ),
        inputs=[gs["simple_hamburger_state"]],
        outputs=[gs["simple_hamburger_menu"], gs["simple_hamburger_state"]],
    )

    # ── About overlay ──
    gs["simple_about_btn"].click(
        fn=lambda: (
            gr.update(visible=False),   # close menu
            False,                       # menu state = closed
            gr.update(visible=True),     # show overlay
        ),
        inputs=[],
        outputs=[gs["simple_hamburger_menu"], gs["simple_hamburger_state"], gs["simple_about_overlay"]],
    )
    gs["simple_about_close_btn"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[gs["simple_about_overlay"]],
    )

    # ── Help (trigger hidden help button via JS) ──
    gs["simple_help_btn"].click(
        fn=lambda: (
            gr.update(visible=False),   # close menu
            False,
        ),
        inputs=[],
        outputs=[gs["simple_hamburger_menu"], gs["simple_hamburger_state"]],
        js="""() => {
            var btn = document.querySelector('.help-inline-btn');
            if (btn) btn.click();
        }""",
    )

    # ── Advanced Mode (from hamburger menu) ──
    if advanced_column is not None and simple_mode_state is not None:
        gs["simple_advanced_btn"].click(
            fn=lambda: (
                gr.update(visible=False),   # close menu
                False,                       # menu state = closed
                gr.update(visible=False),    # hide simple column
                gr.update(visible=True),     # show advanced column
                "Advanced",                  # state = Advanced
            ),
            inputs=[],
            outputs=[
                gs["simple_hamburger_menu"], gs["simple_hamburger_state"],
                gs["simple_column"], advanced_column, simple_mode_state,
            ],
        )

    # ── Random Style ──
    gs["simple_random_btn"].click(
        fn=_go_random,
        inputs=[],
        outputs=[gs["simple_song_style"]],
    )

    # ── Generate (Create Music) ──
    _gen_outputs = [
        gs["simple_generated_audio_1"],          # 0
        gs["simple_generated_audio_2"],          # 1
        gs["simple_step_indicator"],             # 2
        gs["simple_step_3"],                     # 3 — hide remix screen
        gs["simple_step_4"],                     # 4
        gs["simple_step_5"],                     # 5
        gs["simple_progress_text"],              # 6
        gs["simple_gen_info"],                   # 7
        gs.get("simple_metadata_1", gr.skip()),  # 8
        gs.get("simple_metadata_2", gr.skip()),  # 9
        results_section["current_batch_index"],   # 10
        results_section["total_batches"],         # 11
        results_section["batch_queue"],           # 12
        results_section["generation_params_state"], # 13
    ]

    _gen_shared_inputs = [
        gs["simple_song_style"],
        gs["simple_lyrics"],
        gs["simple_instrumental"],
        gs["simple_src_audio"],
        results_section["current_batch_index"],
        results_section["total_batches"],
        results_section["batch_queue"],
        results_section["generation_params_state"],
    ]

    # Generator must be a bare generator function (not wrapped in lambda)
    # so Gradio 6 can detect 'generator': True via introspection.
    def _gen_wrapper(style, lyrics, instrumental, src, bi, tb, bq, gps):
        yield from _simple_generate_wrapper(
            dit_handler, llm_handler, style, lyrics, instrumental, src, bi, tb, bq, gps,
        )

    gs["simple_create_btn"].click(
        fn=_start_generation,
        inputs=[],
        outputs=_gen_outputs,
        show_progress="hidden",
    ).then(
        fn=_gen_wrapper,
        inputs=_gen_shared_inputs,
        outputs=_gen_outputs,
        show_progress="hidden",
    )

    # ── Save Buttons ──
    _save_js = _save_audio_js()
    gs["simple_save_btn_1"].click(
        fn=None,
        inputs=[gs["simple_generated_audio_1"]],
        js=_save_js,
    )
    gs["simple_save_btn_2"].click(
        fn=None,
        inputs=[gs["simple_generated_audio_2"]],
        js=_save_js,
    )

    # ── Retry (Try Different Style) ──
    gs["simple_retry_btn"].click(
        fn=lambda style, lyrics, audio, state: _navigate_to(1, state),
        inputs=[
            gs["simple_song_style"], gs["simple_lyrics"],
            gs["simple_src_audio"], gs["simple_state_current_step"],
        ],
        outputs=_nav_outputs,
    )

    # ── New Song (reset all) ──
    _new_song_outputs = _nav_outputs + [
        gs["simple_song_style"],
        gs["simple_lyrics"],
        gs["simple_instrumental"],
        gs["simple_src_audio"],
        gs["simple_generated_audio_1"],
        gs["simple_generated_audio_2"],
        gs["simple_metadata_1"],
        gs["simple_metadata_2"],
        gs["simple_gen_info"],
    ]

    gs["simple_new_btn"].click(
        fn=lambda: (
            1,
            gr.update(value=_step_indicator_html(1)),
            gr.update(visible=True),        # step 1 show
            gr.update(visible=False),       # step 2 hide
            gr.update(visible=False),       # step 3 hide
            gr.update(visible=False),       # step 4 hide
            gr.update(visible=False),       # step 5 hide
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=False),
            gr.update(value=None),
            gr.update(value=None),
            gr.update(value=None),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
        ),
        inputs=[],
        outputs=_new_song_outputs,
    )
