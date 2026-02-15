"""
Gradio UI Generation Section Module
Contains generation section component definitions, split into:
- create_advanced_settings_section(): Top-level Settings accordion (includes Service Config as sub-accordion)
- create_generation_tab_section(): Generation tab content with mode-based UI
"""
import sys
import gradio as gr
from acestep.constants import (
    VALID_LANGUAGES,
    TRACK_NAMES,
    TASK_TYPES_TURBO,
    TASK_TYPES_BASE,
    DEFAULT_DIT_INSTRUCTION,
    GENERATION_MODES_TURBO,
    GENERATION_MODES_BASE,
    MODE_TO_TASK_TYPE,
)
from acestep.gradio_ui.i18n import t
from acestep.gradio_ui.help_content import create_help_button
from acestep.gradio_ui.events.generation_handlers import get_ui_control_config, _is_pure_base_model
from acestep.gpu_config import get_global_gpu_config, GPUConfig, find_best_lm_model_on_disk, get_gpu_device_name, GPU_TIER_LABELS, GPU_TIER_CHOICES


def _compute_init_defaults(dit_handler, llm_handler, init_params, language):
    """Compute common initialization defaults shared across section creators."""
    service_pre_initialized = init_params is not None and init_params.get('pre_initialized', False)
    service_mode = init_params is not None and init_params.get('service_mode', False)
    current_language = init_params.get('language', language) if init_params else language
    
    gpu_config: GPUConfig = init_params.get('gpu_config') if init_params else None
    if gpu_config is None:
        gpu_config = get_global_gpu_config()
    
    lm_initialized = init_params.get('init_llm', False) if init_params else False
    max_duration = gpu_config.max_duration_with_lm if lm_initialized else gpu_config.max_duration_without_lm
    max_batch_size = gpu_config.max_batch_size_with_lm if lm_initialized else gpu_config.max_batch_size_without_lm
    default_batch_size = min(2, max_batch_size)
    init_lm_default = gpu_config.init_lm_default
    
    default_offload = gpu_config.offload_to_cpu_default
    default_offload_dit = gpu_config.offload_dit_to_cpu_default
    try:
        import torch
        if hasattr(torch, 'xpu') and torch.xpu.is_available():
            default_offload = False
            default_offload_dit = False
    except ImportError:
        pass
    
    default_quantization = gpu_config.quantization_default
    default_compile = gpu_config.compile_model_default
    if sys.platform == "darwin":
        default_quantization = False
        default_compile = False
    
    if gpu_config.lm_backend_restriction == "pt_mlx_only":
        available_backends = ["pt", "mlx"]
    else:
        available_backends = ["vllm", "pt", "mlx"]
    recommended_backend = gpu_config.recommended_backend
    if recommended_backend not in available_backends:
        recommended_backend = available_backends[0]
    
    recommended_lm = gpu_config.recommended_lm_model
    
    return {
        "service_pre_initialized": service_pre_initialized,
        "service_mode": service_mode,
        "current_language": current_language,
        "gpu_config": gpu_config,
        "lm_initialized": lm_initialized,
        "max_duration": max_duration,
        "max_batch_size": max_batch_size,
        "default_batch_size": default_batch_size,
        "init_lm_default": init_lm_default,
        "default_offload": default_offload,
        "default_offload_dit": default_offload_dit,
        "default_quantization": default_quantization,
        "default_compile": default_compile,
        "available_backends": available_backends,
        "recommended_backend": recommended_backend,
        "recommended_lm": recommended_lm,
    }


# ============================================================================
# Service Configuration Section — now created inside Settings accordion
# ============================================================================

