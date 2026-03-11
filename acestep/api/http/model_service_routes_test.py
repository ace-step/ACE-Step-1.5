"""Unit tests for model service route registration helpers."""

import asyncio
import os
import queue
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI
from fastapi.routing import APIRoute

from acestep.api.http.model_service_routes import (
    InitModelRequest,
    _collect_model_inventory,
    register_model_service_routes,
)


def _wrap_response(data, code=200, error=None):
    """Return an ``api_server``-compatible response envelope dict."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(_: str | None = None) -> None:
    """Return ``None`` as a no-op auth dependency for unit tests."""

    return None


def _get_endpoint(app: FastAPI, path: str, method: str):
    """Return the endpoint callable matching ``path`` and HTTP ``method``."""

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods:
            return route.endpoint
    raise AssertionError(f"Missing route: {method} {path}")


class _FakeStore:
    """Small fake store for stats route registration dependencies."""

    def get_stats(self):
        """Return deterministic job stats payload mapping."""

        return {"total": 0, "queued": 0, "running": 0, "succeeded": 0, "failed": 0}


class ModelServiceRoutesTests(unittest.TestCase):
    """Unit-level behavior tests for model service route module."""

    def _build_app(self) -> FastAPI:
        """Create app with minimal state required by registered routes."""

        app = FastAPI()
        app.state._config_path = "acestep-v15-base"
        app.state._config_path2 = ""
        app.state._config_path3 = ""
        app.state._initialized = True
        app.state._initialized2 = False
        app.state._initialized3 = False
        app.state._llm_initialized = True
        app.state.llm_handler = SimpleNamespace(last_init_params={"lm_model_path": "acestep-5Hz-lm-1.7B"})
        app.state._llm_lazy_load_disabled = False
        app.state._init_lock = asyncio.Lock()
        app.state.executor = None
        app.state.stats_lock = asyncio.Lock()
        app.state.avg_job_seconds = 3.5
        app.state.job_queue = queue.Queue()
        app.state.handler = SimpleNamespace()
        app.state._llm_init_lock = mock.MagicMock()
        register_model_service_routes(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            store=_FakeStore(),
            queue_maxsize=200,
            initial_avg_job_seconds=5.0,
            get_project_root=lambda: "/tmp/non-existent",
            get_model_name=lambda p: os.path.basename(str(p).rstrip("/\\")),
            ensure_model_downloaded=lambda *_: "",
            env_bool=lambda *_: False,
        )
        return app

    def test_collect_model_inventory_merges_loaded_and_available_models(self):
        """Inventory helper should include loaded default model and discovered models."""

        app = self._build_app()
        with mock.patch("acestep.api.http.model_service_routes.os.path.isdir", return_value=True), mock.patch(
            "acestep.api.http.model_service_routes.os.listdir",
            return_value=["acestep-v15-base", "acestep-v15-turbo", "acestep-5Hz-lm-1.7B"],
        ):
            inventory = _collect_model_inventory(
                app=app,
                get_project_root=lambda: "/fake/project",
                get_model_name=lambda p: os.path.basename(str(p).rstrip("/\\")),
            )

        names = [m["name"] for m in inventory["models"]]
        self.assertIn("acestep-v15-base", names)
        self.assertIn("acestep-v15-turbo", names)
        self.assertEqual("acestep-v15-base", inventory["default_model"])
        self.assertTrue(inventory["llm_initialized"])

    def test_init_route_wraps_initializer_exception(self):
        """Init endpoint should convert initializer exceptions into wrapped code=500 payloads."""

        app = self._build_app()
        endpoint = _get_endpoint(app, "/v1/init", "POST")
        request = InitModelRequest(model="acestep-v15-base", init_llm=False, lm_model_path=None)

        with mock.patch("acestep.api.http.model_service_routes.initialize_models_for_request", side_effect=RuntimeError("boom")):
            result = asyncio.run(endpoint(request, None))

        self.assertEqual(500, result["code"])
        self.assertIn("Model initialization failed", result["error"])


if __name__ == "__main__":
    unittest.main()
