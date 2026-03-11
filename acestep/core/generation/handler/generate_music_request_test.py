"""Unit tests for ``generate_music`` request helper mixin."""

import types
import unittest

import torch

from acestep.core.generation.handler.generate_music_request import GenerateMusicRequestMixin


class _Host(GenerateMusicRequestMixin):
    """Minimal host implementing dependencies for request helper tests."""

    def __init__(self):
        """Initialize state and default stubs used by helper methods."""
        self.current_offload_cost = 0.0
        self.batch_size = 2
        self.sample_rate = 48000
        self.model = object()
        self.vae = object()
        self.text_tokenizer = object()
        self.text_encoder = object()
        self._vram_guard_reduce_batch = lambda bs, audio_duration=None: bs
        self.prepare_seeds = lambda bs, seed, use_random_seed: ([1] * bs, 1)
        self.process_reference_audio = lambda _ref: torch.zeros(2, 100)
        self.process_src_audio = lambda _src: torch.ones(2, 100)
        self.prepare_batch_data = lambda *args, **kwargs: (
            ["cap"], ["inst"], ["lyr"], ["en"], ["meta"]
        )
        self.determine_task_type = lambda task, codes: (False, False, task == "cover", True)
        self.prepare_padding_info = lambda *args, **kwargs: ([0.0], [1.0], torch.zeros(1, 2, 100))


class GenerateMusicRequestMixinTests(unittest.TestCase):
    """Validate request helper behavior used by ``generate_music`` orchestration."""

    def test_resolve_task_switches_to_cover_when_audio_codes_present(self):
        """Text2music should switch to cover mode when audio code hints are supplied."""
        host = _Host()
        task, instruction = host._resolve_generate_music_task(
            task_type="text2music",
            audio_code_string="<|audio_code_1|>",
            instruction="old",
        )
        self.assertEqual(task, "cover")
        self.assertNotEqual(instruction, "old")

    def test_prepare_runtime_normalizes_batch_and_duration(self):
        """Runtime helper should clamp batch floor and normalize invalid duration/end values."""
        host = _Host()
        out = host._prepare_generate_music_runtime(
            batch_size=0,
            audio_duration=0.0,
            repainting_end=-1.0,
            seed=7,
            use_random_seed=False,
        )
        self.assertEqual(out["actual_batch_size"], 1)
        self.assertIsNone(out["audio_duration"])
        self.assertIsNone(out["repainting_end"])

    def test_prepare_reference_and_source_audio_returns_error_for_invalid_reference(self):
        """Invalid reference audio should return a structured early error payload."""
        host = _Host()
        host.process_reference_audio = lambda _ref: None
        _, _, error = host._prepare_reference_and_source_audio(
            reference_audio="bad.wav",
            src_audio=None,
            audio_code_string="",
            actual_batch_size=1,
            task_type="cover",
        )
        self.assertIsNotNone(error)
        self.assertFalse(error["success"])
        self.assertEqual(error["error"], "Invalid reference audio")

    def test_prepare_reference_and_source_audio_ignores_src_audio_for_text2music(self):
        """Text2music should ignore src audio to preserve upstream behavior."""
        host = _Host()
        called = {"process_src_audio": False}

        def _process_src_audio(_src):
            called["process_src_audio"] = True
            return torch.ones(2, 100)

        host.process_src_audio = _process_src_audio
        _, processed_src_audio, error = host._prepare_reference_and_source_audio(
            reference_audio=None,
            src_audio="song.wav",
            audio_code_string="",
            actual_batch_size=1,
            task_type="text2music",
        )
        self.assertIsNone(error)
        self.assertIsNone(processed_src_audio)
        self.assertFalse(called["process_src_audio"])

    def test_prepare_reference_and_source_audio_returns_error_for_invalid_source(self):
        """Non-text2music source audio failure should return structured error payload."""
        host = _Host()
        host.process_src_audio = lambda _src: None
        _, processed_src_audio, error = host._prepare_reference_and_source_audio(
            reference_audio=None,
            src_audio="bad.wav",
            audio_code_string="",
            actual_batch_size=1,
            task_type="cover",
        )
        self.assertIsNone(processed_src_audio)
        self.assertIsNotNone(error)
        self.assertFalse(error["success"])
        self.assertEqual(error["error"], "Invalid source audio")


    def test_should_return_intermediate_always_true(self):
        """Intermediate tensors must always be returned for LRC generation support."""
        host = _Host()
        for task in ("text2music", "cover", "repaint"):
            inputs = host._prepare_generate_music_service_inputs(
                actual_batch_size=1,
                processed_src_audio=None,
                audio_duration=60.0,
                captions="test",
                lyrics="test",
                vocal_language="en",
                instruction="inst",
                bpm=120,
                key_scale="C major",
                time_signature="4/4",
                task_type=task,
                audio_code_string="",
                repainting_start=0.0,
                repainting_end=1.0,
            )
            self.assertTrue(
                inputs["should_return_intermediate"],
                f"should_return_intermediate must be True for task_type={task!r}",
            )


if __name__ == "__main__":
    unittest.main()
