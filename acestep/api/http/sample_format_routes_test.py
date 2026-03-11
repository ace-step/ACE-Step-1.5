"""Unit tests for sample/format route registration."""

import asyncio
import json
import threading
import unittest
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute

from acestep.api.http.sample_format_routes import register_sample_format_routes


def _wrap_response(data, code=200, error=None):
    """Return an ``api_server``-compatible response envelope dict."""

    return {"data": data, "code": code, "error": error}


def _verify_token_from_request(body: dict, authorization: str | None = None) -> None:
    """Validate a fixed token from body or Authorization header for unit tests."""

    token = (body or {}).get("ai_token")
    if token == "test-token":
        return
    if authorization == "Bearer test-token":
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def _get_endpoint(app: FastAPI, path: str, method: str):
    """Return endpoint callable matching a route path/method pair."""

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods:
            return route.endpoint
    raise AssertionError(f"Missing route: {method} {path}")


class _FakeLlm:
    """Minimal fake LLM handler used by format route tests."""

    def __init__(self) -> None:
        """Initialize fake handler state."""

        self.llm_initialized = False

    def initialize(self, **_kwargs):
        """Return successful initialization tuple."""

        self.llm_initialized = True
        return "ok", True


class SampleFormatRoutesTests(unittest.TestCase):
    """Behavior tests for sample and format route registration helpers."""

    def _build_app(self) -> FastAPI:
        """Create app state and register sample/format routes for tests."""

        app = FastAPI()
        app.state.llm_handler = _FakeLlm()
        app.state._llm_init_lock = threading.Lock()
        app.state._llm_initialized = True
        app.state._llm_init_error = None
        app.state._llm_lazy_load_disabled = False
        register_sample_format_routes(
            app=app,
            verify_token_from_request=_verify_token_from_request,
            wrap_response=_wrap_response,
            simple_example_data=[{"mode": "simple", "x": 1}],
            custom_example_data=[{"mode": "custom", "x": 2}],
            format_sample=lambda **_kwargs: SimpleNamespace(
                success=True,
                caption="formatted-caption",
                lyrics="formatted-lyrics",
                bpm=120,
                keyscale="C",
                timesignature="4/4",
                duration=10,
                language="en",
                error=None,
                status_message=None,
            ),
            get_project_root=lambda: "/tmp/non-existent",
            get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
            ensure_model_downloaded=lambda *_: "",
            env_bool=lambda *_: False,
            to_int=lambda v, d=None: int(v) if v is not None else d,
            to_float=lambda v, d=None: float(v) if v is not None else d,
        )
        return app

    def test_create_random_sample_returns_simple_payload(self):
        """Random sample endpoint should return wrapped random simple-mode payload."""

        app = self._build_app()
        endpoint = _get_endpoint(app, "/create_random_sample", "POST")
        request = SimpleNamespace(headers={"content-type": "application/json"}, json=lambda: {"ai_token": "test-token"})

        async def _json():
            """Return a deterministic JSON payload for this unit test."""

            return {"ai_token": "test-token", "sample_type": "simple_mode"}

        request.json = _json

        result = asyncio.run(endpoint(request, None))

        self.assertEqual(200, result["code"])
        self.assertEqual("simple", result["data"]["mode"])

    def test_format_input_returns_wrapped_success_payload(self):
        """Format endpoint should return wrapped formatted fields on success."""

        app = self._build_app()
        endpoint = _get_endpoint(app, "/format_input", "POST")

        async def _json():
            """Return a deterministic format-input JSON body for this test."""

            return {"ai_token": "test-token", "prompt": "p", "lyrics": "l", "param_obj": json.dumps({"bpm": 100})}

        request = SimpleNamespace(headers={"content-type": "application/json"}, json=_json)
        result = asyncio.run(endpoint(request, None))

        self.assertEqual(200, result["code"])
        self.assertEqual("formatted-caption", result["data"]["caption"])

    def test_format_input_raises_503_when_lazy_load_disabled(self):
        """Format endpoint should preserve 503 contract when lazy loading is disabled."""

        app = self._build_app()
        app.state._llm_initialized = False
        app.state._llm_lazy_load_disabled = True
        endpoint = _get_endpoint(app, "/format_input", "POST")

        async def _json():
            """Return a minimal format-input JSON body for lazy-load test."""

            return {"ai_token": "test-token", "prompt": "p", "lyrics": "l"}

        request = SimpleNamespace(headers={"content-type": "application/json"}, json=_json)

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(endpoint(request, None))
        self.assertEqual(503, ctx.exception.status_code)


if __name__ == "__main__":
    unittest.main()
