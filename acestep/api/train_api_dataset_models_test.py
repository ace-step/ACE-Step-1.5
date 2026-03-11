"""Unit tests for training dataset request models and serialization helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from acestep.api.train_api_dataset_models import AutoLabelRequest, _serialize_samples


class _Sample:
    """Lightweight sample object for serializer tests."""

    def __init__(
        self,
        filename: str,
        audio_path: str,
        duration: float,
        caption: str,
        genre: str,
        prompt_override: str | None,
        lyrics: str,
        bpm: int | None,
        keyscale: str,
        timesignature: str,
        language: str,
        is_instrumental: bool,
        labeled: bool,
    ) -> None:
        """Store sample attributes used by the serializer helper."""

        self.filename = filename
        self.audio_path = audio_path
        self.duration = duration
        self.caption = caption
        self.genre = genre
        self.prompt_override = prompt_override
        self.lyrics = lyrics
        self.bpm = bpm
        self.keyscale = keyscale
        self.timesignature = timesignature
        self.language = language
        self.is_instrumental = is_instrumental
        self.labeled = labeled


class _Builder:
    """Minimal builder object exposing a ``samples`` list."""

    def __init__(self, samples: list[_Sample]) -> None:
        """Initialize with deterministic sample data."""

        self.samples = samples


class TrainApiDatasetModelsTests(unittest.TestCase):
    """Behavior tests for extracted request models and serializers."""

    _TEST_AUDIO_PATH = str(Path(tempfile.gettempdir()) / "song.wav")

    def test_auto_label_request_maps_hunk_size_alias(self) -> None:
        """``hunk_size`` payload key should populate ``chunk_size``."""

        request = AutoLabelRequest(hunk_size=32)
        self.assertEqual(32, request.chunk_size)

    def test_auto_label_request_maps_hunksize_alias(self) -> None:
        """``hunksize`` payload key should populate ``chunk_size``."""

        request = AutoLabelRequest(hunksize=24)
        self.assertEqual(24, request.chunk_size)

    def test_auto_label_request_maps_batchsize_alias(self) -> None:
        """``batchsize`` payload key should populate ``batch_size``."""

        request = AutoLabelRequest(batchsize=3)
        self.assertEqual(3, request.batch_size)

    def test_auto_label_request_keeps_explicit_values(self) -> None:
        """Explicit fields should not be overridden by backward-compatible aliases."""

        request = AutoLabelRequest(chunk_size=16, hunk_size=64, batch_size=2, batchsize=8)
        self.assertEqual(16, request.chunk_size)
        self.assertEqual(2, request.batch_size)

    def test_serialize_samples_returns_expected_payload_shape(self) -> None:
        """Serializer should return stable dictionaries with index and sample fields."""

        builder = _Builder(
            samples=[
                _Sample(
                    filename="song.wav",
                    audio_path=self._TEST_AUDIO_PATH,
                    duration=12.5,
                    caption="bright synthwave",
                    genre="synthwave",
                    prompt_override=None,
                    lyrics="[Instrumental]",
                    bpm=120,
                    keyscale="C major",
                    timesignature="4/4",
                    language="unknown",
                    is_instrumental=True,
                    labeled=True,
                )
            ]
        )

        payload = _serialize_samples(builder)
        self.assertEqual(1, len(payload))
        self.assertEqual(0, payload[0]["index"])
        self.assertEqual("song.wav", payload[0]["filename"])
        self.assertEqual(self._TEST_AUDIO_PATH, payload[0]["audio_path"])
        self.assertEqual(12.5, payload[0]["duration"])
        self.assertEqual("bright synthwave", payload[0]["caption"])
        self.assertEqual("synthwave", payload[0]["genre"])
        self.assertIsNone(payload[0]["prompt_override"])
        self.assertEqual("[Instrumental]", payload[0]["lyrics"])
        self.assertEqual(120, payload[0]["bpm"])
        self.assertEqual("C major", payload[0]["keyscale"])
        self.assertEqual("4/4", payload[0]["timesignature"])
        self.assertEqual("unknown", payload[0]["language"])
        self.assertTrue(payload[0]["is_instrumental"])
        self.assertTrue(payload[0]["labeled"])


if __name__ == "__main__":
    unittest.main()
