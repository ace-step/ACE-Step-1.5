"""HTTP integration tests for dataset scan/load route registration."""

from __future__ import annotations

from typing import Any, Dict, Optional
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api.train_api_dataset_scan_load_routes import register_training_dataset_scan_load_routes


def _wrap_response(data: Any, code: int = 200, error: Optional[str] = None) -> Dict[str, Any]:
    """Return API-compatible response envelope for tests."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Require fixed bearer token for test requests."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


class _Sample:
    """Sample test double used by serializer payload assertions."""

    def __init__(self, caption: str = "cap") -> None:
        """Initialize fields read by ``_serialize_samples``."""

        self.filename = "sample.wav"
        self.audio_path = str(Path(tempfile.gettempdir()) / "sample.wav")
        self.duration = 8.0
        self.caption = caption
        self.genre = "electronic"
        self.prompt_override = None
        self.lyrics = "[Instrumental]"
        self.bpm = 120
        self.keyscale = "C major"
        self.timesignature = "4/4"
        self.language = "unknown"
        self.is_instrumental = True
        self.labeled = True


class _Metadata:
    """Metadata test double used by fake dataset builders."""

    def __init__(self) -> None:
        """Initialize mutable metadata fields consumed by handlers."""

        self.name = "default_name"
        self.custom_tag = ""
        self.tag_position = "replace"
        self.all_instrumental = True


class _ScanSuccessBuilder:
    """Fake DatasetBuilder for scan success flow."""

    def __init__(self) -> None:
        """Initialize fake metadata and deterministic sample list."""

        self.metadata = _Metadata()
        self.samples = [_Sample()]
        self.set_all_instrumental_calls: list[bool] = []
        self.set_custom_tag_calls: list[tuple[str, str]] = []

    def scan_directory(self, _audio_dir: str) -> tuple[list[_Sample], str]:
        """Return a successful scan result."""

        return self.samples, "scan-ok"

    def set_all_instrumental(self, value: bool) -> None:
        """Capture set-all-instrumental call arguments."""

        self.set_all_instrumental_calls.append(value)

    def set_custom_tag(self, tag: str, position: str) -> None:
        """Capture custom-tag call arguments."""

        self.set_custom_tag_calls.append((tag, position))


class _LoadEmptyBuilder:
    """Fake DatasetBuilder for load failure flow."""

    def __init__(self) -> None:
        """Initialize fake metadata and empty sample list."""

        self.metadata = _Metadata()
        self.samples = []

    def load_dataset(self, _dataset_path: str) -> tuple[list[_Sample], str]:
        """Return empty samples with a status message."""

        return [], "no-samples"

    def get_labeled_count(self) -> int:
        """Return zero labeled samples for completeness."""

        return 0


class TrainApiDatasetScanLoadRoutesHttpTests(unittest.TestCase):
    """HTTP tests covering extracted scan/load route behavior."""

    def _build_client(self) -> TestClient:
        """Create app/client pair with scan/load routes only."""

        app = FastAPI()
        register_training_dataset_scan_load_routes(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
        )
        return TestClient(app)

    def test_scan_dataset_success_sets_state_and_returns_serialized_samples(self) -> None:
        """POST /v1/dataset/scan should keep state updates and wrapped sample payload behavior."""

        client = self._build_client()
        fake_module = types.SimpleNamespace(DatasetBuilder=_ScanSuccessBuilder)

        with mock.patch.dict(sys.modules, {"acestep.training.dataset_builder": fake_module}):
            response = client.post(
                "/v1/dataset/scan",
                json={
                    "audio_dir": "dataset_dir",
                    "dataset_name": "test_dataset",
                    "custom_tag": "tag-1",
                    "tag_position": "append",
                    "all_instrumental": False,
                },
                headers={"Authorization": "Bearer test-token"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("scan-ok", payload["data"]["message"])
        self.assertEqual(1, payload["data"]["num_samples"])
        self.assertEqual("sample.wav", payload["data"]["samples"][0]["filename"])
        self.assertEqual("dataset_dir/test_dataset.json", client.app.state.dataset_json_path.replace("\\", "/"))

        builder = client.app.state.dataset_builder
        self.assertIsInstance(builder, _ScanSuccessBuilder)
        self.assertEqual([False], builder.set_all_instrumental_calls)
        self.assertEqual([("tag-1", "append")], builder.set_custom_tag_calls)

    def test_load_dataset_empty_returns_wrapped_400_payload(self) -> None:
        """POST /v1/dataset/load should keep wrapped error payload when load returns no samples."""

        client = self._build_client()
        fake_module = types.SimpleNamespace(DatasetBuilder=_LoadEmptyBuilder)

        with mock.patch.dict(sys.modules, {"acestep.training.dataset_builder": fake_module}):
            response = client.post(
                "/v1/dataset/load",
                json={"dataset_path": "missing.json"},
                headers={"Authorization": "Bearer test-token"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(400, payload["code"])
        self.assertEqual("no-samples", payload["error"])
        self.assertEqual(0, payload["data"]["num_samples"])

    def test_scan_dataset_requires_auth(self) -> None:
        """POST /v1/dataset/scan should return 401 when auth token is missing."""

        client = self._build_client()
        response = client.post("/v1/dataset/scan", json={"audio_dir": "dataset_dir"})
        self.assertEqual(401, response.status_code)


if __name__ == "__main__":
    unittest.main()
