"""HTTP integration tests for dataset auto-label route registration."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Dict, Optional
import time
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api import train_api_models
from acestep.api.train_api_dataset_auto_label_routes import register_training_dataset_auto_label_routes


def _wrap_response(data: Any, code: int = 200, error: Optional[str] = None) -> Dict[str, Any]:
    """Return API-compatible response envelope for tests."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Require fixed bearer token for test requests."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


@contextmanager
def _temporary_llm_model(_app: FastAPI, _llm: Any, _lm_model_path: Optional[str]):
    """No-op context manager used by auto-label routes during tests."""

    yield


class _Sample:
    """Sample test double with attributes consumed by route handlers."""

    def __init__(self, caption: str = "ready", labeled: bool = True) -> None:
        """Initialize sample fields and deterministic defaults."""

        self.filename = "sample.wav"
        self.audio_path = str(Path(tempfile.gettempdir()) / "sample.wav")
        self.duration = 10.0
        self.caption = caption
        self.genre = "electronic"
        self.prompt_override = None
        self.lyrics = "[Instrumental]"
        self.bpm = 120
        self.keyscale = "C major"
        self.timesignature = "4/4"
        self.language = "unknown"
        self.is_instrumental = True
        self.labeled = labeled

    def to_dict(self) -> dict[str, Any]:
        """Return dictionary payload for persistence/status code paths."""

        return {
            "filename": self.filename,
            "audio_path": self.audio_path,
            "duration": self.duration,
            "caption": self.caption,
            "genre": self.genre,
            "prompt_override": self.prompt_override,
            "lyrics": self.lyrics,
            "bpm": self.bpm,
            "keyscale": self.keyscale,
            "timesignature": self.timesignature,
            "language": self.language,
            "is_instrumental": self.is_instrumental,
            "labeled": self.labeled,
        }


class _Metadata:
    """Metadata test double expected by dataset builder routes."""

    def to_dict(self) -> dict[str, Any]:
        """Return dictionary payload used by checkpoint writes."""

        return {"name": "my_dataset"}


class _Builder:
    """Dataset builder test double for auto-label route behavior."""

    def __init__(self, samples: list[_Sample]) -> None:
        """Store deterministic samples for route logic."""

        self.metadata = _Metadata()
        self.samples = samples

    def get_labeled_count(self) -> int:
        """Return number of labeled samples."""

        return sum(1 for sample in self.samples if sample.labeled)

    def label_all_samples(self, **_kwargs: Any) -> tuple[list[_Sample], str]:
        """Return successful label status without mutating sample data."""

        return self.samples, "ok"


class TrainApiDatasetAutoLabelRoutesHttpTests(unittest.TestCase):
    """HTTP tests covering extracted auto-label route behavior."""

    def setUp(self) -> None:
        """Reset global task registries before each test."""

        with train_api_models._auto_label_lock:
            train_api_models._auto_label_tasks.clear()
            train_api_models._auto_label_latest_task_id = None

    def tearDown(self) -> None:
        """Reset global task registries after each test."""

        with train_api_models._auto_label_lock:
            train_api_models._auto_label_tasks.clear()
            train_api_models._auto_label_latest_task_id = None

    def _build_client(self, samples: list[_Sample]) -> TestClient:
        """Create app/client pair with lightweight dataset + model state."""

        app = FastAPI()
        app.state.dataset_builder = _Builder(samples=samples)
        app.state.dataset_json_path = "dataset.json"
        app.state.handler = SimpleNamespace(model=object())
        app.state.llm_handler = SimpleNamespace(llm_initialized=True)
        register_training_dataset_auto_label_routes(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            temporary_llm_model=_temporary_llm_model,
            atomic_write_json=lambda _path, _payload: None,
            append_jsonl=lambda _path, _record: None,
        )
        return TestClient(app)

    def test_auto_label_requires_auth(self) -> None:
        """POST /v1/dataset/auto_label should return 401 when auth token is missing."""

        client = self._build_client(samples=[_Sample()])
        response = client.post("/v1/dataset/auto_label", json={})
        self.assertEqual(401, response.status_code)

    def test_auto_label_async_returns_zero_total_for_only_unlabeled_when_all_labeled(self) -> None:
        """POST /v1/dataset/auto_label_async should return zero total when all samples are already labeled."""

        client = self._build_client(samples=[_Sample(caption="ready", labeled=True)])
        response = client.post(
            "/v1/dataset/auto_label_async",
            json={"only_unlabeled": True},
            headers={"Authorization": "Bearer test-token"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual(0, payload["data"]["total"])
        self.assertEqual("All samples already labeled", payload["data"]["message"])

    def test_auto_label_status_returns_wrapped_task_payload(self) -> None:
        """GET /v1/dataset/auto_label_status/{task_id} should return wrapped task fields for known tasks."""

        client = self._build_client(samples=[_Sample()])
        with train_api_models._auto_label_lock:
            train_api_models._auto_label_tasks["task-1"] = train_api_models.AutoLabelTask(
                task_id="task-1",
                status="running",
                progress="working",
                current=1,
                total=10,
                save_path="dataset.json",
                created_at=time.time(),
                updated_at=time.time(),
            )

        response = client.get(
            "/v1/dataset/auto_label_status/task-1",
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
