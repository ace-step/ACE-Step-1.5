"""LoRA HTTP routes for adapter lifecycle controls."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from acestep.handler import AceStepHandler

_SUCCESS_PREFIX = "\u2705"
_WARNING_PREFIX = "\u26a0\ufe0f"


class LoadLoRARequest(BaseModel):
    """Request payload for loading a LoRA/LoKr adapter."""

    lora_path: str = Field(..., description="Path to LoRA adapter directory or LoKr/LyCORIS safetensors file")
    adapter_name: Optional[str] = Field(default=None, description="Optional adapter name for multi-adapter mode")


class SetLoRAScaleRequest(BaseModel):
    """Request payload for setting LoRA strength."""

    scale: float = Field(..., ge=0.0, le=1.0, description="LoRA scale strength (0.0 to 1.0)")
    adapter_name: Optional[str] = Field(default=None, description="Optional adapter name for multi-adapter mode")


class ToggleLoRARequest(BaseModel):
    """Request payload for enabling/disabling loaded LoRA adapters."""

    use_lora: bool = Field(..., description="Enable or disable LoRA")


def _require_initialized_handler(app: FastAPI) -> AceStepHandler:
    """Return initialized handler or raise HTTP 500 when unavailable."""

    handler: AceStepHandler = app.state.handler
    if handler is None or handler.model is None:
        raise HTTPException(status_code=500, detail="Model not initialized")
    return handler


def _is_success_message(result: str, allow_warning: bool = False) -> bool:
    """Check whether backend operation result is considered successful."""

    if result.startswith(_SUCCESS_PREFIX):
        return True
    return allow_warning and result.startswith(_WARNING_PREFIX)


def register_lora_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[..., Dict[str, Any]],
) -> None:
    """Register LoRA lifecycle endpoints on the provided FastAPI app."""

    @app.post("/v1/lora/load")
    async def load_lora_endpoint(request: LoadLoRARequest, _: None = Depends(verify_api_key)):
        """Load LoRA adapter into the primary model."""

        handler = _require_initialized_handler(app)
        try:
            adapter_name = request.adapter_name.strip() if isinstance(request.adapter_name, str) else None
            if adapter_name:
                result = handler.add_lora(request.lora_path, adapter_name=adapter_name)
            else:
                result = handler.load_lora(request.lora_path)

            if _is_success_message(result):
                response_data: Dict[str, Any] = {"message": result, "lora_path": request.lora_path}
                if adapter_name:
                    response_data["adapter_name"] = adapter_name
                return wrap_response(response_data)
            raise HTTPException(status_code=400, detail=result)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to load LoRA: {str(exc)}")

    @app.post("/v1/lora/unload")
    async def unload_lora_endpoint(_: None = Depends(verify_api_key)):
        """Unload LoRA adapter and restore base model."""

        handler = _require_initialized_handler(app)
        try:
            result = handler.unload_lora()
            if _is_success_message(result, allow_warning=True):
                return wrap_response({"message": result})
            raise HTTPException(status_code=400, detail=result)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to unload LoRA: {str(exc)}")

    @app.post("/v1/lora/toggle")
    async def toggle_lora_endpoint(request: ToggleLoRARequest, _: None = Depends(verify_api_key)):
        """Enable or disable LoRA adapter for inference."""

        handler = _require_initialized_handler(app)
        try:
            result = handler.set_use_lora(request.use_lora)
            if _is_success_message(result):
                return wrap_response({"message": result, "use_lora": request.use_lora})
            return wrap_response(None, code=400, error=result)
        except Exception as exc:
            return wrap_response(None, code=500, error=f"Failed to toggle LoRA: {str(exc)}")

    @app.post("/v1/lora/scale")
    async def set_lora_scale_endpoint(request: SetLoRAScaleRequest, _: None = Depends(verify_api_key)):
        """Set LoRA adapter scale/strength."""

        handler = _require_initialized_handler(app)
        try:
            adapter_name = request.adapter_name.strip() if isinstance(request.adapter_name, str) else None
            if adapter_name:
                result = handler.set_lora_scale(adapter_name, request.scale)
            else:
                result = handler.set_lora_scale(request.scale)

            if _is_success_message(result, allow_warning=True):
                response_data: Dict[str, Any] = {"message": result, "scale": request.scale}
                if adapter_name:
                    response_data["adapter_name"] = adapter_name
                return wrap_response(response_data)
            return wrap_response(None, code=400, error=result)
        except Exception as exc:
            return wrap_response(None, code=500, error=f"Failed to set LoRA scale: {str(exc)}")

    @app.get("/v1/lora/status")
    async def get_lora_status_endpoint(_: None = Depends(verify_api_key)):
        """Get current LoRA/LoKr adapter state for the primary handler."""

        handler = _require_initialized_handler(app)
        status = handler.get_lora_status()
        return wrap_response(
            {
                "lora_loaded": bool(status.get("loaded", getattr(handler, "lora_loaded", False))),
                "use_lora": bool(status.get("active", getattr(handler, "use_lora", False))),
                "lora_scale": float(status.get("scale", getattr(handler, "lora_scale", 1.0))),
                "adapter_type": getattr(handler, "_adapter_type", None),
                "scales": status.get("scales", {}),
                "active_adapter": status.get("active_adapter"),
                "adapters": status.get("adapters", []),
                "synthetic_default_mode": bool(status.get("synthetic_default_mode", False)),
            }
        )
