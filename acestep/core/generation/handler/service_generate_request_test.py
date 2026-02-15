"""Unit tests for service-generation request normalization helpers."""

import types
import unittest
from unittest.mock import patch

from acestep.core.generation.handler.service_generate_request import ServiceGenerateRequestMixin


class _Host(ServiceGenerateRequestMixin):
    """Test host exposing the minimum runtime attributes for request helpers."""

    def __init__(self, is_turbo: bool):
        """Configure turbo flag and no-op normalizers."""
        self.config = types.SimpleNamespace(is_turbo=is_turbo)
        self._normalize_instructions = lambda instructions, _batch, _default: instructions
        self._normalize_audio_code_hints = lambda hints, _batch: hints


class ServiceGenerateRequestMixinTests(unittest.TestCase):
    """Verify request normalization behavior stays stable after extraction."""

    def test_normalize_inputs_clamps_turbo_steps_and_expands_lists(self):
        """Turbo path should clamp infer steps and normalize list-like inputs."""
        host = _Host(is_turbo=True)
        out = host._normalize_service_generate_inputs(
            captions="cap",
            lyrics=["lyric"],
            keys="k1",
            metas={"bpm": 120},
            vocal_languages="en",
            repainting_start=0.1,
            repainting_end=1.2,
            instructions=["i1"],
            audio_code_hints=["h1"],
            infer_steps=20,
            seed=[1],
        )

        self.assertEqual(out["infer_steps"], 8)
        self.assertEqual(out["captions"], ["cap"])
        self.assertEqual(out["lyrics"], ["lyric"])
        self.assertEqual(out["keys"], ["k1"])
        self.assertEqual(out["metas"], [{"bpm": 120}])
        self.assertEqual(out["vocal_languages"], ["en"])
        self.assertEqual(out["repainting_start"], [0.1])
        self.assertEqual(out["repainting_end"], [1.2])
        self.assertEqual(out["seed_list"], [1])

    def test_build_service_seed_list_duplicates_scalar_seed(self):
        """Scalar seed should be copied across the normalized batch size."""
        host = _Host(is_turbo=False)
        out = host._normalize_service_generate_inputs(
            captions=["a", "b", "c"],
            lyrics=["l1"],
            keys=None,
            metas=None,
            vocal_languages=None,
            repainting_start=None,
            repainting_end=None,
            instructions=None,
            audio_code_hints=None,
            infer_steps=12,
            seed=7,
        )

        self.assertEqual(out["infer_steps"], 12)
        self.assertEqual(out["lyrics"], ["l1", "l1", "l1"])
        self.assertEqual(out["seed_list"], [7, 7, 7])

    def test_seed_list_shorter_than_batch_gets_padded(self):
        """Short seed lists should preserve existing entries and append random seeds."""
        host = _Host(is_turbo=False)
        with patch("acestep.core.generation.handler.service_generate_request.random.randint", return_value=99):
            out = host._normalize_service_generate_inputs(
                captions=["a", "b", "c"],
                lyrics=["l1"],
                keys=None,
                metas=None,
                vocal_languages=None,
                repainting_start=None,
                repainting_end=None,
                instructions=None,
                audio_code_hints=None,
                infer_steps=12,
                seed=[3],
            )
        self.assertEqual(out["seed_list"], [3, 99, 99])

    def test_seed_list_longer_than_batch_gets_truncated(self):
        """Long seed lists should be truncated to batch size."""
        host = _Host(is_turbo=False)
        out = host._normalize_service_generate_inputs(
            captions=["a", "b"],
            lyrics=["l1"],
            keys=None,
            metas=None,
            vocal_languages=None,
            repainting_start=None,
            repainting_end=None,
            instructions=None,
            audio_code_hints=None,
            infer_steps=12,
            seed=[11, 12, 13, 14],
        )
        self.assertEqual(out["seed_list"], [11, 12])

    def test_lyrics_longer_than_batch_get_truncated(self):
        """Lyrics list should be truncated to match caption batch size."""
        host = _Host(is_turbo=False)
        out = host._normalize_service_generate_inputs(
            captions=["a", "b"],
            lyrics=["l1", "l2", "l3"],
            keys=None,
            metas=None,
            vocal_languages=None,
            repainting_start=None,
            repainting_end=None,
            instructions=None,
            audio_code_hints=None,
            infer_steps=12,
            seed=[1, 2],
        )
        self.assertEqual(out["lyrics"], ["l1", "l2"])


if __name__ == "__main__":
    unittest.main()
