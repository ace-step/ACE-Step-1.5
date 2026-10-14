"""Regression test for AudioExportDegradedError handling in generate_music.

When save_audio fails to export the requested format but produces a WAV fallback,
generate_music should return the fallback path instead of an empty string.
"""

from __future__ import annotations

import tempfile
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

import torch

from acestep.audio_utils import AudioExportDegradedError
from acestep.inference import GenerationConfig, GenerationParams, generate_music


class MockDitHandler:
    """Stub DiT handler that returns a successful generation result."""

    def __init__(self) -> None:
        """Initialize DiT handler state."""
        self.lora_loaded = False
        self.use_lora = False
        self.lora_scale = 1.0

    def prepare_seeds(self, batch_size: int, seed: str, use_random_seed: bool) -> tuple[list[int], None]:
        """Return a fixed seed list."""
        return [1234] * batch_size, None

    def generate_music(self, **kwargs: Any) -> dict[str, Any]:
        """Return a stub success result with a dummy audio tensor."""
        return {
            "success": True,
            "status_message": "stub ok",
            "audios": [{"tensor": torch.zeros(2, 4800), "sample_rate": 48000}],
            "extra_outputs": {},
        }


class FakeAudioSaver:
    """Controllable audio saver for testing exception handling."""

    def __init__(self, default_format: str = "flac") -> None:
        """Initialize fake saver."""
        self.default_format = default_format

    def save_audio(self, *args: Any, **kwargs: Any) -> str:
        """Controlled by the test via patching or state."""
        # This method is replaced by MagicMock in the tests
        return "saved.flac"


class ExportDegradedTests(unittest.TestCase):
    """Tests that degraded export falls back to WAV path."""

    def setUp(self) -> None:
        """Prepare common test objects."""
        self.dit = MockDitHandler()
        self.llm = MagicMock()
        self.llm.llm_initialized = True
        self.params = GenerationParams(
            task_type="complete",
            src_audio="source.wav",
            caption="warm analog drums",
            lyrics="[Instrumental]",
            seed=42,
        )
        self.config = GenerationConfig(
            batch_size=1,
            seeds=None,
            use_random_seed=False,
            audio_format="mp3",
        )
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        """Clean up temp directory."""
        self.temp_dir.cleanup()

    def test_degraded_export_returns_wav_fallback_path(self) -> None:
        """Test that AudioExportDegradedError results in the fallback WAV path."""
        fallback_path = f"{self.temp_dir.name}/fallback.wav"
        with open(fallback_path, "w") as f:
            f.write("dummy")

        with patch("acestep.inference.AudioSaver", return_value=FakeAudioSaver()):
            with patch.object(FakeAudioSaver, "save_audio") as mock_save:
                mock_save.side_effect = AudioExportDegradedError("ffmpeg missing", fallback_path, "mp3")
                result = generate_music(self.dit, self.llm, self.params, self.config, save_dir=self.temp_dir.name)
                self.assertTrue(result.success)
                self.assertEqual(result.audios[0]["path"], fallback_path)

    def test_generic_save_failure_keeps_empty_path(self) -> None:
        """Test that general RuntimeError results in an empty path."""
        with patch("acestep.inference.AudioSaver", return_value=FakeAudioSaver()):
            with patch.object(FakeAudioSaver, "save_audio") as mock_save:
                mock_save.side_effect = RuntimeError("boom")
                result = generate_music(self.dit, self.llm, self.params, self.config, save_dir=self.temp_dir.name)
                self.assertTrue(result.success)
                self.assertEqual(result.audios[0]["path"], "")

    def test_successful_save_returns_saver_path(self) -> None:
        """Test that successful save returns the path provided by the saver."""
        expected_path = "saved.mp3"
        with patch("acestep.inference.AudioSaver", return_value=FakeAudioSaver()):
            with patch.object(FakeAudioSaver, "save_audio") as mock_save:
                mock_save.return_value = expected_path
                result = generate_music(self.dit, self.llm, self.params, self.config, save_dir=self.temp_dir.name)
                self.assertEqual(result.audios[0]["path"], expected_path)


if __name__ == "__main__":
    unittest.main()
