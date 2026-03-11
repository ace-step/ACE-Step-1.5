"""HTTP integration tests for training API route registration."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Optional
import unittest
from unittest import mock

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api.train_api_service import register_training_api_routes


def _wrap_response(data: Any, code: int = 200, error: Optional[str] = None) -> Dict[str, Any]:
    """Return API-compatible response envelope for tests."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Require fixed bearer token for test requests."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


@contextmanager
def _temporary_llm_model(_app: FastAPI, _llm: Any, _lm_model_path: Optional[str]):
    """No-op context manager used by dataset routes during registration."""

    yield


class TrainingApiServiceHttpTests(unittest.TestCase):
    """HTTP tests covering core training service routes."""

    def _build_client(self) -> tuple[TestClient, dict[str, int], FastAPI]:
        """Build app/client pair with deterministic route dependencies."""

        app = FastAPI()
        calls = {"stop_tensorboard": 0}

        def _start_tensorboard(_app: FastAPI, _logdir: str) -> Optional[str]:
            """Return fixed tensorboard URL."""

            return "http://localhost:6006"

        def _stop_tensorboard(_app: FastAPI) -> None:
            """Record stop callback invocations."""

            calls["stop_tensorboard"] += 1

        register_training_api_routes(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            start_tensorboard=_start_tensorboard,
            stop_tensorboard=_stop_tensorboard,
            temporary_llm_model=_temporary_llm_model,
            atomic_write_json=lambda _path, _payload: None,
            append_jsonl=lambda _path, _record: None,
        )
        return TestClient(app), calls, app

    def test_training_status_requires_auth(self):
        """GET /v1/training/status should return 401 when auth is missing."""

        client, _calls, _app = self._build_client()
        response = client.get("/v1/training/status")
        self.assertEqual(401, response.status_code)

    def test_training_status_returns_wrapped_payload(self):
        """GET /v1/training/status should return wrapped status payload when authorized."""

        client, _calls, _app = self._build_client()
        response = client.get("/v1/training/status", headers={"Authorization": "Bearer test-token"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertIsNone(payload["error"])
        self.assertIn("is_training", payload["data"])
        self.assertIn("status", payload["data"])

    def test_training_stop_sets_should_stop_and_calls_tensorboard_stop(self):
        """POST /v1/training/stop should set stop flag and call stop callback when training."""

        client, calls, app = self._build_client()
        app.state.training_state = {
            "is_training": True,
            "should_stop": False,
            "status": "Running",
        }
        response = client.post("/v1/training/stop", headers={"Authorization": "Bearer test-token"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("Stopping training...", payload["data"]["message"])
        self.assertEqual(1, calls["stop_tensorboard"])
        self.assertTrue(app.state.training_state["should_stop"])

    def test_training_stop_returns_idle_message_when_not_training(self):
        """POST /v1/training/stop should return idle message when no training is active."""

        client, calls, app = self._build_client()
        app.state.training_state = {
            "is_training": False,
            "should_stop": False,
            "status": "Idle",
        }
        response = client.post("/v1/training/stop", headers={"Authorization": "Bearer test-token"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("No training in progress", payload["data"]["message"])
        self.assertEqual(1, calls["stop_tensorboard"])

    def test_load_tensor_info_returns_400_for_missing_dir(self):
        """POST /v1/training/load_tensor_info should return HTTP 400 for missing directory."""

        client, _calls, _app = self._build_client()
        with mock.patch("acestep.api.train_api_service.os.path.exists", return_value=False):
            response = client.post(
                "/v1/training/load_tensor_info",
                json={"tensor_dir": "missing-dir"},
                headers={"Authorization": "Bearer test-token"},
            )

        self.assertEqual(400, response.status_code)
        self.assertIn("Directory not found", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
