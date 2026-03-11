"""HTTP integration tests for dataset save/sample routes."""

from __future__ import annotations

from typing import Any, Dict, Optional
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api.train_api_dataset_sample_routes import register_training_dataset_sample_routes


def _wrap_response(data: Any, code: int = 200, error: Optional[str] = None) -> Dict[str, Any]:
    """Return API-compatible response envelope for tests."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Require fixed bearer token for test requests."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


class _Sample:
    """Sample test double for sample route payloads."""

    def __init__(self) -> None:
        """Initialize default sample fields."""

        self.filename = "sample.wav"
        self.audio_path = str(Path(tempfile.gettempdir()) / "sample.wav")
        self.duration = 10.0
        self.caption = "cap"
        self.genre = "electronic"
        self.prompt_override = None
        self.lyrics = "[Instrumental]"
        self.bpm = 120
        self.keyscale = "C major"
        self.timesignature = "4/4"
        self.language = "unknown"
        self.is_instrumental = True
        self.labeled = True

    def to_dict(self) -> dict[str, Any]:
        """Return dictionary payload consumed by route handlers."""

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
    """Metadata test double used for dataset save/get operations."""

    def __init__(self) -> None:
        """Initialize mutable metadata values."""

        self.name = "dataset"
        self.custom_tag = ""
        self.tag_position = "replace"
        self.all_instrumental = True
        self.genre_ratio = 0


class _Builder:
    """Dataset builder test double for save/sample route behavior."""

    def __init__(self) -> None:
        """Initialize metadata and deterministic sample list."""

        self.metadata = _Metadata()
        self.samples = [_Sample()]
        self.saved_args: tuple[str, str] | None = None

    def get_labeled_count(self) -> int:
        """Return deterministic labeled count."""

        return 1

    def save_dataset(self, save_path: str, dataset_name: str) -> str:
        """Capture save args and return success status."""

        self.saved_args = (save_path, dataset_name)
        return "✅ saved"

    def update_sample(self, sample_idx: int, **_kwargs: Any) -> tuple[_Sample, str]:
        """Return selected sample with success status."""

        return self.samples[sample_idx], "✅ updated"


class TrainApiDatasetSampleRoutesHttpTests(unittest.TestCase):
    """HTTP tests covering extracted sample/save route behavior."""

    def _build_client(self) -> tuple[TestClient, _Builder]:
        """Create app/client pair with sample routes registered."""

        app = FastAPI()
        builder = _Builder()
        app.state.dataset_builder = builder
        register_training_dataset_sample_routes(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
        )
        return TestClient(app), builder

    def test_save_dataset_updates_path_on_success(self) -> None:
        """POST /v1/dataset/save should update app dataset path when save status is successful."""

        client, builder = self._build_client()
        response = client.post(
            "/v1/dataset/save",
            json={"save_path": "x.json", "dataset_name": "ds"},
            headers={"Authorization": "Bearer test-token"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual("✅ saved", payload["data"]["message"])
        self.assertEqual(("x.json", "ds"), builder.saved_args)
        self.assertEqual("x.json", client.app.state.dataset_json_path)

    def test_get_sample_returns_404_when_index_out_of_range(self) -> None:
        """GET /v1/dataset/sample/{sample_idx} should return 404 for out-of-range index."""

        client, _builder = self._build_client()
        response = client.get(
            "/v1/dataset/sample/99",
            headers={"Authorization": "Bearer test-token"},
        )
        self.assertEqual(404, response.status_code)
        self.assertIn("out of range", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
