"""
Audio file handling utilities
"""
import numpy as np
from pathlib import Path
from typing import Tuple, Optional
from loguru import logger

try:
    import librosa
except ImportError:
    librosa = None


def load_audio_file(file_path: str, sr: int = 16000) -> Tuple[np.ndarray, int]:
    """Load audio file and return (audio_data, sample_rate)"""
    if not librosa:
        raise ImportError("librosa is required for audio loading")
    
    try:
        audio, sr = librosa.load(file_path, sr=sr)
        return audio, sr
    except Exception as e:
        logger.error(f"Failed to load audio from {file_path}: {e}")
        raise


def save_audio_file(audio_data: np.ndarray, file_path: str, sr: int = 16000) -> None:
    """Save audio data to file"""
    if not librosa:
        raise ImportError("librosa is required for audio saving")
    
    try:
        librosa.output.write_wav(file_path, audio_data, sr=sr)
        logger.info(f"Saved audio to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save audio to {file_path}: {e}")
        raise


def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds"""
    if not librosa:
        raise ImportError("librosa is required for audio analysis")
    
    try:
        duration = librosa.get_duration(filename=file_path)
        return duration
    except Exception as e:
        logger.error(f"Failed to get duration of {file_path}: {e}")
        return 0.0


def normalize_audio(audio_data: np.ndarray, target_db: float = -1.0) -> np.ndarray:
    """Normalize audio to target loudness (dB)"""
    try:
        # Calculate current RMS level
        rms = np.sqrt(np.mean(audio_data ** 2))
        if rms == 0:
            return audio_data
        
        # Convert target dB to linear scale
        target_linear = 10 ** (target_db / 20.0)
        
        # Scale audio
        normalized = audio_data * (target_linear / rms)
        
        # Prevent clipping
        max_val = np.max(np.abs(normalized))
        if max_val > 1.0:
            normalized = normalized / max_val
        
        return normalized
    except Exception as e:
        logger.error(f"Failed to normalize audio: {e}")
        return audio_data


def get_waveform_data(audio_data: np.ndarray, num_points: int = 1000) -> np.ndarray:
    """Downsample audio for visualization"""
    if len(audio_data) <= num_points:
        return audio_data
    
    # Average pooling for downsampling
    pool_size = len(audio_data) // num_points
    downsampled = audio_data[:pool_size * num_points].reshape(-1, pool_size).mean(axis=1)
    return downsampled
