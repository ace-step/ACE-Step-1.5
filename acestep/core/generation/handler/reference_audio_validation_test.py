"""Regression tests for user-facing reference-audio validation errors."""

import unittest
from unittest.mock import Mock

try:
    from acestep.handler import AceStepHandler
except ModuleNotFoundError:
    AceStepHandler = None


@unittest.skipIf(AceStepHandler is None, "AceStepHandler dependencies are unavailable in this test environment.")
class ReferenceAudioValidationTests(unittest.TestCase):
    """Tests for invalid reference-audio handling in ``generate_music``."""

    def test_generate_music_returns_error_for_invalid_reference_audio(self) -> None:
        """Invalid reference audio should fail fast with a user-facing message."""
        handler = AceStepHandler.__new__(AceStepHandler)
        handler.model = object()
        handler.vae = object()
        handler.text_tokenizer = object()
        handler.text_encoder = object()
        handler.batch_size = 1
        handler.sample_rate = 48000
        handler.current_offload_cost = 0.0

        handler._vram_guard_reduce_batch = lambda batch_size, audio_duration=None: batch_size
        handler.prepare_seeds = lambda batch_size, seed, use_random_seed: ([123] * batch_size, 123)
        handler.process_reference_audio = lambda _audio_file: None
        handler.service_generate = Mock(side_effect=AssertionError("service_generate should not be called"))

        result = handler.generate_music(
            captions="",
            lyrics="",
            reference_audio="not_audio.mp3",
            progress=lambda *_args, **_kwargs: None,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Invalid reference audio")
        self.assertIn("Reference audio is invalid", result["status_message"])
        self.assertEqual(result["audios"], [])


if __name__ == "__main__":
    unittest.main()
