"""Blocking model initialization helpers for API model service routes."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from acestep.gpu_config import VRAM_AUTO_OFFLOAD_THRESHOLD_GB, get_gpu_config


def initialize_models_for_request(
    app_state: Any,
    model_name: Optional[str],
    init_llm: bool,
    requested_lm_model_path: Optional[str],
    get_project_root: Callable[[], str],
    get_model_name: Callable[[str], str],
    ensure_model_downloaded: Callable[[str, str], str],
    env_bool: Callable[[str, bool], bool],
) -> Dict[str, Optional[str]]:
    """Initialize DiT and optional LM models.

    Args:
        app_state: FastAPI application state carrying handler objects and flags.
        model_name: Requested DiT model name, or current configured model when empty.
        init_llm: Whether to initialize the LM in the same request.
        requested_lm_model_path: Optional LM model path/name override.
        get_project_root: Returns the project root path.
        get_model_name: Normalizes a model path to its model name.
        ensure_model_downloaded: Ensures a named model exists under checkpoints.
        env_bool: Reads boolean environment variables.
    Returns:
        Mapping with keys ``loaded_model`` and ``loaded_lm_model``.
    Raises:
        RuntimeError: When model names are invalid or DiT/LLM initialization fails.
        AttributeError: When required app state attributes are missing (legacy behavior).
    """

    handler = app_state.handler
    llm = app_state.llm_handler
    project_root = get_project_root()
    checkpoint_dir = os.path.join(project_root, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)

    target_model = (model_name or get_model_name(getattr(app_state, "_config_path", ""))).strip()
    if not target_model:
        raise RuntimeError("No DiT model specified")

    gpu_config = get_gpu_config()
    auto_offload = gpu_config.gpu_memory_gb > 0 and gpu_config.gpu_memory_gb < VRAM_AUTO_OFFLOAD_THRESHOLD_GB
    offload_to_cpu_env = os.getenv("ACESTEP_OFFLOAD_TO_CPU")
    offload_to_cpu = env_bool("ACESTEP_OFFLOAD_TO_CPU", False) if offload_to_cpu_env is not None else auto_offload
    use_flash_attention = env_bool("ACESTEP_USE_FLASH_ATTENTION", True)
    offload_dit_to_cpu = env_bool("ACESTEP_OFFLOAD_DIT_TO_CPU", False)
    compile_model = env_bool("ACESTEP_COMPILE_MODEL", False)
    device = os.getenv("ACESTEP_DEVICE", "auto")

    ensure_model_downloaded(target_model, checkpoint_dir)
    ensure_model_downloaded("vae", checkpoint_dir)

    status_msg, ok = handler.initialize_service(
        project_root=project_root,
        config_path=target_model,
        device=device,
        use_flash_attention=use_flash_attention,
        compile_model=compile_model,
        offload_to_cpu=offload_to_cpu,
        offload_dit_to_cpu=offload_dit_to_cpu,
    )
    if not ok:
        raise RuntimeError(f"DiT init failed: {status_msg}")

    app_state._config_path = target_model
    app_state._initialized = True
    app_state._init_error = None

    loaded_lm_model: Optional[str] = None
    if init_llm:
        lm_model_path = (requested_lm_model_path or os.getenv("ACESTEP_LM_MODEL_PATH", "acestep-5Hz-lm-0.6B")).strip()
        if not lm_model_path:
            lm_model_path = "acestep-5Hz-lm-0.6B"

        os.environ["ACESTEP_INIT_LLM"] = "true"
        os.environ["ACESTEP_LM_MODEL_PATH"] = lm_model_path

        lm_backend = os.getenv("ACESTEP_LM_BACKEND", "vllm").strip().lower()
        if lm_backend not in {"vllm", "pt", "mlx"}:
            lm_backend = "vllm"
        lm_device = os.getenv("ACESTEP_LM_DEVICE", device)
        lm_offload_env = os.getenv("ACESTEP_LM_OFFLOAD_TO_CPU")
        lm_offload = env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False) if lm_offload_env is not None else offload_to_cpu

        lm_model_name = get_model_name(lm_model_path)
        if lm_model_name:
            ensure_model_downloaded(lm_model_name, checkpoint_dir)

        with app_state._llm_init_lock:
            llm_status, llm_ok = llm.initialize(
                checkpoint_dir=checkpoint_dir,
                lm_model_path=lm_model_path,
                backend=lm_backend,
                device=lm_device,
                offload_to_cpu=lm_offload,
                dtype=None,
            )
            if not llm_ok:
                app_state._llm_initialized = False
                app_state._llm_init_error = llm_status
                raise RuntimeError(f"LLM init failed: {llm_status}")
            app_state._llm_initialized = True
            app_state._llm_init_error = None
            app_state._llm_lazy_load_disabled = False
        loaded_lm_model = lm_model_name or lm_model_path

    return {"loaded_model": target_model, "loaded_lm_model": loaded_lm_model}