def _create_service_config_content(dit_handler, llm_handler, defaults, init_params):
    """Create service configuration components inside the Settings accordion.

    Returns a dict of service-related components.
    """
    service_pre_initialized = defaults["service_pre_initialized"]
    service_mode = defaults["service_mode"]
    current_language = defaults["current_language"]
    gpu_config = defaults["gpu_config"]
    init_lm_default = defaults["init_lm_default"]
    default_offload = defaults["default_offload"]
    default_offload_dit = defaults["default_offload_dit"]
    default_quantization = defaults["default_quantization"]
    default_compile = defaults["default_compile"]
    available_backends = defaults["available_backends"]
    recommended_backend = defaults["recommended_backend"]
    recommended_lm = defaults["recommended_lm"]

    accordion_open = not service_pre_initialized
    accordion_visible = not service_mode

    with gr.Accordion(t("service.title"), open=accordion_open, visible=accordion_visible, elem_classes=["has-info-container"]) as service_config_accordion:
        create_help_button("service_config")
        # Language selector
        with gr.Row():
            language_dropdown = gr.Dropdown(
                choices=[("English", "en"), ("中文", "zh"), ("日本語", "ja")],
                value=current_language,
                label=t("service.language_label"),
                info=t("service.language_info"), elem_classes=["has-info-container"],
                scale=1,
            )

        # GPU info display and tier override
        _gpu_device_name = get_gpu_device_name()
        _gpu_info_text = f"🖥️ **{_gpu_device_name}** — {gpu_config.gpu_memory_gb:.1f} GB VRAM — {t('service.gpu_auto_tier')}: **{GPU_TIER_LABELS.get(gpu_config.tier, gpu_config.tier)}**"
        with gr.Row():
            gpu_info_display = gr.Markdown(value=_gpu_info_text)
        with gr.Row():
            tier_dropdown = gr.Dropdown(
                choices=[(label, key) for key, label in GPU_TIER_LABELS.items()],
                value=gpu_config.tier,
                label=t("service.tier_label"),
                info=t("service.tier_info"), elem_classes=["has-info-container"],
                scale=1,
            )

        # Checkpoint
        with gr.Row(equal_height=True):
            with gr.Column(scale=4):
                checkpoint_value = init_params.get('checkpoint') if service_pre_initialized else None
                checkpoint_dropdown = gr.Dropdown(
                    label=t("service.checkpoint_label"),
                    choices=dit_handler.get_available_checkpoints(),
                    value=checkpoint_value,
                    info=t("service.checkpoint_info"), elem_classes=["has-info-container"],
                )
            with gr.Column(scale=1, min_width=90):
                refresh_btn = gr.Button(t("service.refresh_btn"), size="sm")

        # Model and device
        with gr.Row():
            available_models = dit_handler.get_available_acestep_v15_models()
            default_model = "acestep-v15-turbo" if "acestep-v15-turbo" in available_models else (available_models[0] if available_models else None)
            config_path_value = init_params.get('config_path', default_model) if service_pre_initialized else default_model
            config_path = gr.Dropdown(
                label=t("service.model_path_label"),
                choices=available_models,
                value=config_path_value,
                info=t("service.model_path_info"), elem_classes=["has-info-container"],
            )
            device_value = init_params.get('device', 'auto') if service_pre_initialized else 'auto'
            device = gr.Dropdown(
                choices=["auto", "cuda", "mps", "xpu", "cpu"],
                value=device_value,
                label=t("service.device_label"),
                info=t("service.device_info"), elem_classes=["has-info-container"],
            )

        # LM model and backend
        with gr.Row():
            all_lm_models = llm_handler.get_available_5hz_lm_models()
            # Show all available LM models (no filtering by tier);
            # tier only influences the default/recommended selection.
            default_lm_model = find_best_lm_model_on_disk(recommended_lm, all_lm_models)
            lm_model_path_value = init_params.get('lm_model_path', default_lm_model) if service_pre_initialized else default_lm_model
            lm_model_path = gr.Dropdown(
                label=t("service.lm_model_path_label"),
                choices=all_lm_models,
                value=lm_model_path_value,
                info=t("service.lm_model_path_info") + (f" (Recommended: {recommended_lm})" if recommended_lm else " (LM not available for this GPU tier)"), elem_classes=["has-info-container"],
            )
            backend_value = init_params.get('backend', recommended_backend) if service_pre_initialized else recommended_backend
            backend_dropdown = gr.Dropdown(
                choices=available_backends,
                value=backend_value,
                label=t("service.backend_label"),
                info=t("service.backend_info") + (f" (vllm unavailable for {gpu_config.tier}: VRAM too low)" if gpu_config.lm_backend_restriction == "pt_mlx_only" else ""), elem_classes=["has-info-container"],
            )

        # Checkboxes
        with gr.Row():
            init_llm_value = init_params.get('init_llm', init_lm_default) if service_pre_initialized else init_lm_default
            lm_info_text = t("service.init_llm_info")
            if not gpu_config.available_lm_models:
                lm_info_text += " ⚠️ LM not available for this GPU tier (VRAM too low)"
            init_llm_checkbox = gr.Checkbox(label=t("service.init_llm_label"), value=init_llm_value, info=lm_info_text)

            flash_attn_available = dit_handler.is_flash_attention_available(device_value)
            use_flash_attention_value = init_params.get('use_flash_attention', flash_attn_available) if service_pre_initialized else flash_attn_available
            use_flash_attention_checkbox = gr.Checkbox(
                label=t("service.flash_attention_label"),
                value=use_flash_attention_value,
                interactive=flash_attn_available,
                info=t("service.flash_attention_info_enabled") if flash_attn_available else t("service.flash_attention_info_disabled"), elem_classes=["has-info-container"],
            )

            offload_to_cpu_value = init_params.get('offload_to_cpu', default_offload) if service_pre_initialized else default_offload
            offload_to_cpu_checkbox = gr.Checkbox(
                label=t("service.offload_cpu_label"),
                value=offload_to_cpu_value,
                info=t("service.offload_cpu_info") + (" (recommended for this tier)" if default_offload else " (optional for this tier)"), elem_classes=["has-info-container"],
            )

            offload_dit_to_cpu_value = init_params.get('offload_dit_to_cpu', default_offload_dit) if service_pre_initialized else default_offload_dit
            offload_dit_to_cpu_checkbox = gr.Checkbox(
                label=t("service.offload_dit_cpu_label"),
                value=offload_dit_to_cpu_value,
                info=t("service.offload_dit_cpu_info") + (" (recommended for this tier)" if default_offload_dit else " (optional for this tier)"), elem_classes=["has-info-container"],
            )

            compile_model_value = init_params.get('compile_model', default_compile) if service_pre_initialized else default_compile
            compile_model_checkbox = gr.Checkbox(label=t("service.compile_model_label"), value=compile_model_value, info=t("service.compile_model_info"), elem_classes=["has-info-container"])

            quantization_value = init_params.get('quantization', default_quantization) if service_pre_initialized else default_quantization
            quantization_checkbox = gr.Checkbox(
                label=t("service.quantization_label"),
                value=quantization_value,
                info=t("service.quantization_info") + (" (recommended for this tier)" if default_quantization else " (optional for this tier)"), elem_classes=["has-info-container"],
            )

            from acestep.mlx_dit import mlx_available as _mlx_avail
            _mlx_ok = _mlx_avail()
            mlx_dit_value = init_params.get('mlx_dit', _mlx_ok) if service_pre_initialized else _mlx_ok
            mlx_dit_checkbox = gr.Checkbox(
                label=t("service.mlx_dit_label"),
                value=mlx_dit_value,
                interactive=_mlx_ok,
                info=t("service.mlx_dit_info_enabled") if _mlx_ok else t("service.mlx_dit_info_disabled"), elem_classes=["has-info-container"],
            )

        init_btn = gr.Button(t("service.init_btn"), variant="primary", size="lg")
        init_status_value = init_params.get('init_status', '') if service_pre_initialized else ''
        init_status = gr.Textbox(label=t("service.status_label"), interactive=False, lines=3, value=init_status_value)

    return {
        "service_config_accordion": service_config_accordion,
        "language_dropdown": language_dropdown,
        "checkpoint_dropdown": checkpoint_dropdown,
        "refresh_btn": refresh_btn,
        "config_path": config_path,
        "device": device,
        "init_btn": init_btn,
        "init_status": init_status,
        "lm_model_path": lm_model_path,
        "init_llm_checkbox": init_llm_checkbox,
        "backend_dropdown": backend_dropdown,
        "use_flash_attention_checkbox": use_flash_attention_checkbox,
        "offload_to_cpu_checkbox": offload_to_cpu_checkbox,
        "offload_dit_to_cpu_checkbox": offload_dit_to_cpu_checkbox,
        "compile_model_checkbox": compile_model_checkbox,
        "quantization_checkbox": quantization_checkbox,
        "mlx_dit_checkbox": mlx_dit_checkbox,
        "gpu_info_display": gpu_info_display,
        "tier_dropdown": tier_dropdown,
        "gpu_config": gpu_config,
    }


