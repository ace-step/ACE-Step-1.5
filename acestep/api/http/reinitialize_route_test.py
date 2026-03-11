"""Unit tests for reinitialize route registration."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute

from acestep.api.http.reinitialize_route import register_reinitialize_route


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


class ReinitializeRouteUnitTests(unittest.TestCase):
    """Unit tests for reinitialize route behavior and error handling."""

    def test_raises_http_500_when_service_not_initialized(self):
        """Handler absence should return HTTP 500 via raised HTTPException."""

        app = FastAPI()
        app.state.handler = None
        app.state.llm_handler = None
        app.state._llm_lazy_load_disabled = False
        register_reinitialize_route(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            env_bool=lambda *_: False,
            get_project_root=lambda: "/tmp/non-existent",
        )
        endpoint = _get_endpoint(app, "/v1/reinitialize", "POST")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(endpoint(None))
        self.assertEqual(500, ctx.exception.status_code)

    def test_missing_llm_handler_returns_wrapped_success(self):
        """Missing llm_handler should still preserve legacy wrapped-success behavior."""

        app = FastAPI()
        app.state.handler = SimpleNamespace(model=object(), vae=object(), text_encoder=object(), last_init_params=None)
        app.state.llm_handler = None
        app.state._llm_lazy_load_disabled = False
        register_reinitialize_route(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            env_bool=lambda *_: False,
            get_project_root=lambda: "/tmp/non-existent",
        )
        endpoint = _get_endpoint(app, "/v1/reinitialize", "POST")

        with mock.patch("acestep.api.http.reinitialize_route.torch.cuda.is_available", return_value=False):
            result = asyncio.run(endpoint(None))

        self.assertEqual(200, result["code"])
        self.assertIn("Service reinitialized", result["data"]["message"])

    def test_returns_wrapped_success_when_no_reload_needed(self):
        """Initialized handler/LLM should return wrapped success without reload entries."""

        app = FastAPI()
        app.state.handler = SimpleNamespace(
            model=object(),
            vae=object(),
            text_encoder=object(),
            last_init_params=None,
        )
        app.state.llm_handler = SimpleNamespace(llm_initialized=True)
        app.state._llm_lazy_load_disabled = False
        register_reinitialize_route(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            env_bool=lambda *_: False,
            get_project_root=lambda: "/tmp/non-existent",
        )
        endpoint = _get_endpoint(app, "/v1/reinitialize", "POST")

        with mock.patch("acestep.api.http.reinitialize_route.torch.cuda.is_available", return_value=False):
            result = asyncio.run(endpoint(None))

        self.assertEqual(200, result["code"])
        self.assertIn("Service reinitialized", result["data"]["message"])

    def test_handler_reload_failure_keeps_wrapped_success_contract(self):
        """Failed handler reload should not crash endpoint or change wrapper contract."""

        app = FastAPI()
        app.state.handler = SimpleNamespace(
            model=None,
            vae=None,
            text_encoder=None,
            last_init_params={
                "project_root": ".",
                "config_path": "acestep-v15-base",
                "device": "auto",
                "use_flash_attention": True,
                "compile_model": False,
                "offload_to_cpu": False,
                "offload_dit_to_cpu": False,
            },
            initialize_service=lambda **_kwargs: ("failed", False),
        )
        app.state.llm_handler = SimpleNamespace(llm_initialized=True)
        app.state._llm_lazy_load_disabled = False
        register_reinitialize_route(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            env_bool=lambda *_: False,
            get_project_root=lambda: "/tmp/non-existent",
        )
        endpoint = _get_endpoint(app, "/v1/reinitialize", "POST")

        with mock.patch("acestep.api.http.reinitialize_route.torch.cuda.is_available", return_value=False):
            result = asyncio.run(endpoint(None))

        self.assertEqual(200, result["code"])
        self.assertIn("Service reinitialized", result["data"]["message"])


if __name__ == "__main__":
    unittest.main()
