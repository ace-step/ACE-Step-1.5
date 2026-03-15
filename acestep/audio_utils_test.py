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
        """save_audio should validate 'opus' as a valid format."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test_opus"
        
        # Mock torchaudio.save to avoid actual file writing
        with patch('acestep.audio_utils.torchaudio.save') as mock_save:
            result = saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="opus"
            )
            
            # Verify torchaudio.save was called with ffmpeg backend
            mock_save.assert_called_once()
            call_kwargs = mock_save.call_args[1]
            self.assertEqual(call_kwargs.get('backend'), 'ffmpeg')
            self.assertTrue(result.endswith('.opus'))

    def test_save_audio_validates_aac_format(self):
        """save_audio should validate 'aac' as a valid format."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test_aac"
        
        # Mock torchaudio.save to avoid actual file writing
        with patch('acestep.audio_utils.torchaudio.save') as mock_save:
            result = saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="aac"
            )
            
            # Verify torchaudio.save was called with ffmpeg backend
            mock_save.assert_called_once()
            call_kwargs = mock_save.call_args[1]
            self.assertEqual(call_kwargs.get('backend'), 'ffmpeg')
            self.assertTrue(result.endswith('.aac'))

    def test_save_audio_opus_uses_ffmpeg_backend(self):
        """Opus format should use ffmpeg backend like MP3."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test.opus"
        
        with patch('acestep.audio_utils.torchaudio.save') as mock_save:
            saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="opus"
            )
            
            # Check that ffmpeg backend was used
            call_kwargs = mock_save.call_args[1]
            self.assertEqual(call_kwargs['backend'], 'ffmpeg')

    def test_save_audio_aac_uses_ffmpeg_backend(self):
        """AAC format should use ffmpeg backend like MP3."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test.aac"
        
        with patch('acestep.audio_utils.torchaudio.save') as mock_save:
            saver.save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="aac"
            )
            
            # Check that ffmpeg backend was used
            call_kwargs = mock_save.call_args[1]
            self.assertEqual(call_kwargs['backend'], 'ffmpeg')

    def test_extension_handling_for_opus(self):
        """Test that .opus extension is correctly added."""
        saver = AudioSaver()
        output_path = Path(self.temp_dir) / "test_file"
        
        with patch('acestep.audio_utils.torchaudio.save'):
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
        
        with patch('acestep.audio_utils.torchaudio.save'):
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
        
        with patch('acestep.audio_utils.torchaudio.save'):
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
        
        with patch('acestep.audio_utils.torchaudio.save'):
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
        
        with patch('acestep.audio_utils.torchaudio.save') as mock_save:
            result = saver.save_audio(
                audio_np,
                output_path,
                sample_rate=self.sample_rate,
                format="opus"
            )
            
            # Verify the call was made
            mock_save.assert_called_once()
            self.assertTrue(result.endswith('.opus'))

    def test_convenience_function_supports_opus(self):
        """Test that the convenience save_audio function supports Opus."""
        output_path = Path(self.temp_dir) / "convenience_test.opus"
        
        with patch('acestep.audio_utils.torchaudio.save'):
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

        with patch('acestep.audio_utils.torchaudio.save'):
            result = save_audio(
                self.sample_audio,
                output_path,
                sample_rate=self.sample_rate,
                format="aac"
            )

            self.assertTrue(result.endswith('.aac'))


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


if __name__ == '__main__':
    unittest.main()
