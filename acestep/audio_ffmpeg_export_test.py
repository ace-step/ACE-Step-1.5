"""Unit tests for the ffmpeg-based Opus/AAC export helper."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

from acestep.audio_ffmpeg_export import encode_with_ffmpeg, tensor_to_soundfile_array


class TensorToSoundfileArrayTests(unittest.TestCase):
    """Tests for channels-first tensor -> soundfile array conversion."""

    def test_stereo_is_transposed_and_contiguous(self):
        """A [channels, samples] tensor becomes a C-contiguous [samples, channels] array."""
        audio = torch.arange(6, dtype=torch.float32).reshape(2, 3)

        result = tensor_to_soundfile_array(audio)

        self.assertEqual(result.shape, (3, 2))
        self.assertTrue(result.flags["C_CONTIGUOUS"])
        self.assertEqual(result[:, 0].tolist(), [0.0, 1.0, 2.0])

    def test_mono_1d_is_left_unchanged(self):
        """A 1-D mono tensor is passed through without transposing."""
        result = tensor_to_soundfile_array(torch.zeros(5))

        self.assertEqual(result.shape, (5,))


class EncodeWithFfmpegTests(unittest.TestCase):
    """Tests for encode_with_ffmpeg command construction and error handling."""

    def setUp(self):
        """Create a temporary output directory and sample audio."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.audio = torch.zeros(2, 4800)

    def tearDown(self):
        """Remove the temporary output directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _encode_with_mocks(self, audio_format, output_name, run_side_effect=None):
        """Run encode_with_ffmpeg with soundfile and subprocess mocked; return the mocks."""
        with (
            patch("acestep.audio_ffmpeg_export.sf.write") as mock_write,
            patch(
                "acestep.audio_ffmpeg_export.subprocess.run", side_effect=run_side_effect
            ) as mock_run,
        ):
            encode_with_ffmpeg(self.audio, self.temp_dir / output_name, 48000, audio_format)
        return mock_write, mock_run

    def test_opus_uses_libopus_codec(self):
        """Opus export writes a temp WAV and invokes ffmpeg with libopus."""
        mock_write, mock_run = self._encode_with_mocks("opus", "out.opus")

        self.assertEqual(mock_write.call_args[1]["format"], "WAV")
        self.assertEqual(mock_write.call_args[0][2], 48000)
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("-codec:a") + 1], "libopus")
        self.assertEqual(cmd[-1], str(self.temp_dir / "out.opus"))

    def test_aac_uses_aac_codec(self):
        """AAC export invokes ffmpeg with the native aac encoder."""
        _, mock_run = self._encode_with_mocks("aac", "out.m4a")

        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("-codec:a") + 1], "aac")

    def test_unknown_format_raises_value_error(self):
        """Formats without a configured codec are rejected before any work happens."""
        with patch("acestep.audio_ffmpeg_export.subprocess.run") as mock_run:
            with self.assertRaises(ValueError):
                encode_with_ffmpeg(self.audio, self.temp_dir / "out.xyz", 48000, "xyz")
        mock_run.assert_not_called()

    def test_missing_ffmpeg_raises_runtime_error(self):
        """A missing ffmpeg binary surfaces as an actionable RuntimeError."""
        with self.assertRaisesRegex(RuntimeError, "ffmpeg executable not found"):
            self._encode_with_mocks("opus", "out.opus", run_side_effect=FileNotFoundError())

    def test_ffmpeg_failure_includes_stderr(self):
        """A non-zero ffmpeg exit includes ffmpeg's stderr in the error."""
        error = subprocess.CalledProcessError(1, ["ffmpeg"], stderr=b"Unknown encoder")
        with self.assertRaisesRegex(RuntimeError, "Unknown encoder"):
            self._encode_with_mocks("aac", "out.aac", run_side_effect=error)

    def test_temp_wav_is_removed_after_failure(self):
        """The temporary WAV is cleaned up even when ffmpeg fails."""
        created = []
        real_named_temp = tempfile.NamedTemporaryFile

        def tracking_named_temp(*args, **kwargs):
            handle = real_named_temp(*args, **kwargs)
            created.append(Path(handle.name))
            return handle

        with patch(
            "acestep.audio_ffmpeg_export.tempfile.NamedTemporaryFile",
            side_effect=tracking_named_temp,
        ):
            with self.assertRaises(RuntimeError):
                self._encode_with_mocks("opus", "out.opus", run_side_effect=FileNotFoundError())

        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].exists())

    def test_ffmpeg_does_not_read_stdin(self):
        """ffmpeg must not consume or block on the parent's stdin (background servers)."""
        _, mock_run = self._encode_with_mocks("opus", "out.opus")

        self.assertIn("-nostdin", mock_run.call_args[0][0])
        self.assertIs(mock_run.call_args[1]["stdin"], subprocess.DEVNULL)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
    def test_real_ffmpeg_produces_expected_streams(self):
        """With ffmpeg available, real files decode with the expected codec and channels."""
        cases = (
            ("opus", "real.opus", 48000, "opus"),
            ("opus", "real_44k.opus", 44100, "opus"),
            ("aac", "real.aac", 48000, "aac"),
            ("aac", "real.m4a", 48000, "aac"),
        )
        for audio_format, name, sample_rate, expected_codec in cases:
            with self.subTest(name=name):
                audio = torch.sin(torch.linspace(0, 2000, sample_rate)).repeat(2, 1) * 0.1
                output_path = self.temp_dir / name
                encode_with_ffmpeg(audio, output_path, sample_rate, audio_format)
                probe = subprocess.run(
                    [
                        "ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=codec_name,channels",
                        "-of", "csv=p=0", str(output_path),
                    ],
                    check=True, capture_output=True, text=True,
                )
                self.assertEqual(probe.stdout.strip(), f"{expected_codec},2")

if __name__ == "__main__":
    unittest.main()
