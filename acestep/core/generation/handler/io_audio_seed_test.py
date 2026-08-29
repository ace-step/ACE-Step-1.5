"""Unit tests for seeded reference-audio segment sampling."""

import unittest
from unittest.mock import patch

import numpy as np
import torch

from acestep.core.generation.handler.io_audio import IoAudioMixin
from acestep.core.generation.handler.memory_utils import MemoryUtilsMixin


class _Host(IoAudioMixin, MemoryUtilsMixin):
    """Test host combining the audio IO and silence-check mixins."""


def _fixture_audio():
    """Return 90s of stereo 48kHz noise in soundfile [samples, channels] layout."""
    rng = np.random.default_rng(0)
    audio = rng.uniform(-0.5, 0.5, size=(90 * 48000, 2)).astype(np.float32)
    return audio, 48000


class ProcessReferenceAudioSeedTests(unittest.TestCase):
    """Validate deterministic segment selection under a fixed seed."""

    def test_same_seed_selects_same_segments(self):
        """Two calls with the same seed must return identical tensors."""
        host = _Host()
        with patch(
            "acestep.core.generation.handler.io_audio._read_audio_file",
            return_value=_fixture_audio(),
        ):
            first = host.process_reference_audio("ref.wav", seed=1234)
            second = host.process_reference_audio("ref.wav", seed=1234)
        self.assertTrue(torch.equal(first, second))

    def test_different_seeds_select_different_segments(self):
        """Different seeds should sample different reference slices."""
        host = _Host()
        with patch(
            "acestep.core.generation.handler.io_audio._read_audio_file",
            return_value=_fixture_audio(),
        ):
            first = host.process_reference_audio("ref.wav", seed=1)
            second = host.process_reference_audio("ref.wav", seed=2)
        self.assertFalse(torch.equal(first, second))


if __name__ == "__main__":
    unittest.main()
