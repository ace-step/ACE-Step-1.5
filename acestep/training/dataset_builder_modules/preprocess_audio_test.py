"""Unit tests for the torchaudio / ffmpeg preprocess decoder."""

import json
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import torch

from acestep.training.dataset_builder_modules import preprocess_audio


class LoadAudioStereoTests(unittest.TestCase):
    """load_audio_stereo prefers torchaudio and falls back to the ffmpeg CLI."""

    def test_uses_torchaudio_when_it_decodes(self):
        audio = torch.zeros(2, 8)
        with patch.object(
            preprocess_audio.torchaudio, "load", return_value=(audio, 48000)
        ) as load, patch.object(preprocess_audio.subprocess, "run") as run:
            out, sample_rate = preprocess_audio.load_audio_stereo("song.mp3", 48000, 240)

        load.assert_called_once_with("song.mp3")
        run.assert_not_called()
        self.assertEqual(sample_rate, 48000)
        self.assertEqual(tuple(out.shape), (2, 8))

    def test_ffmpeg_fallback_decodes_interleaved_f32(self):
        pcm = np.array([0.0, 0.5, -0.25, 1.0], dtype=np.float32)
        probe = MagicMock(
            stdout=json.dumps({"streams": [{"sample_rate": "48000", "channels": 2}]})
        )
        decoded = MagicMock(stdout=pcm.tobytes())
        with patch.object(
            preprocess_audio.torchaudio,
            "load",
            side_effect=RuntimeError("libavutil 61 is not supported"),
        ), patch.object(
            preprocess_audio.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.object(
            preprocess_audio.subprocess, "run", side_effect=[probe, decoded]
        ):
            out, sample_rate = preprocess_audio.load_audio_stereo("song.mp3", 48000, 240)

        self.assertEqual(sample_rate, 48000)
        self.assertEqual(tuple(out.shape), (2, 2))
        self.assertTrue(torch.allclose(out[0], torch.tensor([0.0, -0.25])))
        self.assertTrue(torch.allclose(out[1], torch.tensor([0.5, 1.0])))

    def test_reports_both_decoder_failures(self):
        with patch.object(
            preprocess_audio.torchaudio,
            "load",
            side_effect=RuntimeError("torchcodec mismatch"),
        ), patch.object(preprocess_audio.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError) as caught:
                preprocess_audio.load_audio_stereo("song.mp3", 48000, 240)

        message = str(caught.exception)
        self.assertIn("torchcodec mismatch", message)
        self.assertIn("ffmpeg and ffprobe are not on PATH", message)


if __name__ == "__main__":
    unittest.main()
