"""HTTP routes for random sample creation and input formatting."""

from __future__ import annotations

import json
import os
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request


def register_sample_format_routes(
    app: FastAPI,
    verify_token_from_request: Callable[[dict, Optional[str]], Optional[str]],
    wrap_response: Callable[..., Dict[str, Any]],
    simple_example_data: List[Dict[str, Any]],
    custom_example_data: List[Dict[str, Any]],
    format_sample: Callable[..., Any],
    get_project_root: Callable[[], str],
    get_model_name: Callable[[str], str],
    ensure_model_downloaded: Callable[[str, str], str],
    env_bool: Callable[[str, bool], bool],
    to_int: Callable[[Any, Optional[int]], Optional[int]],
    to_float: Callable[[Any, Optional[float]], Optional[float]],
) -> None:
    """Register random-sample and format-input routes on the FastAPI app."""

    @app.post("/create_random_sample")
    async def create_random_sample_endpoint(request: Request, authorization: Optional[str] = Header(None)):
        """Return a random pre-loaded sample payload for UI form filling."""

        content_type = (request.headers.get("content-type") or "").lower()
        if "json" in content_type:
            body = await request.json()
        else:
            form = await request.form()
            body = {k: v for k, v in form.items()}

        verify_token_from_request(body, authorization)
        sample_type = body.get("sample_type", "simple_mode") or "simple_mode"
        example_data = simple_example_data if sample_type == "simple_mode" else custom_example_data
        if not example_data:
            return wrap_response(None, code=500, error="No example data available")
        # Preserve existing API behavior of returning random sample payload.
        import random

        return wrap_response(random.choice(example_data))

    @app.post("/format_input")
    async def format_input_endpoint(request: Request, authorization: Optional[str] = Header(None)):
        """Format prompt/lyrics via LLM and return normalized metadata fields."""

        content_type = (request.headers.get("content-type") or "").lower()
        if "json" in content_type:
            body = await request.json()
        else:
            form = await request.form()
            body = {k: v for k, v in form.items()}

        verify_token_from_request(body, authorization)
        llm = app.state.llm_handler
        llm_lock: Lock = app.state._llm_init_lock

        with llm_lock:
            if not getattr(app.state, "_llm_initialized", False):
                if getattr(app.state, "_llm_init_error", None):
                    raise HTTPException(status_code=500, detail=f"LLM init failed: {app.state._llm_init_error}")
                if getattr(app.state, "_llm_lazy_load_disabled", False):
                    raise HTTPException(
                        status_code=503,
                        detail="LLM not initialized. Set ACESTEP_INIT_LLM=true in .env to enable.",
                    )

                project_root = get_project_root()
                checkpoint_dir = os.path.join(project_root, "checkpoints")
                lm_model_path = os.getenv("ACESTEP_LM_MODEL_PATH", "acestep-5Hz-lm-0.6B").strip()
                backend = os.getenv("ACESTEP_LM_BACKEND", "vllm").strip().lower()
                if backend not in {"vllm", "pt", "mlx"}:
                    backend = "vllm"

                lm_model_name = get_model_name(lm_model_path)
                if lm_model_name:
                    try:
                        ensure_model_downloaded(lm_model_name, checkpoint_dir)
                    except Exception as exc:
                        print(f"[API Server] Warning: Failed to download LM model {lm_model_name}: {exc}")

                lm_device = os.getenv("ACESTEP_LM_DEVICE", os.getenv("ACESTEP_DEVICE", "auto"))
                lm_offload = env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False)
                status, ok = llm.initialize(
                    checkpoint_dir=checkpoint_dir,
                    lm_model_path=lm_model_path,
                    backend=backend,
                    device=lm_device,
                    offload_to_cpu=lm_offload,
                    dtype=None,
                )
                if not ok:
                    app.state._llm_init_error = status
                    raise HTTPException(status_code=500, detail=f"LLM init failed: {status}")
                app.state._llm_initialized = True

        prompt = body.get("prompt", "") or ""
        lyrics = body.get("lyrics", "") or ""
        temperature = to_float(body.get("temperature"), 0.85)
        param_obj_str = body.get("param_obj", "{}")
        if isinstance(param_obj_str, dict):
            param_obj = param_obj_str
        else:
            try:
                param_obj = json.loads(param_obj_str) if param_obj_str else {}
            except json.JSONDecodeError:
                param_obj = {}

        duration = to_float(param_obj.get("duration"))
        bpm = to_int(param_obj.get("bpm"))
        key_scale = param_obj.get("key", "") or param_obj.get("key_scale", "") or ""
        time_signature = param_obj.get("time_signature", "") or body.get("time_signature", "") or ""
        language = param_obj.get("language", "") or ""

        user_metadata_for_format: Dict[str, Any] = {}
        if bpm is not None:
            user_metadata_for_format["bpm"] = bpm
        if duration is not None and duration > 0:
            user_metadata_for_format["duration"] = int(duration)
        if key_scale:
            user_metadata_for_format["keyscale"] = key_scale
        if time_signature:
            user_metadata_for_format["timesignature"] = time_signature
        if language and language != "unknown":
            user_metadata_for_format["language"] = language

        try:
            format_result = format_sample(
                llm_handler=llm,
                caption=prompt,
                lyrics=lyrics,
                user_metadata=user_metadata_for_format if user_metadata_for_format else None,
                temperature=temperature,
                use_constrained_decoding=True,
            )
            if not format_result.success:
                error_msg = format_result.error or format_result.status_message
                return wrap_response(None, code=500, error=f"format_sample failed: {error_msg}")

            return wrap_response(
                {
                    "caption": format_result.caption or prompt,
                    "lyrics": format_result.lyrics or lyrics,
                    "bpm": format_result.bpm or bpm,
                    "key_scale": format_result.keyscale or key_scale,
                    "time_signature": format_result.timesignature or time_signature,
                    "duration": format_result.duration or duration,
                    "vocal_language": format_result.language or language or "unknown",
                }
            )
        except Exception as exc:
            return wrap_response(None, code=500, error=f"format_sample error: {str(exc)}")
