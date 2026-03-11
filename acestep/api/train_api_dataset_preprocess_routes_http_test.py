"""HTTP integration tests for dataset preprocess routes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional
import unittest

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api import train_api_models
from acestep.api.train_api_dataset_preprocess_routes import register_training_dataset_preprocess_routes


def _wrap_response(data: Any, code: int = 200, error: Optional[str] = None) -> Dict[str, Any]:
    """Return API-compatible response envelope for tests."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Require fixed bearer token for test requests."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


class _Sample:
    """Minimal sample test double for preprocess route logic."""

    def __init__(self, labeled: bool) -> None:
        """Store labeled marker consumed by preprocess route filtering."""

        self.labeled = labeled


class _Builder:
    """Dataset builder test double for preprocess route behavior."""

    def __init__(self, samples: list[_Sample]) -> None:
        """Initialize deterministic sample list."""

        self.samples = samples

    def preprocess_to_tensors(self, **_kwargs: Any) -> tuple[list[str], str]:
        """Return deterministic preprocess success payload."""

        return ["tensor-1.pt"], "✅ preprocessed"


class TrainApiDatasetPreprocessRoutesHttpTests(unittest.TestCase):
    """HTTP tests covering extracted preprocess route behavior."""

    def setUp(self) -> None:
        """Reset preprocess task registries before each test."""

        with train_api_models._preprocess_lock:
            train_api_models._preprocess_tasks.clear()
            train_api_models._preprocess_latest_task_id = None

    def tearDown(self) -> None:
        """Reset preprocess task registries after each test."""

        with train_api_models._preprocess_lock:
            train_api_models._preprocess_tasks.clear()
            train_api_models._preprocess_latest_task_id = None

    def _build_client(self, samples: list[_Sample]) -> TestClient:
        """Create app/client pair with lightweight preprocess dependencies."""

        app = FastAPI()
        app.state.dataset_builder = _Builder(samples=samples)
        app.state.handler = SimpleNamespace(model=object())
        app.state.llm_handler = SimpleNamespace(llm_initialized=True)
        register_training_dataset_preprocess_routes(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
        )
        return TestClient(app)

    def test_preprocess_async_returns_zero_total_when_no_labeled_samples(self) -> None:
        """POST /v1/dataset/preprocess_async should return zero total when no samples are labeled."""

        client = self._build_client(samples=[_Sample(labeled=False)])
        response = client.post(
            "/v1/dataset/preprocess_async",
            json={"output_dir": "out"},
            headers={"Authorization": "Bearer test-token"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual(0, payload["data"]["total"])
        self.assertEqual("No labeled samples to preprocess", payload["data"]["message"])

    def test_preprocess_status_by_task_returns_wrapped_payload(self) -> None:
        """GET /v1/dataset/preprocess_status/{task_id} should return wrapped task payload."""

        with train_api_models._preprocess_lock:
            train_api_models._preprocess_tasks["task-1"] = train_api_models.PreprocessTask(
                task_id="task-1",
                status="running",
                progress="working",
                current=1,
                total=10,
            )

        client = self._build_client(samples=[_Sample(labeled=True)])
        response = client.get(
            "/v1/dataset/preprocess_status/task-1",
            headers={"Authorization": "Bearer test-token"},
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("task-1", payload["data"]["task_id"])
        self.assertEqual("running", payload["data"]["status"])
        self.assertEqual(1, payload["data"]["current"])
        self.assertEqual(10, payload["data"]["total"])


if __name__ == "__main__":
    unittest.main()
