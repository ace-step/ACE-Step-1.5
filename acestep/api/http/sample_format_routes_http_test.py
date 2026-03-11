"""HTTP integration tests for sample/format routes."""

import threading
import unittest
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from acestep.api.http.sample_format_routes import register_sample_format_routes


def _wrap_response(data, code=200, error=None):
    """Return an ``api_server``-compatible response envelope dict."""

    return {"data": data, "code": code, "error": error}


def _verify_token_from_request(body: dict, authorization: str | None = None) -> None:
    """Validate fixed bearer/body token for integration tests."""

    if (body or {}).get("ai_token") == "test-token":
        return
    if authorization == "Bearer test-token":
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


class _FakeLlm:
    """Minimal fake LLM handler for format endpoint HTTP tests."""

    llm_initialized = True

    def initialize(self, **_kwargs):
        """Return successful initialization tuple."""

        self.llm_initialized = True
        return "ok", True


class SampleFormatRoutesHttpTests(unittest.TestCase):
    """Integration tests covering real HTTP calls for sample/format routes."""

    def _build_client(self) -> TestClient:
        """Create app and register sample/format routes."""

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
            simple_example_data=[{"mode": "simple", "seed": 1}],
            custom_example_data=[{"mode": "custom", "seed": 2}],
            format_sample=lambda **_kwargs: SimpleNamespace(
                success=True,
                caption="c",
                lyrics="l",
                bpm=100,
                keyscale="C",
                timesignature="4/4",
                duration=8,
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
        return TestClient(app)

    def test_create_random_sample_requires_auth(self):
        """POST /create_random_sample should return 401 when auth is missing."""

        client = self._build_client()
        response = client.post("/create_random_sample", json={"sample_type": "simple_mode"})
        self.assertEqual(401, response.status_code)

    def test_create_random_sample_returns_wrapped_payload(self):
        """POST /create_random_sample should return wrapped payload when authorized."""

        client = self._build_client()
        response = client.post(
            "/create_random_sample",
            json={"ai_token": "test-token", "sample_type": "simple_mode"},
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("simple", payload["data"]["mode"])

    def test_format_input_returns_wrapped_payload(self):
        """POST /format_input should return wrapped formatted response."""

        client = self._build_client()
        response = client.post(
            "/format_input",
            json={"ai_token": "test-token", "prompt": "p", "lyrics": "l", "param_obj": {"bpm": 100}},
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("c", payload["data"]["caption"])


if __name__ == "__main__":
    unittest.main()
