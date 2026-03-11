"""HTTP integration tests for dataset route registration behavior."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Dict, Optional
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api.train_api_dataset_service import register_training_dataset_routes


def _wrap_response(data: Any, code: int = 200, error: Optional[str] = None) -> Dict[str, Any]:
    """Return API-compatible response envelope for tests."""

    return {"data": data, "code": code, "error": error}


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Require fixed bearer token for test requests."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


@contextmanager
def _temporary_llm_model(_app: FastAPI, _llm: Any, _lm_model_path: Optional[str]):
    """No-op context manager used by dataset routes during tests."""

    yield


class _Sample:
    """Sample test double with ``to_dict`` payload support."""

    def __init__(self, caption: str = "") -> None:
        """Initialize sample fields consumed by dataset route handlers."""

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
        self.labeled = bool(caption)

    def to_dict(self) -> dict[str, Any]:
        """Return stable dictionary representation used by route persistence logic."""

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

    def __init__(self) -> None:
        """Initialize mutable metadata fields used by route code."""

        self.name = "my_dataset"
        self.custom_tag = ""
        self.tag_position = "replace"
        self.all_instrumental = True
        self.genre_ratio = 0

    def to_dict(self) -> dict[str, Any]:
        """Return dictionary payload used for save checkpoints."""

        return {
            "name": self.name,
            "custom_tag": self.custom_tag,
            "tag_position": self.tag_position,
            "all_instrumental": self.all_instrumental,
            "genre_ratio": self.genre_ratio,
        }


class _Builder:
    """Dataset builder test double backing route behavior."""

    def __init__(self) -> None:
        """Initialize deterministic sample data and call-capture hooks."""

        self.metadata = _Metadata()
        self.samples = [_Sample(caption="already set"), _Sample(caption="")]
        self.last_label_call: dict[str, Any] | None = None

    def get_labeled_count(self) -> int:
        """Return deterministic labeled count."""

        return 1

    def label_all_samples(self, **kwargs: Any) -> tuple[list[Any], str]:
        """Capture label invocation arguments and return success status."""

        self.last_label_call = kwargs
        return self.samples, "ok"


class _RuntimeComponentManager:
    """No-op runtime manager replacement for route tests."""

    def __init__(self, handler: Any, llm: Any, app_state: Any) -> None:
        """Store passed runtime references."""

        self.handler = handler
        self.llm = llm
        self.app_state = app_state
        self.decoder_moved = False
        self.llm_unloaded = False

    def offload_decoder_to_cpu(self) -> None:
        """No-op in tests."""

    def unload_llm(self) -> None:
        """No-op in tests."""

    def restore(self) -> None:
        """No-op in tests."""


class TrainApiDatasetServiceHttpTests(unittest.TestCase):
    """HTTP tests covering extracted dataset-route dependencies."""

    def _build_client(self) -> tuple[TestClient, _Builder]:
        """Create app/client pair with lightweight dataset state."""

        app = FastAPI()
        builder = _Builder()
        app.state.dataset_builder = builder
        app.state.dataset_json_path = "dataset.json"
        app.state.handler = SimpleNamespace(model=object())
        app.state.llm_handler = SimpleNamespace(llm_initialized=True)

        register_training_dataset_routes(
            app=app,
            verify_api_key=_verify_api_key,
            wrap_response=_wrap_response,
            temporary_llm_model=_temporary_llm_model,
            atomic_write_json=lambda _path, _payload: None,
            append_jsonl=lambda _path, _record: None,
        )
        return TestClient(app), builder

    @mock.patch(
        "acestep.api.train_api_dataset_auto_label_sync_route.RuntimeComponentManager",
        new=_RuntimeComponentManager,
    )
    def test_auto_label_accepts_legacy_alias_fields(self) -> None:
        """POST /v1/dataset/auto_label should map legacy alias keys to current request fields."""

        client, builder = self._build_client()
        response = client.post(
            "/v1/dataset/auto_label",
            json={"hunk_size": 7, "batchsize": 3, "only_unlabeled": False},
            headers={"Authorization": "Bearer test-token"},
        )

        self.assertEqual(200, response.status_code)
        self.assertIsNotNone(builder.last_label_call)
        self.assertEqual(7, builder.last_label_call["chunk_size"])
        self.assertEqual(3, builder.last_label_call["batch_size"])

    def test_get_samples_returns_wrapped_serialized_payload(self) -> None:
        """GET /v1/dataset/samples should return serialized sample data in wrapped response."""

        client, _builder = self._build_client()
        response = client.get("/v1/dataset/samples", headers={"Authorization": "Bearer test-token"})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertIsNone(payload["error"])
        self.assertEqual(2, payload["data"]["num_samples"])
        self.assertEqual(0, payload["data"]["samples"][0]["index"])
        self.assertEqual("sample.wav", payload["data"]["samples"][0]["filename"])


if __name__ == "__main__":
    unittest.main()
