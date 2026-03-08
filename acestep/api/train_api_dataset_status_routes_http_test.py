"""HTTP integration tests for latest-status dataset routes."""

from __future__ import annotations

import time
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acestep.api import train_api_models
from acestep.api._test_support import wrap_response as _wrap_response, bearer_verify_api_key as _verify_api_key
from acestep.api.train_api_dataset_status_routes import register_training_dataset_status_routes


class TrainApiDatasetStatusRoutesHttpTests(unittest.TestCase):
    """HTTP tests covering latest-status route behavior."""

    def setUp(self) -> None:
        """Reset global preprocess/auto-label task registries before each test."""

        with train_api_models._auto_label_lock:
            train_api_models._auto_label_tasks.clear()
            train_api_models._auto_label_latest_task_id = None
        with train_api_models._preprocess_lock:
            train_api_models._preprocess_tasks.clear()
            train_api_models._preprocess_latest_task_id = None

    def tearDown(self) -> None:
        """Reset global preprocess/auto-label task registries after each test."""

        with train_api_models._auto_label_lock:
            train_api_models._auto_label_tasks.clear()
            train_api_models._auto_label_latest_task_id = None
        with train_api_models._preprocess_lock:
            train_api_models._preprocess_tasks.clear()
            train_api_models._preprocess_latest_task_id = None

    def _build_client(self) -> TestClient:
        """Create app/client pair with status routes registered."""

        app = FastAPI()
        register_training_dataset_status_routes(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
        )
        return TestClient(app)

    def test_preprocess_status_latest_returns_idle_when_no_task(self) -> None:
        """GET /v1/dataset/preprocess_status should return wrapped idle payload when no task exists."""

        client = self._build_client()
        response = client.get("/v1/dataset/preprocess_status", headers={"Authorization": "Bearer test-token"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("idle", payload["data"]["status"])
        self.assertIsNone(payload["data"]["task_id"])

    def test_auto_label_status_latest_returns_task_payload(self) -> None:
        """GET /v1/dataset/auto_label_status should return wrapped latest-task payload."""

        with train_api_models._auto_label_lock:
            train_api_models._auto_label_tasks["task-1"] = train_api_models.AutoLabelTask(
                task_id="task-1",
                status="running",
                progress="working",
                current=1,
                total=5,
                save_path="dataset.json",
                created_at=time.time(),
                updated_at=time.time(),
            )
            train_api_models._auto_label_latest_task_id = "task-1"

        client = self._build_client()
        response = client.get("/v1/dataset/auto_label_status", headers={"Authorization": "Bearer test-token"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("task-1", payload["data"]["task_id"])
        self.assertEqual("running", payload["data"]["status"])
        self.assertEqual(1, payload["data"]["current"])
        self.assertEqual(5, payload["data"]["total"])


if __name__ == "__main__":
    unittest.main()