def create_service_config_section(dit_handler, llm_handler, init_params=None, language='en') -> dict:
    """DEPRECATED: Service config is now inside Settings accordion.

    This wrapper is kept for backward compatibility — it creates a standalone
    accordion that will be hidden since the real one lives inside Settings.
    """
    defaults = _compute_init_defaults(dit_handler, llm_handler, init_params, language)
    return _create_service_config_content(dit_handler, llm_handler, defaults, init_params)


# ============================================================================
# Settings Section (top-level accordion, collapsed by default)
# Contains: Service Configuration (sub-accordion) + Advanced Settings
# ============================================================================

def create_advanced_settings_section(dit_handler, llm_handler, init_params=None, language='en') -> dict:
    """Create the unified Settings accordion (top-level, collapsed by default).

    Contains Service Configuration as a sub-accordion, plus all advanced
    generation settings (DiT, LM, output, automation).
    """
    defaults = _compute_init_defaults(dit_handler, llm_handler, init_params, language)
    service_pre_initialized = defaults["service_pre_initialized"]
    service_mode = defaults["service_mode"]

    if service_pre_initialized and 'dit_handler' in init_params:
        _cfg_path = init_params.get('config_path', '')
        _ui_config = get_ui_control_config(
            init_params['dit_handler'].is_turbo_model(),
            is_pure_base=_is_pure_base_model((_cfg_path or "").lower()),
        )
    else:
        _ui_config = get_ui_control_config(True)

    # Auto-expand Settings when service is not yet initialized so users can init
    settings_open = not service_pre_initialized
    with gr.Accordion(t("generation.advanced_settings"), open=settings_open) as advanced_settings_accordion:

        # ═══════════════════════════════════════════
        # Service Configuration (sub-accordion)
        # ═══════════════════════════════════════════
        service_components = _create_service_config_content(
            dit_handler, llm_handler, defaults, init_params
        )

        # ═══════════════════════════════════════════
        # LoRA Adapter (sub-accordion, collapsed)
        # ═══════════════════════════════════════════
        with gr.Accordion("🔧 LoRA Adapter", open=False, elem_classes=["has-info-container"]):
            with gr.Row():
                lora_path = gr.Textbox(label="LoRA Path", placeholder="./lora_output/final/adapter", info="Path to trained LoRA adapter directory", scale=3)
                load_lora_btn = gr.Button("📥 Load LoRA", variant="secondary", scale=1)
                unload_lora_btn = gr.Button("🗑️ Unload", variant="secondary", scale=1)
            with gr.Row():
                use_lora_checkbox = gr.Checkbox(label="Use LoRA", value=False, info="Enable LoRA adapter for inference", scale=1)
                lora_scale_slider = gr.Slider(minimum=0.0, maximum=1.0, value=1.0, step=0.05, label="LoRA Scale", info="LoRA influence strength (0=disabled, 1=full)", scale=2)
                lora_status = gr.Textbox(label="LoRA Status", value="No LoRA loaded", interactive=False, scale=2)

        # ═══════════════════════════════════════════
        # DiT Diffusion Parameters (with help button)
        # ═══════════════════════════════════════════
        with gr.Accordion(t("generation.advanced_dit_section"), open=True, elem_classes=["has-info-container"]):
            create_help_button("generation_advanced")
            with gr.Row():
                inference_steps = gr.Slider(
                    minimum=_ui_config["inference_steps_minimum"],
                    maximum=_ui_config["inference_steps_maximum"],
                    value=_ui_config["inference_steps_value"],
                    step=1,
                    label=t("generation.inference_steps_label"),
                    info=t("generation.inference_steps_info"), elem_classes=["has-info-container"],
                )
                guidance_scale = gr.Slider(
                    minimum=1.0, maximum=15.0, value=7.0, step=0.1,
                    label=t("generation.guidance_scale_label"),
                    info=t("generation.guidance_scale_info"), elem_classes=["has-info-container"],
                    visible=_ui_config["guidance_scale_visible"],
                )
                infer_method = gr.Dropdown(
                    choices=["ode", "sde"], value="ode",
                    label=t("generation.infer_method_label"),
                    info=t("generation.infer_method_info"), elem_classes=["has-info-container"],
                )
            with gr.Row():
                use_adg = gr.Checkbox(
                    label=t("generation.use_adg_label"), value=False,
                    info=t("generation.use_adg_info"), elem_classes=["has-info-container"],
                    visible=_ui_config["use_adg_visible"],
                )
                shift = gr.Slider(
                    minimum=1.0, maximum=5.0, value=_ui_config["shift_value"], step=0.1,
                    label=t("generation.shift_label"),
                    info=t("generation.shift_info"), elem_classes=["has-info-container"],
                    visible=_ui_config["shift_visible"],
                )
            with gr.Row():
                custom_timesteps = gr.Textbox(
                    label=t("generation.custom_timesteps_label"),
                    placeholder="0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0",
                    value="",
                    info=t("generation.custom_timesteps_info"), elem_classes=["has-info-container"],
                )
            with gr.Row():
                cfg_interval_start = gr.Slider(
                    minimum=0.0, maximum=1.0, value=0.0, step=0.01,
                    label=t("generation.cfg_interval_start"),
                    visible=_ui_config["cfg_interval_start_visible"],
                )
                cfg_interval_end = gr.Slider(
                    minimum=0.0, maximum=1.0, value=1.0, step=0.01,
                    label=t("generation.cfg_interval_end"),
                    visible=_ui_config["cfg_interval_end_visible"],
                )
            with gr.Row():
                with gr.Column():
                    seed = gr.Textbox(label=t("generation.seed_label"), value="-1", info=t("generation.seed_info"), elem_classes=["has-info-container"])
                    random_seed_checkbox = gr.Checkbox(label=t("generation.random_seed_label"), value=True, info=t("generation.random_seed_info"), elem_classes=["has-info-container"])

        # ═══════════════════════════════════════════
        # LM Generation Parameters
        # ═══════════════════════════════════════════
        with gr.Accordion(t("generation.advanced_lm_section"), open=False, elem_classes=["has-info-container"]):
            with gr.Row():
                lm_temperature = gr.Slider(label=t("generation.lm_temperature_label"), minimum=0.0, maximum=2.0, value=0.85, step=0.1, scale=1, info=t("generation.lm_temperature_info"), elem_classes=["has-info-container"])
                lm_cfg_scale = gr.Slider(label=t("generation.lm_cfg_scale_label"), minimum=1.0, maximum=3.0, value=2.0, step=0.1, scale=1, info=t("generation.lm_cfg_scale_info"), elem_classes=["has-info-container"])
            with gr.Row():
                lm_top_k = gr.Slider(label=t("generation.lm_top_k_label"), minimum=0, maximum=100, value=0, step=1, scale=1, info=t("generation.lm_top_k_info"), elem_classes=["has-info-container"])
                lm_top_p = gr.Slider(label=t("generation.lm_top_p_label"), minimum=0.0, maximum=1.0, value=0.9, step=0.01, scale=1, info=t("generation.lm_top_p_info"), elem_classes=["has-info-container"])
            with gr.Row():
                lm_negative_prompt = gr.Textbox(
                    label=t("generation.lm_negative_prompt_label"),
                    value="NO USER INPUT",
                    placeholder=t("generation.lm_negative_prompt_placeholder"),
                    info=t("generation.lm_negative_prompt_info"), elem_classes=["has-info-container"],
                    lines=2,
                )
            with gr.Row():
                use_cot_metas = gr.Checkbox(label=t("generation.cot_metas_label"), value=True, info=t("generation.cot_metas_info"), scale=1, elem_classes=["has-info-container"])
                use_cot_language = gr.Checkbox(label=t("generation.cot_language_label"), value=True, info=t("generation.cot_language_info"), scale=1, elem_classes=["has-info-container"])
                constrained_decoding_debug = gr.Checkbox(
                    label=t("generation.constrained_debug_label"), value=False,
                    info=t("generation.constrained_debug_info"), scale=1,
                    interactive=not service_mode,
                )
            with gr.Row():
                allow_lm_batch = gr.Checkbox(label=t("generation.parallel_thinking_label"), value=True, info=t("generation.parallel_thinking_info"), scale=1, elem_classes=["has-info-container"])
                use_cot_caption = gr.Checkbox(label=t("generation.caption_rewrite_label"), value=False, info=t("generation.caption_rewrite_info"), scale=1, elem_classes=["has-info-container"])

        # ═══════════════════════════════════════════
        # Audio Output & Post-processing
        # ═══════════════════════════════════════════
        with gr.Accordion(t("generation.advanced_output_section"), open=False, elem_classes=["has-info-container"]):
            with gr.Row():
                audio_format = gr.Dropdown(
                    choices=[("FLAC", "flac"), ("MP3", "mp3"), ("Opus", "opus"), ("AAC", "aac"), ("WAV (16-bit)", "wav"), ("WAV (32-bit Float)", "wav32")],
                    value="mp3",
                    label=t("generation.audio_format_label"),
                    info=t("generation.audio_format_info"), elem_classes=["has-info-container"],
                    interactive=not service_mode,
                )
                score_scale = gr.Slider(
                    minimum=0.01, maximum=1.0, value=0.5, step=0.01,
                    label=t("generation.score_sensitivity_label"),
                    info=t("generation.score_sensitivity_info"), elem_classes=["has-info-container"],
                    scale=1, visible=not service_mode,
                )
            with gr.Row():
                enable_norm_val = init_params.get("enable_normalization", True) if service_pre_initialized else True
                norm_db_val = init_params.get("normalization_db", -1.0) if service_pre_initialized else -1.0
                enable_normalization = gr.Checkbox(label=t("gen.enable_normalization"), value=enable_norm_val, info=t("gen.enable_normalization_info"), elem_classes=["has-info-container"])
                normalization_db = gr.Slider(label=t("gen.normalization_db"), minimum=-10.0, maximum=0.0, step=0.1, value=norm_db_val, info=t("gen.normalization_db_info"), elem_classes=["has-info-container"])
            with gr.Row():
                latent_shift_val = init_params.get("latent_shift", 0.0) if service_pre_initialized else 0.0
                latent_rescale_val = init_params.get("latent_rescale", 1.0) if service_pre_initialized else 1.0
                latent_shift = gr.Slider(label=t("gen.latent_shift"), minimum=-0.2, maximum=0.2, step=0.01, value=latent_shift_val, info=t("gen.latent_shift_info"), elem_classes=["has-info-container"])
                latent_rescale = gr.Slider(label=t("gen.latent_rescale"), minimum=0.5, maximum=1.5, step=0.01, value=latent_rescale_val, info=t("gen.latent_rescale_info"), elem_classes=["has-info-container"])

        # ═══════════════════════════════════════════
        # Automation & Batch
        # ═══════════════════════════════════════════
        with gr.Accordion(t("generation.advanced_automation_section"), open=False, elem_classes=["has-info-container"]):
            with gr.Row():
                lm_batch_chunk_size = gr.Number(label=t("generation.lm_batch_chunk_label"), value=8, minimum=1, maximum=32, step=1, info=t("generation.lm_batch_chunk_info"), scale=1, interactive=not service_mode, elem_classes=["has-info-container"])

    # Merge service components into the return dict
    result = {
        "advanced_settings_accordion": advanced_settings_accordion,
        "inference_steps": inference_steps,
        "guidance_scale": guidance_scale,
        "infer_method": infer_method,
        "use_adg": use_adg,
        "shift": shift,
        "custom_timesteps": custom_timesteps,
        "cfg_interval_start": cfg_interval_start,
        "cfg_interval_end": cfg_interval_end,
        "seed": seed,
        "random_seed_checkbox": random_seed_checkbox,
        "lm_temperature": lm_temperature,
        "lm_cfg_scale": lm_cfg_scale,
        "lm_top_k": lm_top_k,
        "lm_top_p": lm_top_p,
        "lm_negative_prompt": lm_negative_prompt,
        "use_cot_metas": use_cot_metas,
        "use_cot_language": use_cot_language,
        "constrained_decoding_debug": constrained_decoding_debug,
        "audio_format": audio_format,
        "score_scale": score_scale,
        "enable_normalization": enable_normalization,
        "normalization_db": normalization_db,
        "latent_shift": latent_shift,
        "latent_rescale": latent_rescale,
        "lm_batch_chunk_size": lm_batch_chunk_size,
        "allow_lm_batch": allow_lm_batch,
        "use_cot_caption": use_cot_caption,
        # LoRA components
        "lora_path": lora_path,
        "load_lora_btn": load_lora_btn,
        "unload_lora_btn": unload_lora_btn,
        "use_lora_checkbox": use_lora_checkbox,
        "lora_scale_slider": lora_scale_slider,
        "lora_status": lora_status,
    }
    # Include all service config components
    result.update(service_components)
    return result


