"""LLM readiness helper for generation requests."""

from __future__ import annotations

import os
from typing import Any, Callable


def ensure_llm_ready_for_request(
    *,
    app_state: Any,
    llm_handler: Any,
    req: Any,
    get_project_root: Callable[[], str],
    get_model_name: Callable[[str], str],
    ensure_model_downloaded: Callable[[str, str], str],
    env_bool: Callable[[str, bool], bool],
    log_fn: Callable[[str], None] = print,
) -> None:
    """Initialize LLM on-demand for a request unless lazy loading is blocked.

    Args:
        app_state: FastAPI app state with LLM init flags and lock.
        llm_handler: LLM handler instance.
        req: Request object carrying optional LM overrides.
        get_project_root: Callback that returns project root path.
        get_model_name: Callback that maps model path to model name.
        ensure_model_downloaded: Callback to ensure checkpoint availability.
        env_bool: Boolean env parser callback.
        log_fn: Logging callback for user-visible status messages.
    """

    with app_state._llm_init_lock:
        initialized = getattr(app_state, "_llm_initialized", False)
        had_error = getattr(app_state, "_llm_init_error", None)
        if initialized or had_error is not None:
            return
        log_fn("[API Server] reloading.")

        if getattr(app_state, "_llm_lazy_load_disabled", False):
            app_state._llm_init_error = (
                "LLM not initialized at startup. To enable LLM, set ACESTEP_INIT_LLM=true "
                "in .env or environment variables. For this request, optional LLM features "
                "(use_cot_caption, use_cot_language) will be auto-disabled."
            )
            log_fn("[API Server] LLM lazy load blocked: LLM was not initialized at startup")
            return

        init_llm_env = os.getenv("ACESTEP_INIT_LLM", "").strip().lower()
        if init_llm_env in {"0", "false", "no", "n", "off"}:
            app_state._llm_lazy_load_disabled = True
            app_state._llm_init_error = (
                "LLM disabled via ACESTEP_INIT_LLM=false. "
                "Optional LLM features (use_cot_caption, use_cot_language) will be auto-disabled."
            )
            log_fn("[API Server] LLM lazy load blocked: ACESTEP_INIT_LLM=false")
            return

        project_root = get_project_root()
        checkpoint_dir = os.path.join(project_root, "checkpoints")
        lm_model_path = (
            req.lm_model_path or os.getenv("ACESTEP_LM_MODEL_PATH") or "acestep-5Hz-lm-0.6B"
        ).strip()
        backend = (req.lm_backend or os.getenv("ACESTEP_LM_BACKEND") or "vllm").strip().lower()
        if backend not in {"vllm", "pt", "mlx"}:
            backend = "vllm"

        lm_model_name = get_model_name(lm_model_path)
        if lm_model_name:
            try:
                ensure_model_downloaded(lm_model_name, checkpoint_dir)
            except Exception as exc:
                log_fn(f"[API Server] Warning: Failed to download LM model {lm_model_name}: {exc}")

        lm_device = os.getenv("ACESTEP_LM_DEVICE", os.getenv("ACESTEP_DEVICE", "auto"))
        lm_offload = env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False)
        status, ok = llm_handler.initialize(
            checkpoint_dir=checkpoint_dir,
            lm_model_path=lm_model_path,
            backend=backend,
            device=lm_device,
            offload_to_cpu=lm_offload,
            dtype=None,
        )
        if not ok:
            app_state._llm_init_error = status
        else:
            app_state._llm_initialized = True
