"""Unit tests for audio IO mixin extraction."""

import sys
import types
import unittest
from unittest.mock import patch

import numpy as np
import torch

from acestep.core.generation.handler.io_audio import IoAudioMixin


class _Host(IoAudioMixin):
    """Minimal host implementing methods used by ``IoAudioMixin``."""

    def is_silence(self, audio: torch.Tensor) -> bool:
        """Treat near-zero tensors as silence."""
        return torch.all(audio.abs() < 1e-6).item()


def _fake_torchaudio_module(load_fn):
    """Create fake ``torchaudio`` module with minimal API used by tests."""
    module = types.ModuleType("torchaudio")
    module.load = load_fn
    module.transforms = types.SimpleNamespace(Resample=lambda *_args, **_kwargs: (lambda x: x))
    return module


class IoAudioMixinTests(unittest.TestCase):
    """Tests for normalization and audio loading helpers."""

    def test_normalize_audio_to_stereo_48k_duplicates_mono_and_clamps(self):
        """Mono input should duplicate to stereo and clamp values."""
        host = _Host()
        audio = torch.tensor([[2.0, -2.0, 0.5]], dtype=torch.float32)
        result = host._normalize_audio_to_stereo_48k(audio, 48000)

        self.assertEqual(tuple(result.shape), (2, 3))
        self.assertTrue(torch.all(result <= 1.0))
        self.assertTrue(torch.all(result >= -1.0))

    def test_process_target_audio_loads_and_normalizes(self):
        """Target audio should be loaded and normalized through helper."""
        host = _Host()
        fake_np = np.array([0.1, -0.1, 0.2], dtype=np.float32)
        fake_sf = types.ModuleType("soundfile")
        fake_sf.read = lambda *_args, **_kwargs: (fake_np, 32000)

        with patch.dict(sys.modules, {"soundfile": fake_sf}):
            with patch.object(host, "_normalize_audio_to_stereo_48k", return_value=torch.zeros(2, 3)) as norm:
                result = host.process_target_audio("fake.wav")

        self.assertIsNotNone(result)
        norm.assert_called_once()

    def test_process_src_audio_handles_load_error(self):
        """Source audio processing should return None on load failure."""
        host = _Host()
        fake_ta = _fake_torchaudio_module(lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad")))
        with patch.dict(sys.modules, {"torchaudio": fake_ta}):
            result = host.process_src_audio("bad.wav")
        self.assertIsNone(result)

    def test_process_reference_audio_returns_none_for_silence(self):
        """Reference audio should short-circuit for silent input."""
        host = _Host()
        silent = torch.zeros(2, 16, dtype=torch.float32)
        fake_ta = _fake_torchaudio_module(lambda *_args, **_kwargs: (silent, 48000))
        with patch.dict(sys.modules, {"torchaudio": fake_ta}):
            result = host.process_reference_audio("silent.wav")
        self.assertIsNone(result)

    def test_process_reference_audio_samples_expected_segments(self):
        """Reference audio should concatenate front/middle/back 10s sampled windows."""
        host = _Host()
        base = torch.linspace(-1.0, 1.0, 1_800_000, dtype=torch.float32)
        audio = torch.stack([base, -base], dim=0)
        fake_ta = _fake_torchaudio_module(lambda *_args, **_kwargs: (audio, 48000))

        with patch.dict(sys.modules, {"torchaudio": fake_ta}):
            with patch("acestep.core.generation.handler.io_audio.random.randint", side_effect=[10, 20, 30]):
                result = host.process_reference_audio("ref.wav")

        self.assertIsNotNone(result)
        segment_frames = 10 * 48000
        expected = torch.cat(
            [
                audio[:, 10 : 10 + segment_frames],
                audio[:, 600_000 + 20 : 600_000 + 20 + segment_frames],
                audio[:, 1_200_000 + 30 : 1_200_000 + 30 + segment_frames],
            ],
            dim=-1,
        )
        self.assertTrue(torch.equal(result, expected))

    def test_process_reference_audio_returns_none_on_load_error(self):
        """Reference audio processing should return None when loading fails."""
        host = _Host()
        fake_ta = _fake_torchaudio_module(lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad")))
        with patch.dict(sys.modules, {"torchaudio": fake_ta}):
            result = host.process_reference_audio("bad.wav")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
