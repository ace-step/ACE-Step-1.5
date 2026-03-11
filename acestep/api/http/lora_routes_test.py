"""Unit tests for LoRA route registration and endpoint behavior."""

import asyncio
import unittest
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute

from acestep.api.http.lora_routes import (
    LoadLoRARequest,
    SetLoRAScaleRequest,
    ToggleLoRARequest,
    register_lora_routes,
)


def _wrap_response(data: Any, code: int = 200, error: str | None = None) -> Dict[str, Any]:
    """Return response envelope matching api_server wrapper contract."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(_: str | None = None) -> None:
    """Test no-op auth dependency."""

    return None


def _get_route_endpoint(app: FastAPI, path: str, method: str):
    """Resolve route endpoint callable by path and HTTP method."""

    method = method.upper()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")


class _FakeHandler:
    """Minimal handler stub for LoRA route tests."""

    def __init__(self, model: object | None = None) -> None:
        self.model = model
        self.calls: list[tuple] = []
        self.lora_loaded = False
        self.use_lora = False
        self.lora_scale = 1.0
        self._adapter_type = "lora"
        self.scale_result = "\u2705 scale set"

    def add_lora(self, lora_path: str, adapter_name: str | None = None) -> str:
        self.calls.append(("add_lora", lora_path, adapter_name))
        return "\u2705 loaded adapter"

    def load_lora(self, lora_path: str) -> str:
        self.calls.append(("load_lora", lora_path))
        return "\u2705 loaded"

    def unload_lora(self) -> str:
        self.calls.append(("unload_lora",))
        return "\u2705 unloaded"

    def set_use_lora(self, use_lora: bool) -> str:
        self.calls.append(("set_use_lora", use_lora))
        return "failed to toggle"

    def set_lora_scale(self, *args) -> str:
        self.calls.append(("set_lora_scale",) + args)
        return self.scale_result

    def get_lora_status(self) -> Dict[str, Any]:
        self.calls.append(("get_lora_status",))
        return {"loaded": True, "active": True, "scale": 0.6, "adapters": ["main"], "scales": {"main": 0.6}}


class LoraRoutesTests(unittest.TestCase):
    """Behavior tests for the extracted LoRA endpoint registration module."""

    def _build_app(self, handler: _FakeHandler) -> FastAPI:
        """Create test app and register LoRA routes with stubs."""

        app = FastAPI()
        app.state.handler = handler
        register_lora_routes(app=app, verify_api_key=_verify_api_key, wrap_response=_wrap_response)
        return app

    def test_load_route_uses_add_lora_when_adapter_name_present(self):
        """Load endpoint should route named adapters through add_lora()."""

        handler = _FakeHandler(model=object())
        app = self._build_app(handler)
        endpoint = _get_route_endpoint(app, "/v1/lora/load", "POST")

        payload = LoadLoRARequest(lora_path="adapter.safetensors", adapter_name="main")
        result = asyncio.run(endpoint(payload, None))

        self.assertEqual(("add_lora", "adapter.safetensors", "main"), handler.calls[0])
        self.assertEqual(200, result["code"])
        self.assertEqual("main", result["data"]["adapter_name"])

    def test_status_route_raises_when_model_not_initialized(self):
        """Status endpoint should reject requests when model is unavailable."""

        handler = _FakeHandler(model=None)
        app = self._build_app(handler)
        endpoint = _get_route_endpoint(app, "/v1/lora/status", "GET")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(endpoint(None))

        self.assertEqual(500, ctx.exception.status_code)
        self.assertIn("Model not initialized", str(ctx.exception.detail))

    def test_scale_route_accepts_warning_prefix_as_success(self):
        """Scale endpoint should treat warning-prefixed responses as success."""

        handler = _FakeHandler(model=object())
        handler.scale_result = "\u26a0\ufe0f using fallback adapter"
        app = self._build_app(handler)
        endpoint = _get_route_endpoint(app, "/v1/lora/scale", "POST")

        payload = SetLoRAScaleRequest(scale=0.42)
        result = asyncio.run(endpoint(payload, None))

        self.assertEqual(200, result["code"])
        self.assertEqual(0.42, result["data"]["scale"])

    def test_toggle_route_returns_400_wrapper_for_non_success_message(self):
        """Toggle endpoint should map non-success handler responses to code 400."""

        handler = _FakeHandler(model=object())
        app = self._build_app(handler)
        endpoint = _get_route_endpoint(app, "/v1/lora/toggle", "POST")

        payload = ToggleLoRARequest(use_lora=True)
        result = asyncio.run(endpoint(payload, None))

        self.assertEqual(400, result["code"])
        self.assertEqual("failed to toggle", result["error"])


if __name__ == "__main__":
    unittest.main()