# ============================================================================
# Generation Tab Section (inside the Generation tab)
# ============================================================================

def create_generation_tab_section(dit_handler, llm_handler, init_params=None, language='en') -> dict:
    """Create the generation tab content with mode-based UI.

    This replaces the old task_type dropdown + simple/custom toggle with a
    unified Generation Mode radio selector.
    """
    defaults = _compute_init_defaults(dit_handler, llm_handler, init_params, language)
    service_pre_initialized = defaults["service_pre_initialized"]
    service_mode = defaults["service_mode"]
    lm_initialized = defaults["lm_initialized"]
    max_duration = defaults["max_duration"]
    max_batch_size = defaults["max_batch_size"]
    default_batch_size = defaults["default_batch_size"]

    # Determine initial mode choices based on model type
    # Only pure base models (not SFT, not turbo) get extended modes (Extract/Lego/Complete)
    if service_pre_initialized and 'dit_handler' in init_params:
        _config_path = init_params.get('config_path', '')
        is_pure_base = _is_pure_base_model((_config_path or "").lower())
    else:
        available_models = dit_handler.get_available_acestep_v15_models()
        default_model = "acestep-v15-turbo" if "acestep-v15-turbo" in available_models else (available_models[0] if available_models else None)
        actual_model = init_params.get('config_path', default_model) if service_pre_initialized else default_model
        is_pure_base = _is_pure_base_model((actual_model or "").lower())

    initial_mode_choices = GENERATION_MODES_BASE if is_pure_base else GENERATION_MODES_TURBO

    # Wrap everything in a Group to eliminate gaps between components
    with gr.Group():

        # --- Generation Mode selector + Load JSON on same row ---
        with gr.Row(equal_height=True):
            generation_mode = gr.Radio(
                choices=initial_mode_choices,
                value="Custom",
                label=t("generation.mode_label"),
                info=t("generation.mode_info_custom"), elem_classes=["has-info-container"],
                scale=10,
            )
            with gr.Column(scale=1, min_width=80, elem_classes="icon-btn-wrap") as load_file_col:
                load_file = gr.UploadButton(
                    t("generation.load_btn"),
                    file_types=[".json"],
                    file_count="single",
                    variant="secondary",
                    size="lg",
                )

        # Hidden task_type state (set programmatically based on mode)
        task_type = gr.Textbox(
            value="text2music",
            visible=False,
            label="task_type",
        )

        # Instruction display (read-only, hidden — used internally by generation backend)
        instruction_display_gen = gr.Textbox(
            label=t("generation.instruction_label"),
            value=DEFAULT_DIT_INSTRUCTION,
            interactive=False,
            lines=1,
            info=t("generation.instruction_info"), elem_classes=["has-info-container"],
            visible=False,
        )

        # --- Simple Mode Components (only visible in Simple mode) ---
        with gr.Group(visible=False, elem_classes=["has-info-container"]) as simple_mode_group:
            create_help_button("generation_simple")
            with gr.Row(equal_height=True):
                simple_query_input = gr.Textbox(
                    label=t("generation.simple_query_label"),
                    placeholder=t("generation.simple_query_placeholder"),
                    lines=2,
                    info=t("generation.simple_query_info"), elem_classes=["has-info-container"],
                    scale=9,
                )
                with gr.Column(scale=1):
                    simple_vocal_language = gr.Dropdown(
                        choices=[(lang if lang != "unknown" else "Instrumental / auto", lang) for lang in VALID_LANGUAGES], value="unknown",
                        allow_custom_value=True,
                        label=t("generation.simple_vocal_language_label"),
                        interactive=True,
                        scale=1,
                    )
                    simple_instrumental_checkbox = gr.Checkbox(
                        label=t("generation.instrumental_label"), value=False,
                        scale=1
                    )
                with gr.Column(scale=1, min_width=80, elem_classes="icon-btn-wrap"):
                    random_desc_btn = gr.Button(t("generation.sample_btn"), variant="secondary", size="lg")

            with gr.Row(equal_height=True):
                create_sample_btn = gr.Button(
                    t("generation.create_sample_btn"), variant="primary", size="lg",
                )

        simple_sample_created = gr.State(value=False)
        # State to store lyrics before checking Instrumental (for restore on uncheck)
        lyrics_before_instrumental = gr.State(value="")
        # Track previous generation mode so we can clean up polluted values
        # when switching away from Extract/Lego.
        previous_generation_mode = gr.State(value="Custom")

        # --- Source Audio Row (for remix/repaint/extract/lego/complete — hidden in Simple/Custom) ---
        with gr.Row(equal_height=True, visible=False) as src_audio_row:
            src_audio = gr.Audio(
                label=t("generation.source_audio"),
                type="filepath",
                scale=10,
            )
            with gr.Column(scale=1, min_width=80):
                analyze_btn = gr.Button(
                    t("generation.analyze_btn"),
                    variant="secondary",
                    size="lg",
                )

        # --- Track selectors (for extract/lego/complete, base model only) ---
        # Placed immediately below source audio for logical grouping
        # Help buttons for extract/lego are shown alongside their track selectors
        with gr.Group(visible=False) as extract_help_group:
            create_help_button("generation_extract")
        track_name = gr.Dropdown(
            choices=TRACK_NAMES,
            value=None,
            label=t("generation.track_name_label"),
            info=t("generation.track_name_info"), elem_classes=["has-info-container"],
            visible=False,
        )
        with gr.Group(visible=False) as complete_help_group:
            create_help_button("generation_complete")
        complete_track_classes = gr.CheckboxGroup(
            choices=TRACK_NAMES,
            label=t("generation.track_classes_label"),
            info=t("generation.track_classes_info"), elem_classes=["has-info-container"],
            visible=False,
        )

        # --- LM Codes Hints (only visible in Custom mode, collapsed by default) ---
        with gr.Accordion(t("generation.lm_codes_hints"), open=False, visible=True, elem_classes=["has-info-container"]) as text2music_audio_codes_group:
            with gr.Row(equal_height=True):
                lm_codes_audio_upload = gr.Audio(
                    label=t("generation.source_audio"),
                    type="filepath",
                    scale=3,
                )
                text2music_audio_code_string = gr.Textbox(
                    label=t("generation.lm_codes_label"),
                    placeholder=t("generation.lm_codes_placeholder"),
                    lines=6,
                    info=t("generation.lm_codes_info"), elem_classes=["has-info-container"],
                    scale=6,
                )
            with gr.Row():
                convert_src_to_codes_btn = gr.Button(
                    t("generation.convert_codes_btn"),
                    variant="secondary",
                    size="sm",
                    scale=1,
                )
                transcribe_btn = gr.Button(
                    t("generation.transcribe_btn"),
                    variant="secondary",
                    size="sm",
                    scale=1,
                )

        # --- Audio Cover Strength / LM Codes Strength / Remix Strength slider ---
        # Visible in Custom, Remix, Extract, Lego, Complete; hidden in Simple and Repaint
        audio_cover_strength = gr.Slider(
            minimum=0.0, maximum=1.0, value=1.0, step=0.01,
            label=t("generation.codes_strength_label"),
            info=t("generation.codes_strength_info"), elem_classes=["has-info-container"],
            visible=True,
        )

        # --- Cover Strength slider (only visible in Remix mode) + Remix help ---
        with gr.Group(visible=False) as remix_help_group:
            create_help_button("generation_remix")
        cover_noise_strength = gr.Slider(
            minimum=0.0, maximum=1.0, value=0.0, step=0.01,
            label=t("generation.cover_noise_strength_label"),
            info=t("generation.cover_noise_strength_info"), elem_classes=["has-info-container"],
            visible=False,
        )

        # --- Custom Mode: Reference Audio | (Caption + Enhance) | (Lyrics + Instrumental + Enhance) | 🎲 ---
        with gr.Group(visible=True, elem_classes=["has-info-container"]) as custom_mode_group:
            create_help_button("generation_custom")
            with gr.Row(equal_height=True):
                # Left: Reference Audio
                with gr.Column(scale=2, min_width=200):
                    reference_audio = gr.Audio(
                        label=t("generation.reference_audio"),
                        type="filepath",
                        show_label=True,
                    )

                # Middle: Caption column + Lyrics column
                with gr.Column(scale=8):
                    with gr.Row(equal_height=True):
                        # Caption sub-column
                        with gr.Column(scale=1):
                            captions = gr.Textbox(
                                label=t("generation.caption_label"),
                                placeholder=t("generation.caption_placeholder"),
                                lines=12,
                                max_lines=12,
                            )
                            with gr.Row(elem_classes="instrumental-row"):
                                format_caption_btn = gr.Button(t("generation.format_caption_btn"), variant="secondary", size="sm")
                        # Lyrics sub-column
                        with gr.Column(scale=1):
                            lyrics = gr.Textbox(
                                label=t("generation.lyrics_label"),
                                placeholder=t("generation.lyrics_placeholder"),
                                lines=12,
                                max_lines=12,
                            )
                            with gr.Row(elem_classes="instrumental-row"):
                                instrumental_checkbox = gr.Checkbox(
                                    label=t("generation.instrumental_label"), value=False, scale=1,
                                )
                                format_lyrics_btn = gr.Button(t("generation.format_lyrics_btn"), variant="secondary", size="sm", scale=2)

                # Right column: 🎲 Random
                with gr.Column(scale=1, min_width=80, elem_classes="icon-btn-wrap"):
                    sample_btn = gr.Button(t("generation.sample_btn"), variant="primary", size="lg")

        # --- Repainting controls (also used for Lego stem area) ---
        with gr.Group(visible=False) as repainting_group:
            create_help_button("generation_repaint")
            repainting_header_html = gr.HTML(f"<h5>{t('generation.repainting_controls')}</h5>")
            with gr.Row():
                repainting_start = gr.Number(label=t("generation.repainting_start"), value=0.0, step=0.1)
                repainting_end = gr.Number(label=t("generation.repainting_end"), value=-1, minimum=-1, step=0.1)

        # --- Optional Parameters (collapsed by default) ---
        with gr.Accordion(t("generation.optional_params"), open=False, visible=True, elem_classes=["has-info-container"]) as optional_params_accordion:
            gr.Markdown(f"#### {t('generation.optional_music_props')}")
            with gr.Row():
                bpm = gr.Number(label=t("generation.bpm_label"), value=None, step=1, info=t("generation.bpm_info"), elem_classes=["has-info-container"])
                key_scale = gr.Textbox(label=t("generation.keyscale_label"), placeholder=t("generation.keyscale_placeholder"), value="", info=t("generation.keyscale_info"), elem_classes=["has-info-container"])
                time_signature = gr.Dropdown(choices=["", "2", "3", "4", "6", "N/A"], value="", label=t("generation.timesig_label"), allow_custom_value=True, info=t("generation.timesig_info"), elem_classes=["has-info-container"])
                vocal_language = gr.Dropdown(
                    choices=[(lang if lang != "unknown" else "Instrumental / auto", lang) for lang in VALID_LANGUAGES], value="unknown",
                    label=t("generation.vocal_language_label"),
                    info=t("generation.vocal_language_info"),
                    allow_custom_value=True,
                    elem_classes=["has-info-container"],
                )
            gr.Markdown(f"#### {t('generation.optional_gen_settings')}")
            with gr.Row():
                audio_duration = gr.Number(
                    label=t("generation.duration_label"), value=-1, minimum=-1,
                    maximum=float(max_duration), step=0.1,
                    info=t("generation.duration_info") + f" (Max: {max_duration}s / {max_duration // 60} min)", elem_classes=["has-info-container"],
                )
                batch_size_input = gr.Number(
                    label=t("generation.batch_size_label"), value=default_batch_size,
                    minimum=1, maximum=max_batch_size, step=1,
                    info=t("generation.batch_size_info") + f" (Max: {max_batch_size})", elem_classes=["has-info-container"],
                    interactive=not service_mode,
                )

        # --- Generate Button Row (hidden in Simple mode) ---
        generate_btn_interactive = init_params.get('enable_generate', False) if service_pre_initialized else False
        with gr.Row(equal_height=True, visible=True) as generate_btn_row:
            with gr.Column(scale=1, variant="compact"):
                think_checkbox = gr.Checkbox(label=t("generation.think_label"), value=lm_initialized, scale=1, interactive=lm_initialized)
                auto_score = gr.Checkbox(label=t("generation.auto_score_label"), value=False, scale=1, interactive=not service_mode)
            with gr.Column(scale=18):
                generate_btn = gr.Button(t("generation.generate_btn"), variant="primary", size="lg", interactive=generate_btn_interactive)
            with gr.Column(scale=1, variant="compact"):
                autogen_checkbox = gr.Checkbox(
                    label=t("generation.autogen_label"), value=False, scale=1,
                    interactive=not service_mode,
                )
                auto_lrc = gr.Checkbox(label=t("generation.auto_lrc_label"), value=False, scale=1, interactive=not service_mode)
    
    return {
        "generation_mode": generation_mode,
        "task_type": task_type,
        "instruction_display_gen": instruction_display_gen,
        "load_file": load_file,
        "load_file_col": load_file_col,
        "reference_audio": reference_audio,
        "src_audio": src_audio,
        "src_audio_row": src_audio_row,
        "analyze_btn": analyze_btn,
        "convert_src_to_codes_btn": convert_src_to_codes_btn,
        "lm_codes_audio_upload": lm_codes_audio_upload,
        "text2music_audio_code_string": text2music_audio_code_string,
        "transcribe_btn": transcribe_btn,
        "text2music_audio_codes_group": text2music_audio_codes_group,
        "audio_cover_strength": audio_cover_strength,
        "cover_noise_strength": cover_noise_strength,
        "track_name": track_name,
        "complete_track_classes": complete_track_classes,
        "repainting_group": repainting_group,
        "repainting_header_html": repainting_header_html,
        "repainting_start": repainting_start,
        "repainting_end": repainting_end,
        "simple_mode_group": simple_mode_group,
        "simple_query_input": simple_query_input,
        "random_desc_btn": random_desc_btn,
        "simple_instrumental_checkbox": simple_instrumental_checkbox,
        "simple_vocal_language": simple_vocal_language,
        "create_sample_btn": create_sample_btn,
        "simple_sample_created": simple_sample_created,
        "lyrics_before_instrumental": lyrics_before_instrumental,
        "previous_generation_mode": previous_generation_mode,
        "custom_mode_group": custom_mode_group,
        "captions": captions,
        "sample_btn": sample_btn,
        "lyrics": lyrics,
        "instrumental_checkbox": instrumental_checkbox,
        "vocal_language": vocal_language,
        "format_caption_btn": format_caption_btn,
        "format_lyrics_btn": format_lyrics_btn,
        "optional_params_accordion": optional_params_accordion,
        "bpm": bpm,
        "key_scale": key_scale,
        "time_signature": time_signature,
        "audio_duration": audio_duration,
        "batch_size_input": batch_size_input,
        "think_checkbox": think_checkbox,
        "auto_score": auto_score,
        "generate_btn": generate_btn,
        "generate_btn_row": generate_btn_row,
        "autogen_checkbox": autogen_checkbox,
        "auto_lrc": auto_lrc,
        # Mode-specific help button groups (visibility toggled with mode)
        "remix_help_group": remix_help_group,
        "extract_help_group": extract_help_group,
        "complete_help_group": complete_help_group,
        # GPU config values for validation (passed through)
        "max_duration": max_duration,
        "max_batch_size": max_batch_size,
    }


# ============================================================================
# Backward-compatible wrapper (deprecated, kept for reference)
# ============================================================================

def create_generation_section(dit_handler, llm_handler, init_params=None, language='en') -> dict:
    """DEPRECATED: Use create_advanced_settings_section + create_generation_tab_section instead.

    This wrapper creates both sections and merges their dicts for backward compatibility.
    """
    settings_section = create_advanced_settings_section(dit_handler, llm_handler, init_params, language)
    gen_section = create_generation_tab_section(dit_handler, llm_handler, init_params, language)

    merged = {}
    merged.update(settings_section)
    merged.update(gen_section)
    return merged
