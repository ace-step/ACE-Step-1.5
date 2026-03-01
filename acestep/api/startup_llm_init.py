"""LLM startup initialization helper for API server."""

from __future__ import annotations

import os
from typing import Any, Callable

from acestep.gpu_config import get_recommended_lm_model, is_lm_model_supported


def initialize_llm_at_startup(
    *,
    app: Any,
    llm_handler: Any,
    gpu_config: Any,
    device: str,
    offload_to_cpu: bool,
    checkpoint_dir: str,
    get_model_name: Callable[[str], str],
    ensure_model_downloaded: Callable[[str, str], str],
    env_bool: Callable[[str, bool], bool],
) -> None:
    """Initialize LLM model according to GPU config and environment overrides."""

    init_llm_env = os.getenv("ACESTEP_INIT_LLM", "").strip().lower()
    init_llm = gpu_config.init_lm_default
    print(
        f"[API Server] GPU auto-detection: init_llm={init_llm} "
        f"(VRAM: {gpu_config.gpu_memory_gb:.1f}GB, tier: {gpu_config.tier})"
    )
    if not init_llm_env or init_llm_env == "auto":
        print("[API Server] ACESTEP_INIT_LLM=auto, using GPU auto-detection result")
    elif init_llm_env in {"1", "true", "yes", "y", "on"}:
        if init_llm:
            print("[API Server] ACESTEP_INIT_LLM=true (GPU already supports LLM, no override needed)")
        else:
            init_llm = True
            print("[API Server] ACESTEP_INIT_LLM=true, overriding GPU auto-detection (force enable)")
    else:
        if not init_llm:
            print("[API Server] ACESTEP_INIT_LLM=false (GPU already disabled LLM, no override needed)")
        else:
            init_llm = False
            print("[API Server] ACESTEP_INIT_LLM=false, overriding GPU auto-detection (force disable)")

    if init_llm:
        print("[API Server] Loading LLM model...")
        lm_model_path = os.getenv("ACESTEP_LM_MODEL_PATH", "").strip()
        if lm_model_path:
            print(f"[API Server] Using user-specified LM model: {lm_model_path}")
        else:
            recommended_lm = get_recommended_lm_model(gpu_config)
            if recommended_lm:
                lm_model_path = recommended_lm
                print(f"[API Server] Auto-selected LM model: {lm_model_path} based on GPU tier")
            else:
                lm_model_path = "acestep-5Hz-lm-0.6B"
                print(f"[API Server] No recommended model for this GPU tier, using smallest: {lm_model_path}")

        is_supported, warning_msg = is_lm_model_supported(lm_model_path, gpu_config)
        if not is_supported:
            print(f"[API Server] Warning: {warning_msg}")
            recommended_lm = get_recommended_lm_model(gpu_config)
            if recommended_lm:
                lm_model_path = recommended_lm
                print(f"[API Server] Falling back to supported LM model: {lm_model_path}")
            else:
                print(f"[API Server] No GPU-validated LM model available, attempting {lm_model_path} anyway (may cause OOM)")

        lm_backend = os.getenv("ACESTEP_LM_BACKEND", "vllm").strip().lower()
        if lm_backend not in {"vllm", "pt", "mlx"}:
            lm_backend = "vllm"
        lm_device = os.getenv("ACESTEP_LM_DEVICE", device)
        lm_offload_env = os.getenv("ACESTEP_LM_OFFLOAD_TO_CPU")
        lm_offload = env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False) if lm_offload_env is not None else offload_to_cpu

        lm_model_name = get_model_name(lm_model_path)
        try:
            ensure_model_downloaded(lm_model_name, checkpoint_dir)
        except Exception as exc:
            print(f"[API Server] Warning: Failed to download LLM model: {exc}")

        llm_status, llm_ok = llm_handler.initialize(
            checkpoint_dir=checkpoint_dir,
            lm_model_path=lm_model_path,
            backend=lm_backend,
            device=lm_device,
            offload_to_cpu=lm_offload,
            dtype=None,
        )
        if llm_ok:
            app.state._llm_initialized = True
            print(f"[API Server] LLM model loaded: {lm_model_path}")
        else:
            app.state._llm_init_error = llm_status
            print(f"[API Server] Warning: LLM model failed to load: {llm_status}")
        return

    print("[API Server] Skipping LLM initialization (disabled or not supported for this GPU)")
    app.state._llm_initialized = False
    app.state._llm_lazy_load_disabled = True
    print("[API Server] LLM lazy loading disabled. To enable LLM:")
    print("[API Server]   - Set ACESTEP_INIT_LLM=true in .env or environment")
    print("[API Server]   - Or use --init-llm command line flag")
