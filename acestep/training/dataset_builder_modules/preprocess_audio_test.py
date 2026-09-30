"""Unit tests for the torchaudio / ffmpeg preprocess decoder."""

import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import torch

from acestep.training.dataset_builder_modules import preprocess_audio


def _completed(stdout: str | bytes, returncode: int = 0) -> MagicMock:
    """Build a subprocess result with the fields the decoder reads."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = b""
    return result


class LoadAudioStereoTests(unittest.TestCase):
    """load_audio_stereo prefers torchaudio and falls back to the ffmpeg CLI."""

    def test_uses_torchaudio_when_it_decodes(self):
        """A successful torchaudio load does not call ffmpeg."""
        audio = torch.zeros(2, 8)
        with patch.object(
            preprocess_audio.torchaudio, "load", return_value=(audio, 48000)
        ) as load, patch.object(preprocess_audio.subprocess, "run") as run:
            out, sample_rate = preprocess_audio.load_audio_stereo(
                "song.mp3", 48000, 240
            )

        load.assert_called_once_with("song.mp3")
        run.assert_not_called()
        self.assertEqual(sample_rate, 48000)
        self.assertEqual(tuple(out.shape), (2, 8))

    def test_ffmpeg_fallback_decodes_interleaved_f32(self):
        """The fallback probes with -i and decodes the probed channel count."""
        pcm = np.array([0.0, 0.5, -0.25, 1.0], dtype=np.float32)
        probe = _completed(
            json.dumps({"streams": [{"sample_rate": "48000", "channels": 2}]})
        )
        decoded = _completed(pcm.tobytes())
        with patch.object(
            preprocess_audio.torchaudio,
            "load",
            side_effect=RuntimeError("libavutil 61 is not supported"),
        ), patch.object(
            preprocess_audio.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.object(
            preprocess_audio.subprocess, "run", side_effect=[probe, decoded]
        ) as run:
            out, sample_rate = preprocess_audio.load_audio_stereo(
                "song.mp3", 48000, 240
            )

        probe_cmd = run.call_args_list[0].args[0]
        decode_cmd = run.call_args_list[1].args[0]
        self.assertEqual(probe_cmd[-2:], ["-i", "song.mp3"])
        self.assertEqual(run.call_args_list[0].kwargs["timeout"], 300)
        self.assertIn("-map", decode_cmd)
        self.assertEqual(decode_cmd[decode_cmd.index("-ac") + 1], "2")
        self.assertEqual(run.call_args_list[1].kwargs["timeout"], 300)
        self.assertEqual(sample_rate, 48000)
        self.assertEqual(tuple(out.shape), (2, 2))
        self.assertTrue(torch.allclose(out[0], torch.tensor([0.0, -0.25])))
        self.assertTrue(torch.allclose(out[1], torch.tensor([0.5, 1.0])))

    def test_reports_both_decoder_failures(self):
        """A missing ffmpeg binary is included with the torchaudio error."""
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

    def test_ffmpeg_failure_includes_the_process_error(self):
        """A non-zero ffmpeg exit becomes part of the combined error."""
        failure = subprocess.CalledProcessError(
            1, ["ffmpeg"], stderr=b"Invalid data found when processing input"
        )
        with patch.object(
            preprocess_audio.torchaudio,
            "load",
            side_effect=RuntimeError("torchcodec mismatch"),
        ), patch.object(
            preprocess_audio.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.object(preprocess_audio.subprocess, "run", side_effect=failure):
            with self.assertRaises(RuntimeError) as caught:
                preprocess_audio.load_audio_stereo("song.mp3", 48000, 240)

        self.assertIn("Invalid data found", str(caught.exception))

    def test_ffmpeg_timeout_is_reported(self):
        """A hung ffmpeg is reported instead of blocking preprocessing."""
        failure = subprocess.TimeoutExpired(["ffprobe"], 300)
        with patch.object(
            preprocess_audio.torchaudio,
            "load",
            side_effect=RuntimeError("torchcodec mismatch"),
        ), patch.object(
            preprocess_audio.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.object(preprocess_audio.subprocess, "run", side_effect=failure):
            with self.assertRaises(RuntimeError) as caught:
                preprocess_audio.load_audio_stereo("song.mp3", 48000, 240)

        self.assertIn("timed out", str(caught.exception))

    def test_rejects_pcm_that_does_not_match_the_channel_count(self):
        """A short final frame is an error instead of a mis-shaped tensor."""
        probe = _completed(
            json.dumps({"streams": [{"sample_rate": "48000", "channels": 2}]})
        )
        decoded = _completed(np.array([0.1, 0.2, 0.3], dtype=np.float32).tobytes())
        with patch.object(
            preprocess_audio.torchaudio,
            "load",
            side_effect=RuntimeError("torchcodec mismatch"),
        ), patch.object(
            preprocess_audio.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.object(
            preprocess_audio.subprocess, "run", side_effect=[probe, decoded]
        ):
            with self.assertRaises(RuntimeError) as caught:
                preprocess_audio.load_audio_stereo("song.mp3", 48000, 240)

        self.assertIn("not divisible by 2", str(caught.exception))

    def test_rejects_empty_ffmpeg_output(self):
        """A successful ffmpeg process that writes nothing is an error."""
        probe = _completed(
            json.dumps({"streams": [{"sample_rate": "48000", "channels": 2}]})
        )
        decoded = _completed(b"")
        with patch.object(
            preprocess_audio.torchaudio,
            "load",
            side_effect=RuntimeError("torchcodec mismatch"),
        ), patch.object(
            preprocess_audio.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.object(
            preprocess_audio.subprocess, "run", side_effect=[probe, decoded]
        ):
            with self.assertRaises(RuntimeError) as caught:
                preprocess_audio.load_audio_stereo("song.mp3", 48000, 240)

        self.assertIn("decoded no samples", str(caught.exception))

    def test_rejects_probe_output_without_a_stream(self):
        """Probe JSON with no audio stream names the file in the error."""
        probe = _completed(json.dumps({"streams": []}))
        with patch.object(
            preprocess_audio.torchaudio,
            "load",
            side_effect=RuntimeError("torchcodec mismatch"),
        ), patch.object(
            preprocess_audio.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.object(preprocess_audio.subprocess, "run", return_value=probe):
            with self.assertRaises(RuntimeError) as caught:
                preprocess_audio.load_audio_stereo("song.mp3", 48000, 240)

        self.assertIn("no usable audio stream", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
