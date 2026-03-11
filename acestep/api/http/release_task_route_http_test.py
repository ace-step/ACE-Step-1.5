"""HTTP integration tests for release-task route registration."""

import asyncio
import time
import unittest
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from acestep.api.http.release_task_route import register_release_task_route


class _FakeParser:
    """Minimal parser stub exposing typed accessors used by route dependencies."""

    def __init__(self, values: dict) -> None:
        """Store deterministic key/value pairs for parser methods."""

        self._values = values

    def get(self, key: str):
        """Return raw value for ``key`` from parser payload."""

        return self._values.get(key)

    def str(self, key: str, default: str = "") -> str:
        """Return string value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        return default if value is None else str(value)

    def bool(self, key: str, default: bool = False) -> bool:
        """Return boolean value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def int(self, key: str, default=None):
        """Return integer value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        return default if value is None else int(value)

    def float(self, key: str, default=None):
        """Return float value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        return default if value is None else float(value)


class _FakeStore:
    """Minimal job-store fake returning deterministic job IDs."""

    def __init__(self) -> None:
        """Initialize deterministic record counter."""

        self._counter = 0

    def create(self):
        """Return next deterministic record with ``job_id`` attribute."""

        self._counter += 1
        return SimpleNamespace(job_id=f"job-{self._counter}")


class ReleaseTaskRouteHttpTests(unittest.TestCase):
    """Integration tests covering real HTTP calls for `/release_task`."""

    def _build_client(self, queue_maxsize: int = 8) -> TestClient:
        """Build app and register release-task route with deterministic fakes."""

        app = FastAPI()
        app.state.job_queue = asyncio.Queue(maxsize=queue_maxsize)
        app.state.job_temp_files = {}
        app.state.pending_ids = []
        app.state.job_temp_files_lock = asyncio.Lock()
        app.state.pending_lock = asyncio.Lock()
        store = _FakeStore()

        def _verify_token_from_request(body: dict, authorization: str | None = None) -> None:
            """Require fixed token either in body or Authorization header."""

            if (body or {}).get("ai_token") == "test-token":
                return
            if authorization == "Bearer test-token":
                return
            raise HTTPException(status_code=401, detail="Unauthorized")

        def _wrap_response(data, code=200, error=None):
            """Return an ``api_server``-compatible response envelope dict."""

            return {
                "data": data,
                "code": code,
                "error": error,
                "timestamp": int(time.time() * 1000),
                "extra": None,
            }

        register_release_task_route(
            app=app,
            verify_token_from_request=_verify_token_from_request,
            wrap_response=_wrap_response,
            store=store,
            request_parser_cls=_FakeParser,
            request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
            validate_audio_path=lambda path: path,
            save_upload_to_temp=lambda *_args, **_kwargs: "",
            upload_file_type=type("Upload", (), {}),
            default_dit_instruction="default-instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
        )
        return TestClient(app)

    def test_release_task_requires_auth(self):
        """POST /release_task should return HTTP 401 when auth token is missing."""

        client = self._build_client()
        response = client.post("/release_task", json={"prompt": "hello"})
        self.assertEqual(401, response.status_code)

    def test_release_task_returns_wrapped_queue_response(self):
        """POST /release_task should enqueue job and return wrapped queued payload."""

        client = self._build_client()
        response = client.post("/release_task", json={"ai_token": "test-token", "prompt": "hello"})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("queued", payload["data"]["status"])
        self.assertEqual(1, payload["data"]["queue_position"])
        self.assertIn("timestamp", payload)

    def test_release_task_returns_429_when_queue_is_full(self):
        """POST /release_task should return HTTP 429 when queue capacity is exhausted."""

        client = self._build_client(queue_maxsize=1)
        first = client.post("/release_task", json={"ai_token": "test-token", "prompt": "first"})
        self.assertEqual(200, first.status_code)

        second = client.post("/release_task", json={"ai_token": "test-token", "prompt": "second"})
        self.assertEqual(429, second.status_code)
        self.assertEqual("Server busy: queue is full", second.json()["detail"])

    def test_release_task_rejects_unsupported_content_type(self):
        """POST /release_task should return HTTP 415 for unsupported content type."""

        client = self._build_client()
        response = client.post(
            "/release_task",
            headers={"Content-Type": "text/plain"},
            content="hello world",
        )
        self.assertEqual(415, response.status_code)
        self.assertIn("Unsupported Content-Type", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
