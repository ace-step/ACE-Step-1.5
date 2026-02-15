"""Unit tests for audio_utils module, focusing on format support."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import torch
import numpy as np

from acestep.audio_utils import AudioSaver, save_audio


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


if __name__ == '__main__':
    unittest.main()
