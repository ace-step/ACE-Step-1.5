"""HTTP route for reinitializing service components after unload flows."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict

import torch
from fastapi import Depends, FastAPI, HTTPException


def register_reinitialize_route(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[..., Dict[str, Any]],
    env_bool: Callable[[str, bool], bool],
    get_project_root: Callable[[], str],
) -> None:
    """Register the reinitialization endpoint.

    Inputs: app, auth dependency, response wrapper, env parser, and project-root helper.
    Returns: None after registering ``POST /v1/reinitialize`` on ``app``.
    """

    @app.post("/v1/reinitialize")
    async def reinitialize_service(_: None = Depends(verify_api_key)):
        """Reinitialize components that were unloaded during training/preprocessing."""

        handler = app.state.handler
        llm = app.state.llm_handler

        # Preserve original api_server contract: missing service state is an HTTP 500.
        if handler is None:
            raise HTTPException(status_code=500, detail="Service not initialized")

        try:
            import gc

            reloaded = []
            params = getattr(handler, "last_init_params", None) or None
            if params and (handler.model is None or handler.vae is None or handler.text_encoder is None):
                status, ok = handler.initialize_service(
                    project_root=params["project_root"],
                    config_path=params["config_path"],
                    device=params["device"],
                    use_flash_attention=params["use_flash_attention"],
                    compile_model=params["compile_model"],
                    offload_to_cpu=params["offload_to_cpu"],
                    offload_dit_to_cpu=params["offload_dit_to_cpu"],
                    quantization=params.get("quantization"),
                    prefer_source=params.get("prefer_source"),
                    use_mlx_dit=params.get("use_mlx_dit", True),
                )
                if ok:
                    reloaded.append("DiT/VAE/Text Encoder")

            if llm and not llm.llm_initialized:
                llm_params = getattr(llm, "last_init_params", None)
                if llm_params is None:
                    project_root = get_project_root()
                    checkpoint_dir = os.path.join(project_root, "checkpoints")
                    lm_model_path = os.getenv("ACESTEP_LM_MODEL_PATH", "acestep-5Hz-lm-0.6B").strip()
                    backend = os.getenv("ACESTEP_LM_BACKEND", "vllm").strip().lower()
                    lm_device = os.getenv("ACESTEP_LM_DEVICE", os.getenv("ACESTEP_DEVICE", "auto"))
                    lm_offload = env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False)
                    llm_params = {
                        "checkpoint_dir": checkpoint_dir,
                        "lm_model_path": lm_model_path,
                        "backend": backend,
                        "device": lm_device,
                        "offload_to_cpu": lm_offload,
                        "dtype": None,
                    }

                status, ok = llm.initialize(**llm_params)
                if ok:
                    reloaded.append("LLM")
                    try:
                        app.state._llm_initialized = True
                        app.state._llm_init_error = None
                    except Exception:
                        pass
                else:
                    try:
                        app.state._llm_initialized = False
                        app.state._llm_init_error = status
                    except Exception:
                        pass

            if handler.model is not None:
                if hasattr(handler.model, "decoder") and handler.model.decoder is not None:
                    first_param = next(handler.model.decoder.parameters(), None)
                    if first_param is not None and first_param.device.type == "cpu":
                        handler.model.decoder = handler.model.decoder.to(handler.device).to(handler.dtype)
                        reloaded.append("Decoder (moved to GPU)")

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            message = "\u2705 Service reinitialized"
            if reloaded:
                message += f"\n\U0001f504 Reloaded: {', '.join(reloaded)}"
            return wrap_response({"message": message, "reloaded": reloaded})
        except Exception as exc:
            return wrap_response(None, code=500, error=f"Reinitialization failed: {str(exc)}")
