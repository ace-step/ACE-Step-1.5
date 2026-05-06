"""Unit tests for audio_utils module, focusing on format support."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import torch
import numpy as np

from acestep.audio_utils import AudioSaver, apply_fade, save_audio

class AudioSaverFormatTests(unittest.TestCase):
    """Tests for AudioSaver format support, especially new Opus and AAC formats."""

    def setUp(self):
        """Set up temporary directory for test outputs."""
        self.temp_dir = tempfile.mkdtemp()
        self.sample_audio = torch.randn(2, 48000)  # 2 channels, 1 second at 48kHz
        self.sample_rate = 48000

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_accepts_opus_format(self):
        """AudioSaver should accept 'opus' as a valid format."""
        saver = AudioSaver(default_format="opus")
        self.assertEqual(saver.default_format, "opus")

    def test_init_accepts_aac_format(self):
        """AudioSaver should accept 'aac' as a valid format."""
        saver = AudioSaver(default_format="aac")
        self.assertEqual(saver.default_format, "aac")

    def test_init_accepts_all_formats(self):
        """AudioSaver should accept all supported formats."""
        for fmt in ["flac", "wav", "mp3", "wav32", "opus", "aac"]:
            saver = AudioSaver(default_format=fmt)
            self.assertEqual(saver.default_format, fmt)

    def test_init_rejects_invalid_format(self):
        """AudioSaver should reject invalid formats and fall back to 'flac'."""
        saver = AudioSaver(default_format="invalid")
        self.assertEqual(saver.default_format, "flac")

    def test_save_audio_validates_opus_format(self):
        """save_audio should validate 'opus' as a valid format (uses subprocess + libopus)."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test_opus"

        with (
            patch('subprocess.run') as mock_run,
            patch('soundfile.write'),
        ):
            result = saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="opus"
            )

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn('libopus', cmd)
            self.assertTrue(result.endswith('.opus'))

    def test_save_audio_validates_aac_format(self):
        """save_audio should validate 'aac' as a valid format (uses subprocess + aac codec)."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test_aac"

        with (
            patch('subprocess.run') as mock_run,
            patch('soundfile.write'),
        ):
            result = saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="aac"
            )

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn('aac', cmd)
            self.assertTrue(result.endswith('.aac'))


    def test_save_audio_mp3_uses_custom_export_path(self):
        """MP3 should use the dedicated export path, not torchaudio ffmpeg backend directly."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test.mp3"

        with patch.object(AudioSaver, '_save_mp3') as mock_save_mp3:
            saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="mp3"
            )

            mock_save_mp3.assert_called_once()
            _, _, call_sample_rate = mock_save_mp3.call_args[0]
            self.assertEqual(call_sample_rate, self.sample_rate)
            self.assertEqual(mock_save_mp3.call_args[1]['mp3_bitrate'], None)
            self.assertEqual(mock_save_mp3.call_args[1]['mp3_sample_rate'], None)

    def test_save_audio_mp3_forwards_optional_export_settings(self):
        """Optional MP3 bitrate/sample-rate settings should be forwarded unchanged."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test.mp3"

        with patch.object(AudioSaver, '_save_mp3') as mock_save_mp3:
            saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="mp3",
                mp3_bitrate="320k",
                mp3_sample_rate=44100,
            )

            mock_save_mp3.assert_called_once()
            self.assertEqual(mock_save_mp3.call_args[1]['mp3_bitrate'], "320k")
            self.assertEqual(mock_save_mp3.call_args[1]['mp3_sample_rate'], 44100)

    def test__save_mp3_uses_default_settings_when_not_overridden(self):
        """MP3 export should default to 128k at 48 kHz when no overrides are provided."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test.mp3"

        with (
            patch('soundfile.write') as mock_sf_write,
            patch('acestep.audio_utils.subprocess.run') as mock_subprocess_run,
        ):
            saver._save_mp3(self.sample_audio, output_path, self.sample_rate)

            # soundfile.write should be called to write the temp WAV
            mock_sf_write.assert_called_once()
            # Check sample rate argument (third positional arg to sf.write)
            sf_args = mock_sf_write.call_args[0]
            self.assertEqual(sf_args[2], 48000)

            cmd = mock_subprocess_run.call_args[0][0]
            self.assertIn('libmp3lame', cmd)
            self.assertIn('128k', cmd)
            self.assertIn('48000', cmd)
            self.assertNotIn('-abr', cmd)

    def test__save_mp3_uses_custom_bitrate_and_sample_rate(self):
        """MP3 export should honor explicit bitrate/sample-rate overrides."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test.mp3"

        with (
            patch('acestep.audio_utils.torchaudio.functional.resample', return_value=self.sample_audio) as mock_resample,
            patch('soundfile.write') as mock_sf_write,
            patch('acestep.audio_utils.subprocess.run') as mock_subprocess_run,
        ):
            saver._save_mp3(
                self.sample_audio,
                output_path,
                self.sample_rate,
                mp3_bitrate="320k",
                mp3_sample_rate=44100,
            )

            mock_resample.assert_called_once_with(self.sample_audio, 48000, 44100)
            mock_sf_write.assert_called_once()
            # Check that soundfile was called with the target sample rate
            sf_args = mock_sf_write.call_args[0]
            self.assertEqual(sf_args[2], 44100)

            cmd = mock_subprocess_run.call_args[0][0]
            self.assertIn('320k', cmd)
            self.assertIn('44100', cmd)

    def test_save_audio_opus_uses_subprocess_libopus(self):
        """Opus format should use ffmpeg subprocess with libopus codec."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test.opus"

        with (
            patch('subprocess.run') as mock_run,
            patch('soundfile.write'),
        ):
            saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="opus"
            )

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn('libopus', cmd)

    def test_save_audio_aac_uses_subprocess_aac_codec(self):
        """AAC format should use ffmpeg subprocess with aac codec."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test.aac"

        with (
            patch('subprocess.run') as mock_run,
            patch('soundfile.write'),
        ):
            saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="aac"
            )

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertIn('aac', cmd)

    def test_extension_handling_for_opus(self):
        """Test that .opus extension is correctly added."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test_file"

        with (
            patch('subprocess.run'),
            patch('soundfile.write'),
        ):
            result = saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="opus"
            )

            self.assertTrue(result.endswith('.opus'))
            self.assertTrue('test_file.opus' in result)

    def test_extension_handling_for_aac(self):
        """Test that .aac extension is correctly added."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test_file"

        with (
            patch('subprocess.run'),
            patch('soundfile.write'),
        ):
            result = saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="aac"
            )

            self.assertTrue(result.endswith('.aac'))
            self.assertTrue('test_file.aac' in result)

    def test_m4a_extension_accepted_for_aac(self):
        """Test that .m4a extension is accepted as valid for AAC format."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test_file.m4a"

        with (
            patch('subprocess.run'),
            patch('soundfile.write'),
        ):
            result = saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="aac"
            )

            self.assertTrue(result.endswith('.m4a'))

    def test_save_audio_invalid_format_fallback(self):
        """save_audio should fall back to default format for invalid formats."""
        saver = AudioSaver(default_format="flac")
        output_path = Path(self.temp_dir) / "test"

        with patch('soundfile.write'):
            result = saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="invalid_format"
            )

            # Should fall back to flac
            self.assertTrue(result.endswith('.flac'))

    def test_numpy_array_input_with_opus(self):
        """Test that numpy arrays work with Opus format."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test_numpy.opus"
        audio_np = np.random.randn(2, 48000).astype(np.float32)

        with (
            patch('subprocess.run') as mock_run,
            patch('soundfile.write'),
        ):
            result = saver.save_audio(
                audio_np,
                output_path,
                sample_rate=self.sample_rate,
                format="opus"
            )

            mock_run.assert_called_once()
            self.assertTrue(result.endswith('.opus'))

    def test_convenience_function_supports_opus(self):
        """Test that the convenience save_audio function supports Opus."""
        output_path = Path(self.temp_dir) / "convenience_test.opus"

        with (
            patch('subprocess.run'),
            patch('soundfile.write'),
        ):
            result = save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="opus"
            )

            self.assertTrue(result.endswith('.opus'))

    def test_convenience_function_supports_aac(self):
        """Test that the convenience save_audio function supports AAC."""
        output_path = Path(self.temp_dir) / "convenience_test.aac"

        with (
            patch('subprocess.run'),
            patch('soundfile.write'),
        ):
            result = save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="aac"
            )

            self.assertTrue(result.endswith('.aac'))



    def test_save_audio_mp3_does_not_fallback_to_soundfile_on_failure(self):
        """MP3 export must fail loudly instead of silently falling back to soundfile."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test.mp3"

        with patch.object(AudioSaver, '_save_mp3', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                saver.save_audio(
                    self.sample_audio,
                    output_path,
                    sample_rate=self.sample_rate,
                    format="mp3",
                )

    def test_opus_subprocess_error_propagates_directly(self):
        """CalledProcessError from ffmpeg for opus must propagate, not fall to soundfile fallback."""
        import subprocess
        import soundfile as sf_real

        saver = AudioSaver()
        # Create a real temp WAV to write
        with tempfile.NamedTemporaryFile(suffix=".opus", delete=False) as f:
            output_path = Path(f.name)
        try:
            sf_call_count = []

            real_sf_write = sf_real.write

            def spy_sf_write(*args, **kwargs):
                sf_call_count.append(args)
                return real_sf_write(*args, **kwargs)

            ffmpeg_error = subprocess.CalledProcessError(1, "ffmpeg", stderr=b"codec not found")

            with (
                patch("acestep.audio_utils.subprocess.run", side_effect=ffmpeg_error),
                patch("soundfile.write", side_effect=spy_sf_write),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    saver.save_audio(
                        self.sample_audio,
                        output_path,
                        sample_rate=self.sample_rate,
                        format="opus",
                    )

            # soundfile.write should have been called exactly ONCE (to write the temp WAV),
            # NOT a second time as a fallback for opus encoding.
            self.assertEqual(
                len(sf_call_count),
                1,
                f"soundfile.write called {len(sf_call_count)} times — fallback was attempted after ffmpeg failure",
            )
        finally:
            output_path.unlink(missing_ok=True)

    def test_aac_subprocess_error_propagates_directly(self):
        """CalledProcessError from ffmpeg for aac must propagate, not fall to soundfile fallback."""
        import subprocess
        import soundfile as sf_real

        saver = AudioSaver()
        with tempfile.NamedTemporaryFile(suffix=".aac", delete=False) as f:
            output_path = Path(f.name)
        try:
            sf_call_count = []

            real_sf_write = sf_real.write

            def spy_sf_write(*args, **kwargs):
                sf_call_count.append(args)
                return real_sf_write(*args, **kwargs)

            ffmpeg_error = subprocess.CalledProcessError(1, "ffmpeg", stderr=b"codec not found")

            with (
                patch("acestep.audio_utils.subprocess.run", side_effect=ffmpeg_error),
                patch("soundfile.write", side_effect=spy_sf_write),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    saver.save_audio(
                        self.sample_audio,
                        output_path,
                        sample_rate=self.sample_rate,
                        format="aac",
                    )

            # soundfile.write should have been called exactly ONCE (temp WAV only),
            # NOT a second time as a fallback for aac encoding.
            self.assertEqual(
                len(sf_call_count),
                1,
                f"soundfile.write called {len(sf_call_count)} times — fallback was attempted after ffmpeg failure",
            )
        finally:
            output_path.unlink(missing_ok=True)


class ApplyFadeTests(unittest.TestCase):
    """Tests for apply_fade function."""

    def setUp(self):
        """Create a constant-amplitude stereo test signal."""
        # 1 second of constant value 1.0 at 48 kHz, stereo
        self.sample_rate = 48000
        self.audio_tensor = torch.ones(2, self.sample_rate)
        self.audio_numpy = np.ones((2, self.sample_rate), dtype=np.float32)

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------

    def test_no_fade_returns_unchanged_tensor(self):
        """Zero fade durations should return audio unchanged."""
        result = apply_fade(self.audio_tensor, 0, 0)
        self.assertTrue(torch.allclose(result, self.audio_tensor))

    def test_no_fade_returns_unchanged_numpy(self):
        """Zero fade durations should return numpy audio unchanged."""
        result = apply_fade(self.audio_numpy, 0, 0)
        np.testing.assert_array_equal(result, self.audio_numpy)

    def test_fade_in_first_sample_is_zero(self):
        """The very first sample should be 0 after a fade in is applied."""
        result = apply_fade(self.audio_tensor, fade_in_samples=1000, fade_out_samples=0)
        self.assertAlmostEqual(result[0, 0].item(), 0.0, places=5)

    def test_fade_in_last_ramp_sample_near_one(self):
        """The last sample of a fade-in ramp should approach 1.0."""
        fade_samples = 4800
        result = apply_fade(self.audio_tensor, fade_in_samples=fade_samples, fade_out_samples=0)
        # Sample at index fade_samples - 1 should be close to 1.0
        self.assertAlmostEqual(result[0, fade_samples - 1].item(), 1.0, places=3)

    def test_fade_out_last_sample_is_zero(self):
        """The last sample should be 0 after a fade out is applied."""
        result = apply_fade(self.audio_tensor, fade_in_samples=0, fade_out_samples=1000)
        self.assertAlmostEqual(result[0, -1].item(), 0.0, places=5)

    def test_fade_out_first_ramp_sample_near_one(self):
        """The first sample of the fade-out region should approach 1.0."""
        total = self.sample_rate
        fade_samples = 4800
        result = apply_fade(self.audio_tensor, fade_in_samples=0, fade_out_samples=fade_samples)
        self.assertAlmostEqual(result[0, total - fade_samples].item(), 1.0, places=3)

    def test_both_fades_combined(self):
        """Fade in and fade out should both be applied correctly."""
        result = apply_fade(self.audio_tensor, fade_in_samples=480, fade_out_samples=480)
        self.assertAlmostEqual(result[0, 0].item(), 0.0, places=5)
        self.assertAlmostEqual(result[0, -1].item(), 0.0, places=5)
        # Middle should be unaffected (constant 1.0)
        mid = self.sample_rate // 2
        self.assertAlmostEqual(result[0, mid].item(), 1.0, places=5)

    def test_fade_preserves_type_tensor(self):
        """apply_fade should return a tensor when given a tensor."""
        result = apply_fade(self.audio_tensor, 100, 100)
        self.assertIsInstance(result, torch.Tensor)

    def test_fade_preserves_type_numpy(self):
        """apply_fade should return a numpy array when given a numpy array."""
        result = apply_fade(self.audio_numpy, 100, 100)
        self.assertIsInstance(result, np.ndarray)

    def test_fade_does_not_modify_input_tensor(self):
        """apply_fade should not modify the original tensor in place."""
        original = self.audio_tensor.clone()
        apply_fade(self.audio_tensor, 1000, 1000)
        self.assertTrue(torch.allclose(self.audio_tensor, original))

    def test_fade_does_not_modify_input_numpy(self):
        """apply_fade should not modify the original numpy array in place."""
        original = self.audio_numpy.copy()
        apply_fade(self.audio_numpy, 1000, 1000)
        np.testing.assert_array_equal(self.audio_numpy, original)

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_fade_clamps_to_signal_length(self):
        """Fade longer than the signal should be clamped to signal length."""
        very_long = self.sample_rate * 10
        result = apply_fade(self.audio_tensor, very_long, very_long)
        # Should not raise and both ends should be 0
        self.assertAlmostEqual(result[0, 0].item(), 0.0, places=5)
        self.assertAlmostEqual(result[0, -1].item(), 0.0, places=5)

    def test_fade_in_numpy_first_sample_is_zero(self):
        """Numpy fade-in should make the first sample 0."""
        result = apply_fade(self.audio_numpy, fade_in_samples=1000, fade_out_samples=0)
        self.assertAlmostEqual(float(result[0, 0]), 0.0, places=5)

    def test_fade_out_numpy_last_sample_is_zero(self):
        """Numpy fade-out should make the last sample 0."""
        result = apply_fade(self.audio_numpy, fade_in_samples=0, fade_out_samples=1000)
        self.assertAlmostEqual(float(result[0, -1]), 0.0, places=5)


class AudioSaverTorchaudioFreeTests(unittest.TestCase):
    """Integration tests verifying audio I/O works without torchaudio (torchcodec not required)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.audio = torch.zeros(2, 4800)  # 0.1s stereo at 48kHz
        self.sr = 48000

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_wav_save_uses_soundfile_not_torchaudio(self):
        """WAV save must not call torchaudio.save (uses soundfile directly)."""
        saver = AudioSaver()
        with patch('acestep.audio_utils.torchaudio.save') as mock_ta:
            path = saver.save_audio(self.audio, Path(self.temp_dir) / 'out.wav', sample_rate=self.sr, format='wav')
            mock_ta.assert_not_called()
        self.assertTrue(Path(path).exists())

    def test_flac_save_uses_soundfile_not_torchaudio(self):
        """FLAC save must not call torchaudio.save (uses soundfile directly)."""
        saver = AudioSaver()
        with patch('acestep.audio_utils.torchaudio.save') as mock_ta:
            path = saver.save_audio(self.audio, Path(self.temp_dir) / 'out.flac', sample_rate=self.sr, format='flac')
            mock_ta.assert_not_called()
        self.assertTrue(Path(path).exists())

    def test_mp3_temp_wav_uses_soundfile_not_torchaudio(self):
        """_save_mp3 must use soundfile for temp WAV, not torchaudio.save."""
        saver = AudioSaver()
        with (
            patch('acestep.audio_utils.torchaudio.save') as mock_ta,
            patch('acestep.audio_utils.subprocess.run'),
        ):
            saver._save_mp3(self.audio, Path(self.temp_dir) / 'out.mp3', self.sr)
            mock_ta.assert_not_called()

    def test_opus_save_uses_subprocess_libopus(self):
        """Opus save must call ffmpeg subprocess with libopus codec."""
        saver = AudioSaver()
        with (
            patch('subprocess.run') as mock_run,
            patch('soundfile.write'),
        ):
            saver.save_audio(self.audio, Path(self.temp_dir) / 'out.opus', sample_rate=self.sr, format='opus')
            cmd = mock_run.call_args[0][0]
            self.assertIn('libopus', cmd)

    def test_aac_save_uses_subprocess_aac_codec(self):
        """AAC save must call ffmpeg subprocess with aac codec."""
        saver = AudioSaver()
        with (
            patch('subprocess.run') as mock_run,
            patch('soundfile.write'),
        ):
            saver.save_audio(self.audio, Path(self.temp_dir) / 'out.aac', sample_rate=self.sr, format='aac')
            cmd = mock_run.call_args[0][0]
            self.assertIn('aac', cmd)

    def test_convert_audio_does_not_use_torchaudio_load(self):
        """convert_audio must not call torchaudio.load (uses soundfile.read)."""
        import soundfile as sf
        import numpy as np
        src = Path(self.temp_dir) / 'src.wav'
        sf.write(str(src), np.zeros((4800, 2), dtype=np.float32), self.sr)
        saver = AudioSaver()
        with patch('acestep.audio_utils.torchaudio.load') as mock_load:
            saver.convert_audio(str(src), str(Path(self.temp_dir) / 'out.flac'), 'flac')
            mock_load.assert_not_called()

    def test_convert_audio_handles_soundfile_unsupported_format(self):
        """BUG: convert_audio should fall back to subprocess ffmpeg when soundfile cannot read input.

        Currently convert_audio calls sf.read() directly with no fallback. libsndfile cannot
        read AAC/M4A/Opus files, so those calls raise RuntimeError. This test documents the
        DESIRED behavior (fallback via subprocess) and will FAIL until the bug is fixed.
        """
        import subprocess

        saver = AudioSaver()

        # Simulate soundfile failing to read (as it does for AAC/M4A in practice)
        sf_error = RuntimeError("Format not recognised")

        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            f.write(b"\x00" * 100)
            input_path = f.name

        try:
            with (
                patch("soundfile.read", side_effect=sf_error),
                patch("subprocess.run") as mock_subprocess,
                patch.object(saver, "save_audio", return_value=str(Path(self.temp_dir) / "output.wav")),
            ):
                result = saver.convert_audio(input_path, str(Path(self.temp_dir) / "output.wav"), "wav")
                # After the fix: convert_audio must attempt a subprocess/ffmpeg fallback
                # when sf.read fails, rather than propagating the RuntimeError.
                mock_subprocess.assert_called()
        finally:
            Path(input_path).unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
