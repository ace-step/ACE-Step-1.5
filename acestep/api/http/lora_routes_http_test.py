"""HTTP integration tests for LoRA route registration."""

import unittest
from typing import Any, Dict

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api.http.lora_routes import register_lora_routes


def _wrap_response(data: Any, code: int = 200, error: str | None = None) -> Dict[str, Any]:
    """Return response envelope matching API server contract."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Require a fixed bearer token for integration tests."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


class _FakeHandler:
    """Minimal route handler stub used for HTTP integration tests."""

    def __init__(self, model: object | None = None) -> None:
        self.model = model
        self.calls: list[tuple] = []
        self.toggle_result = "\u2705 toggled"

    def add_lora(self, lora_path: str, adapter_name: str | None = None) -> str:
        """Record add_lora calls and return success marker."""

        self.calls.append(("add_lora", lora_path, adapter_name))
        return "\u2705 loaded adapter"

    def load_lora(self, lora_path: str) -> str:
        """Record load_lora calls and return success marker."""

        self.calls.append(("load_lora", lora_path))
        return "\u2705 loaded"

    def unload_lora(self) -> str:
        """Record unload_lora calls and return success marker."""

        self.calls.append(("unload_lora",))
        return "\u2705 unloaded"

    def set_use_lora(self, use_lora: bool) -> str:
        """Record set_use_lora calls and return configurable result."""

        self.calls.append(("set_use_lora", use_lora))
        return self.toggle_result

    def set_lora_scale(self, *args) -> str:
        """Record set_lora_scale calls and return success marker."""

        self.calls.append(("set_lora_scale",) + args)
        return "\u2705 scale set"

    def get_lora_status(self) -> Dict[str, Any]:
        """Return canned LoRA status payload."""

        self.calls.append(("get_lora_status",))
        return {"loaded": True, "active": True, "scale": 0.6, "adapters": ["main"], "scales": {"main": 0.6}}


class LoraRoutesHttpTests(unittest.TestCase):
    """Exercise LoRA endpoints through real TestClient HTTP requests."""

    def _build_client(self, handler: _FakeHandler) -> TestClient:
        """Build a FastAPI app, register routes, and return an HTTP client."""

        app = FastAPI()
        app.state.handler = handler
        register_lora_routes(app=app, verify_api_key=_verify_api_key, wrap_response=_wrap_response)
        return TestClient(app)

    def test_load_lora_post_returns_wrapped_success_payload(self):
        """POST /v1/lora/load should return wrapped response and call add_lora."""

        handler = _FakeHandler(model=object())
        client = self._build_client(handler)

        response = client.post(
            "/v1/lora/load",
            headers={"Authorization": "Bearer test-token"},
            json={"lora_path": "adapter.safetensors", "adapter_name": "main"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("main", payload["data"]["adapter_name"])
        self.assertEqual(("add_lora", "adapter.safetensors", "main"), handler.calls[0])

    def test_toggle_lora_post_preserves_wrapper_400_semantics(self):
        """POST /v1/lora/toggle should keep HTTP 200 with wrapped code=400 on failure."""

        handler = _FakeHandler(model=object())
        handler.toggle_result = "failed to toggle"
        client = self._build_client(handler)

        response = client.post(
            "/v1/lora/toggle",
            headers={"Authorization": "Bearer test-token"},
            json={"use_lora": True},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(400, payload["code"])
        self.assertEqual("failed to toggle", payload["error"])

    def test_status_get_returns_http_500_when_model_not_initialized(self):
        """GET /v1/lora/status should return HTTP 500 when handler model is missing."""

        handler = _FakeHandler(model=None)
        client = self._build_client(handler)

        response = client.get("/v1/lora/status", headers={"Authorization": "Bearer test-token"})

        self.assertEqual(500, response.status_code)
        self.assertEqual("Model not initialized", response.json()["detail"])

    def test_requests_require_authorization_header(self):
        """GET /v1/lora/status without token should return HTTP 401 from dependency."""

        handler = _FakeHandler(model=object())
        client = self._build_client(handler)

        response = client.get("/v1/lora/status")

        self.assertEqual(401, response.status_code)
        self.assertEqual("Unauthorized", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
