"""Unit tests for audio IO mixin extraction."""

import os
import tempfile
import types
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import torch

from acestep.core.generation.handler.io_audio import IoAudioMixin, _read_audio_file


class _Host(IoAudioMixin):
    """Minimal host implementing methods used by ``IoAudioMixin``."""

    def is_silence(self, audio: torch.Tensor) -> bool:
        """Treat near-zero tensors as silence."""
        return torch.all(audio.abs() < 1e-6).item()


class ReadAudioFileTests(unittest.TestCase):
    """Tests for the _read_audio_file fallback logic."""

    def test_reads_wav_via_soundfile(self):
        """WAV files should be read directly by soundfile."""
        import soundfile as sf

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            data = np.random.randn(48000).astype(np.float32)
            sf.write(tmp.name, data, 48000)
            audio_np, sr = _read_audio_file(tmp.name)
            self.assertEqual(sr, 48000)
            self.assertEqual(audio_np.shape[0], 48000)
        finally:
            os.unlink(tmp.name)

    def test_falls_back_to_torchaudio_on_soundfile_failure(self):
        """When soundfile fails, torchaudio.load should be tried."""
        fake_waveform = torch.randn(1, 44100)

        with patch("acestep.core.generation.handler.io_audio.sf") as mock_sf:
            mock_sf.read.side_effect = Exception("Format not recognised")
            with patch("torchaudio.load", return_value=(fake_waveform, 44100)) as mock_load:
                audio_np, sr = _read_audio_file("test.aac")

        self.assertEqual(sr, 44100)
        self.assertEqual(audio_np.shape[0], 44100)
        mock_load.assert_called_once_with("test.aac")

    def test_raises_when_both_fail(self):
        """Should raise RuntimeError when both soundfile and torchaudio fail."""
        with patch("acestep.core.generation.handler.io_audio.sf") as mock_sf:
            mock_sf.read.side_effect = Exception("sf fail")
            with patch("torchaudio.load", side_effect=RuntimeError("ta fail")):
                with self.assertRaises(RuntimeError) as ctx:
                    _read_audio_file("bad.xyz")
                self.assertIn("sf fail", str(ctx.exception))
                self.assertIn("ta fail", str(ctx.exception))


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

        with patch("acestep.core.generation.handler.io_audio._read_audio_file", return_value=(fake_np, 48000)):
            with patch.object(host, "_normalize_audio_to_stereo_48k", return_value=torch.zeros(2, 3)) as norm:
                result = host.process_target_audio("fake.wav")

        self.assertIsNotNone(result)
        norm.assert_called_once()

    def test_process_src_audio_handles_load_error(self):
        """Source audio processing should return None on load failure."""
        host = _Host()
        with patch("acestep.core.generation.handler.io_audio._read_audio_file", side_effect=RuntimeError("bad")):
            result = host.process_src_audio("bad.aac")
        self.assertIsNone(result)

    def test_process_reference_audio_returns_none_for_silence(self):
        """Reference audio should short-circuit for silent input."""
        host = _Host()
        silent_np = np.zeros((16, 2), dtype=np.float32)
        with patch("acestep.core.generation.handler.io_audio._read_audio_file", return_value=(silent_np, 48000)):
            result = host.process_reference_audio("silent.wav")
        self.assertIsNone(result)

    def test_process_reference_audio_samples_expected_segments(self):
        """Reference audio should concatenate front/middle/back 10s sampled windows."""
        host = _Host()
        base = torch.linspace(-1.0, 1.0, 1_800_000, dtype=torch.float32)
        audio = torch.stack([base, -base], dim=0)
        # _read_audio_file returns numpy in [samples, channels]
        audio_np = audio.T.numpy()

        with patch("acestep.core.generation.handler.io_audio._read_audio_file", return_value=(audio_np, 48000)):
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
        with patch("acestep.core.generation.handler.io_audio._read_audio_file", side_effect=RuntimeError("bad")):
            result = host.process_reference_audio("bad.aac")
        self.assertIsNone(result)

    def test_process_src_audio_returns_none_for_none_input(self):
        """None input should return None without error."""
        host = _Host()
        result = host.process_src_audio(None)
        self.assertIsNone(result)


class ReadAudioFileIntegrationTest(unittest.TestCase):
    """Integration test with real AAC file (requires ffmpeg on system)."""

    @unittest.skipUnless(os.path.exists("/tmp/test_aac.aac"), "test AAC file not present")
    def test_reads_aac_file(self):
        """AAC file should be readable via torchaudio fallback."""
        audio_np, sr = _read_audio_file("/tmp/test_aac.aac")
        self.assertGreater(sr, 0)
        self.assertGreater(audio_np.shape[0], 0)


if __name__ == "__main__":
    unittest.main()
