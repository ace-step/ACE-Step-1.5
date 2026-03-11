"""HTTP routes for service health, model inventory, and on-demand model init."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from acestep.api.http.model_init_service import initialize_models_for_request


class InitModelRequest(BaseModel):
    """Request payload for on-demand DiT/LM model initialization."""

    model: Optional[str] = Field(default=None, description="DiT model name to initialize (e.g., 'acestep-v15-base')")
    init_llm: bool = Field(default=False, description="Whether to initialize LLM as part of this request")
    lm_model_path: Optional[str] = Field(default=None, description="LLM model path/name (e.g., 'acestep-5Hz-lm-1.7B')")


def _collect_model_inventory(
    app: FastAPI,
    get_project_root: Callable[[], str],
    get_model_name: Callable[[str], str],
) -> Dict[str, Any]:
    """Collect DiT/LM inventory for status endpoints.

    Inputs: app state plus project/model helper callables.
    Returns: wrapped-internal inventory payload with loaded/default model metadata.
    """

    project_root = get_project_root()
    checkpoint_dir = os.path.join(project_root, "checkpoints")

    loaded_dit_models: Dict[str, bool] = {}
    primary_model = get_model_name(getattr(app.state, "_config_path", ""))
    secondary_model = get_model_name(getattr(app.state, "_config_path2", ""))
    third_model = get_model_name(getattr(app.state, "_config_path3", ""))

    if getattr(app.state, "_initialized", False) and primary_model:
        loaded_dit_models[primary_model] = True
    if getattr(app.state, "_initialized2", False) and secondary_model:
        loaded_dit_models[secondary_model] = True
    if getattr(app.state, "_initialized3", False) and third_model:
        loaded_dit_models[third_model] = True

    available_dit_models = set(loaded_dit_models.keys())
    available_lm_models = set()

    if os.path.isdir(checkpoint_dir):
        for name in os.listdir(checkpoint_dir):
            full_path = os.path.join(checkpoint_dir, name)
            if not os.path.isdir(full_path):
                continue
            if name.startswith("acestep-5Hz-lm-"):
                available_lm_models.add(name)
            elif name.startswith("acestep-"):
                available_dit_models.add(name)

    llm_initialized = bool(getattr(app.state, "_llm_initialized", False))
    loaded_lm_model: Optional[str] = None
    if llm_initialized:
        llm = getattr(app.state, "llm_handler", None)
        llm_params = getattr(llm, "last_init_params", None) if llm else None
        lm_model_path = ""
        if isinstance(llm_params, dict):
            lm_model_path = str(llm_params.get("lm_model_path", "") or "")
        if not lm_model_path:
            lm_model_path = os.getenv("ACESTEP_LM_MODEL_PATH", "").strip()
        loaded_lm_model = get_model_name(lm_model_path) or None
        if loaded_lm_model:
            available_lm_models.add(loaded_lm_model)

    models = [
        {
            "name": name,
            "is_default": bool(name == primary_model and primary_model),
            "is_loaded": name in loaded_dit_models,
        }
        for name in sorted(available_dit_models)
    ]
    lm_models = [
        {
            "name": name,
            "is_loaded": bool(loaded_lm_model and name == loaded_lm_model),
        }
        for name in sorted(available_lm_models)
    ]

    return {
        "models": models,
        "default_model": primary_model or None,
        "lm_models": lm_models,
        "loaded_lm_model": loaded_lm_model,
        "llm_initialized": llm_initialized,
    }


def register_model_service_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[..., Dict[str, Any]],
    store: Any,
    queue_maxsize: int,
    initial_avg_job_seconds: float,
    get_project_root: Callable[[], str],
    get_model_name: Callable[[str], str],
    ensure_model_downloaded: Callable[[str, str], str],
    env_bool: Callable[[str, bool], bool],
) -> None:
    """Register health/stats/inventory/init routes.

    Inputs: app, auth/response wrappers, job store settings, and model helper callables.
    Returns: None after route registration side effects on ``app``.
    """

    @app.get("/health")
    async def health_check():
        """Health check endpoint for service status."""

        inventory = _collect_model_inventory(app, get_project_root, get_model_name)
        return wrap_response(
            {
                "status": "ok",
                "service": "ACE-Step API",
                "version": "1.0",
                "models_initialized": bool(getattr(app.state, "_initialized", False)),
                "llm_initialized": inventory["llm_initialized"],
                "loaded_model": inventory["default_model"],
                "loaded_lm_model": inventory["loaded_lm_model"],
            }
        )

    @app.get("/v1/stats")
    async def get_stats(_: None = Depends(verify_api_key)):
        """Get server statistics including job store stats."""

        job_stats = store.get_stats()
        async with app.state.stats_lock:
            avg_job_seconds = getattr(app.state, "avg_job_seconds", initial_avg_job_seconds)
        return wrap_response(
            {
                "jobs": job_stats,
                "queue_size": app.state.job_queue.qsize(),
                "queue_maxsize": queue_maxsize,
                "avg_job_seconds": avg_job_seconds,
            }
        )

    @app.get("/v1/models")
    async def list_models(_: None = Depends(verify_api_key)):
        """List available DiT/LM models and their load status."""

        return wrap_response(_collect_model_inventory(app, get_project_root, get_model_name))

    @app.get("/v1/model_inventory")
    async def model_inventory(_: None = Depends(verify_api_key)):
        """List available DiT/LM models (non-OpenRouter internal endpoint)."""

        return wrap_response(_collect_model_inventory(app, get_project_root, get_model_name))

    @app.post("/v1/init")
    async def init_model(request: InitModelRequest, _: None = Depends(verify_api_key)):
        """Initialize or switch DiT/LM models on demand."""

        async with app.state._init_lock:
            loop = asyncio.get_running_loop()

            try:
                result = await loop.run_in_executor(
                    app.state.executor,
                    lambda: initialize_models_for_request(
                        app_state=app.state,
                        model_name=request.model,
                        init_llm=request.init_llm,
                        requested_lm_model_path=request.lm_model_path,
                        get_project_root=get_project_root,
                        get_model_name=get_model_name,
                        ensure_model_downloaded=ensure_model_downloaded,
                        env_bool=env_bool,
                    ),
                )
                inventory = _collect_model_inventory(app, get_project_root, get_model_name)
                return wrap_response(
                    {
                        "message": "Model initialization completed",
                        "loaded_model": result.get("loaded_model"),
                        "loaded_lm_model": result.get("loaded_lm_model"),
                        "models": inventory["models"],
                        "lm_models": inventory["lm_models"],
                        "llm_initialized": inventory["llm_initialized"],
                    }
                )
            except Exception as exc:
                return wrap_response(None, code=500, error=f"Model initialization failed: {str(exc)}")
