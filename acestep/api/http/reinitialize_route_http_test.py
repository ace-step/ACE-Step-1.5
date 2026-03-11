"""HTTP integration tests for the /v1/reinitialize route."""

from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api.http.reinitialize_route import register_reinitialize_route

_NON_EXISTENT_TEST_ROOT = str(Path.cwd() / "non-existent-test-root")


def _wrap_response(data, code=200, error=None):
    """Return an ``api_server``-compatible response envelope dict."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Validate a fixed bearer token and return ``None`` on success."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


class ReinitializeRouteHttpTests(unittest.TestCase):
    """Integration tests for reinitialize route using real HTTP requests."""

    def _build_client(self, handler) -> TestClient:
        """Create a test app with route registration and return TestClient."""

        app = FastAPI()
        app.state.handler = handler
        app.state.llm_handler = SimpleNamespace(llm_initialized=True)
        register_reinitialize_route(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            env_bool=lambda *_: False,
            get_project_root=lambda: _NON_EXISTENT_TEST_ROOT,
        )
        return TestClient(app)

    def test_missing_handler_returns_raw_http_500_contract(self):
        """POST /v1/reinitialize should preserve legacy raw HTTP 500 when handler is missing."""

        app = FastAPI()
        app.state.handler = None
        app.state.llm_handler = SimpleNamespace(llm_initialized=True)
        register_reinitialize_route(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            env_bool=lambda *_: False,
            get_project_root=lambda: _NON_EXISTENT_TEST_ROOT,
        )
        client = TestClient(app)
        response = client.post("/v1/reinitialize", headers={"Authorization": "Bearer test-token"})

        self.assertEqual(500, response.status_code)
        payload = response.json()
        self.assertEqual("Service not initialized", payload["detail"])

    def test_requires_authentication(self):
        """POST /v1/reinitialize without token should return HTTP 401."""

        handler = SimpleNamespace(model=object(), vae=object(), text_encoder=object(), last_init_params=None)
        client = self._build_client(handler)
        response = client.post("/v1/reinitialize")
        self.assertEqual(401, response.status_code)

    def test_returns_wrapped_success_payload(self):
        """POST /v1/reinitialize should return wrapped success payload when initialized."""

        handler = SimpleNamespace(model=object(), vae=object(), text_encoder=object(), last_init_params=None)
        client = self._build_client(handler)
        with mock.patch("acestep.api.http.reinitialize_route.torch.cuda.is_available", return_value=False):
            response = client.post("/v1/reinitialize", headers={"Authorization": "Bearer test-token"})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertIn("Service reinitialized", payload["data"]["message"])


if __name__ == "__main__":
    unittest.main()
