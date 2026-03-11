"""HTTP integration tests for model service routes."""

import asyncio
import queue
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api.http.model_service_routes import register_model_service_routes


def _wrap_response(data, code=200, error=None):
    """Return an ``api_server``-compatible response envelope dict."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Validate a fixed bearer token and return ``None`` on success."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


class _FakeStore:
    """Fake job store implementation for stats endpoint tests."""

    def get_stats(self):
        """Return deterministic job stats as a mapping payload."""

        return {"total": 2, "queued": 1, "running": 1, "succeeded": 0, "failed": 0}


class _FakeHandler:
    """Minimal fake DiT handler for /v1/init route wiring."""

    def initialize_service(self, **_kwargs):
        """Return ``(\"ok\", True)`` to emulate a successful DiT initialization."""

        return "ok", True


class _FakeLlm:
    """Minimal fake LLM handler for route state access."""

    last_init_params = None

    def initialize(self, **_kwargs):
        """Return ``(\"ok\", True)`` for init_llm success paths."""

        return "ok", True


class _FailingLlm:
    """Minimal fake LLM handler that fails initialization."""

    last_init_params = None

    def initialize(self, **_kwargs):
        """Return ``(\"llm-failed\", False)`` for LLM failure-path tests."""

        return "llm-failed", False


class ModelServiceRoutesHttpTests(unittest.TestCase):
    """Integration tests covering real HTTP requests for model service routes."""

    def _build_client(self, llm_handler=None) -> TestClient:
        """Create a route-wired app and return ``TestClient`` for HTTP assertions."""

        app = FastAPI()
        app.state._config_path = "acestep-v15-base"
        app.state._config_path2 = ""
        app.state._config_path3 = ""
        app.state._initialized = True
        app.state._initialized2 = False
        app.state._initialized3 = False
        app.state._llm_initialized = False
        app.state._llm_init_error = None
        app.state._llm_lazy_load_disabled = False
        app.state.llm_handler = llm_handler or _FakeLlm()
        app.state.handler = _FakeHandler()
        app.state._init_lock = asyncio.Lock()
        app.state._llm_init_lock = threading.Lock()
        app.state.stats_lock = asyncio.Lock()
        app.state.avg_job_seconds = 4.2
        app.state.job_queue = queue.Queue()
        app.state.executor = None
        register_model_service_routes(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            store=_FakeStore(),
            queue_maxsize=200,
            initial_avg_job_seconds=5.0,
            get_project_root=lambda: "/tmp/non-existent",
            get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
            ensure_model_downloaded=lambda *_: "",
            env_bool=lambda *_: False,
        )
        return TestClient(app)

    def test_stats_requires_authentication(self):
        """GET /v1/stats without token should return HTTP 401."""

        client = self._build_client()
        response = client.get("/v1/stats")
        self.assertEqual(401, response.status_code)

    def test_models_requires_authentication(self):
        """GET /v1/models without token should return HTTP 401."""

        client = self._build_client()
        response = client.get("/v1/models")
        self.assertEqual(401, response.status_code)

    def test_model_inventory_requires_authentication(self):
        """GET /v1/model_inventory without token should return HTTP 401."""

        client = self._build_client()
        response = client.get("/v1/model_inventory")
        self.assertEqual(401, response.status_code)

    def test_init_requires_authentication(self):
        """POST /v1/init without token should return HTTP 401."""

        client = self._build_client()
        response = client.post("/v1/init", json={"model": "acestep-v15-base", "init_llm": False})
        self.assertEqual(401, response.status_code)

    def test_health_returns_wrapped_payload(self):
        """GET /health should return wrapped status payload with service marker."""

        client = self._build_client()
        response = client.get("/health")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("ACE-Step API", payload["data"]["service"])

    def test_init_route_returns_wrapped_success(self):
        """POST /v1/init should return wrapped success payload."""

        client = self._build_client()
        with mock.patch(
            "acestep.api.http.model_service_routes.initialize_models_for_request",
            return_value={"loaded_model": "acestep-v15-base", "loaded_lm_model": None},
        ):
            response = client.post(
                "/v1/init",
                headers={"Authorization": "Bearer test-token"},
                json={"model": "acestep-v15-base", "init_llm": False},
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("Model initialization completed", payload["data"]["message"])

    def test_init_route_returns_wrapped_error_when_initializer_fails(self):
        """POST /v1/init should preserve wrapped code=500 contract on init failures."""

        client = self._build_client()
        with mock.patch(
            "acestep.api.http.model_service_routes.initialize_models_for_request",
            side_effect=RuntimeError("boom"),
        ):
            response = client.post(
                "/v1/init",
                headers={"Authorization": "Bearer test-token"},
                json={"model": "acestep-v15-base", "init_llm": False},
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(500, payload["code"])
        self.assertIn("Model initialization failed", payload["error"])

    def test_init_route_returns_wrapped_error_when_llm_init_fails(self):
        """POST /v1/init with init_llm should wrap LLM initialization failures."""

        client = self._build_client(llm_handler=_FailingLlm())
        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            response = client.post(
                "/v1/init",
                headers={"Authorization": "Bearer test-token"},
                json={"model": "acestep-v15-base", "init_llm": True, "lm_model_path": "acestep-5Hz-lm-0.6B"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(500, payload["code"])
        self.assertIn("LLM init failed", payload["error"])


if __name__ == "__main__":
    unittest.main()
