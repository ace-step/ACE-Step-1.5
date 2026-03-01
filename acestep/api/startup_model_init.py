"""Startup model initialization orchestration for API server lifespan."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from acestep.gpu_config import (
    VRAM_AUTO_OFFLOAD_THRESHOLD_GB,
    get_gpu_config,
    set_global_gpu_config,
)
from acestep.api.startup_llm_init import initialize_llm_at_startup


def initialize_models_at_startup(
    *,
    app: Any,
    handler: Any,
    llm_handler: Any,
    handler2: Any,
    handler3: Any,
    config_path2: str,
    config_path3: str,
    get_project_root: Callable[[], str],
    get_model_name: Callable[[str], str],
    ensure_model_downloaded: Callable[[str, str], str],
    env_bool: Callable[[str, bool], bool],
) -> None:
    """Initialize DiT and optional LLM models at server startup."""

    no_init = env_bool("ACESTEP_NO_INIT", False)
    gpu_config = get_gpu_config()
    set_global_gpu_config(gpu_config)
    app.state.gpu_config = gpu_config

    gpu_memory_gb = gpu_config.gpu_memory_gb
    auto_offload = gpu_memory_gb > 0 and gpu_memory_gb < VRAM_AUTO_OFFLOAD_THRESHOLD_GB

    print(f"\n{'='*60}")
    print("[API Server] GPU Configuration Detected:")
    print(f"{'='*60}")
    print(f"  GPU Memory: {gpu_memory_gb:.2f} GB")
    print(f"  Configuration Tier: {gpu_config.tier}")
    print(f"  Max Duration (with LM): {gpu_config.max_duration_with_lm}s")
    print(f"  Max Duration (without LM): {gpu_config.max_duration_without_lm}s")
    print(f"  Max Batch Size (with LM): {gpu_config.max_batch_size_with_lm}")
    print(f"  Max Batch Size (without LM): {gpu_config.max_batch_size_without_lm}")
    print(f"  Default LM Init: {gpu_config.init_lm_default}")
    print(f"  Available LM Models: {gpu_config.available_lm_models or 'None'}")
    print(f"{'='*60}\n")

    if no_init:
        print("[API Server] --no-init mode: Skipping all model loading at startup")
        print("[API Server] Models will be lazy-loaded on first request")
        print("[API Server] Server is ready to accept requests (models not loaded yet)")
        return

    print("[API Server] Initializing models at startup...")
    if auto_offload:
        print("[API Server] Auto-enabling CPU offload (GPU < 16GB)")
    elif gpu_memory_gb > 0:
        print("[API Server] CPU offload disabled by default (GPU >= 16GB)")
    else:
        print("[API Server] No GPU detected, running on CPU")

    project_root = get_project_root()
    config_path = os.getenv("ACESTEP_CONFIG_PATH", "acestep-v15-turbo")
    device = os.getenv("ACESTEP_DEVICE", "auto")
    use_flash_attention = env_bool("ACESTEP_USE_FLASH_ATTENTION", True)

    offload_to_cpu_env = os.getenv("ACESTEP_OFFLOAD_TO_CPU")
    if offload_to_cpu_env is not None:
        offload_to_cpu = env_bool("ACESTEP_OFFLOAD_TO_CPU", False)
    else:
        offload_to_cpu = auto_offload
        if auto_offload:
            print("[API Server] Auto-setting offload_to_cpu=True based on GPU memory")

    offload_dit_to_cpu = env_bool("ACESTEP_OFFLOAD_DIT_TO_CPU", False)
    compile_model = env_bool("ACESTEP_COMPILE_MODEL", False)

    checkpoint_dir = os.path.join(project_root, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)

    dit_model_name = get_model_name(config_path)
    if dit_model_name:
        try:
            ensure_model_downloaded(dit_model_name, checkpoint_dir)
        except Exception as exc:
            print(f"[API Server] Warning: Failed to download DiT model: {exc}")

    try:
        ensure_model_downloaded("vae", checkpoint_dir)
    except Exception as exc:
        print(f"[API Server] Warning: Failed to download VAE model: {exc}")

    print(f"[API Server] Loading primary DiT model: {config_path}")
    status_msg, ok = handler.initialize_service(
        project_root=project_root,
        config_path=config_path,
        device=device,
        use_flash_attention=use_flash_attention,
        compile_model=compile_model,
        offload_to_cpu=offload_to_cpu,
        offload_dit_to_cpu=offload_dit_to_cpu,
    )
    if not ok:
        app.state._init_error = status_msg
        print(f"[API Server] ERROR: Primary model failed to load: {status_msg}")
        raise RuntimeError(status_msg)
    app.state._initialized = True
    print(f"[API Server] Primary model loaded: {get_model_name(config_path)}")

    if handler2 and config_path2:
        model2_name = get_model_name(config_path2)
        if model2_name:
            try:
                ensure_model_downloaded(model2_name, checkpoint_dir)
            except Exception as exc:
                print(f"[API Server] Warning: Failed to download secondary model: {exc}")
        print(f"[API Server] Loading secondary DiT model: {config_path2}")
        try:
            status_msg2, ok2 = handler2.initialize_service(
                project_root=project_root,
                config_path=config_path2,
                device=device,
                use_flash_attention=use_flash_attention,
                compile_model=compile_model,
                offload_to_cpu=offload_to_cpu,
                offload_dit_to_cpu=offload_dit_to_cpu,
            )
            app.state._initialized2 = ok2
            if ok2:
                print(f"[API Server] Secondary model loaded: {model2_name}")
            else:
                print(f"[API Server] Warning: Secondary model failed: {status_msg2}")
        except Exception as exc:
            print(f"[API Server] Warning: Failed to initialize secondary model: {exc}")
            app.state._initialized2 = False

    if handler3 and config_path3:
        model3_name = get_model_name(config_path3)
        if model3_name:
            try:
                ensure_model_downloaded(model3_name, checkpoint_dir)
            except Exception as exc:
                print(f"[API Server] Warning: Failed to download third model: {exc}")
        print(f"[API Server] Loading third DiT model: {config_path3}")
        try:
            status_msg3, ok3 = handler3.initialize_service(
                project_root=project_root,
                config_path=config_path3,
                device=device,
                use_flash_attention=use_flash_attention,
                compile_model=compile_model,
                offload_to_cpu=offload_to_cpu,
                offload_dit_to_cpu=offload_dit_to_cpu,
            )
            app.state._initialized3 = ok3
            if ok3:
                print(f"[API Server] Third model loaded: {model3_name}")
            else:
                print(f"[API Server] Warning: Third model failed: {status_msg3}")
        except Exception as exc:
            print(f"[API Server] Warning: Failed to initialize third model: {exc}")
            app.state._initialized3 = False

    initialize_llm_at_startup(
        app=app,
        llm_handler=llm_handler,
        gpu_config=gpu_config,
        device=device,
        offload_to_cpu=offload_to_cpu,
        checkpoint_dir=checkpoint_dir,
        get_model_name=get_model_name,
        ensure_model_downloaded=ensure_model_downloaded,
        env_bool=env_bool,
    )

    print("[API Server] All models initialized successfully!")
