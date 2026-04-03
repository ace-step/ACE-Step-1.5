"""Audio IO and normalization helpers for handler decomposition."""

import math
import random
from typing import Optional, Tuple

import numpy as np
import torch
import soundfile as sf
from loguru import logger


def _read_audio_file(audio_file: str) -> Tuple[np.ndarray, int]:
    """Read an audio file, with torchaudio fallback for formats unsupported by soundfile.

    soundfile (libsndfile) supports WAV/FLAC/OGG/MP3 etc. but NOT AAC/M4A/MP4.
    When soundfile fails, we fall back to torchaudio.load() which uses torchcodec
    and can handle virtually any format via FFmpeg.

    Args:
        audio_file: Path to the audio file.

    Returns:
        Tuple of (audio_np in float32 with shape [samples] or [samples, channels],
        sample_rate).

    Raises:
        RuntimeError: If both soundfile and torchaudio fail to read the file.
    """
    # Fast path: try soundfile directly (no torchcodec/FFmpeg overhead)
    sf_err = None
    try:
        audio_np, sr = sf.read(audio_file, dtype="float32")
        return audio_np, sr
    except Exception as exc:
        sf_err = exc
        logger.debug(
            "[_read_audio_file] soundfile cannot read '{}': {}. Trying torchaudio fallback.",
            audio_file, sf_err,
        )

    # Slow path: torchaudio (uses torchcodec -> FFmpeg under the hood)
    try:
        import torchaudio

        waveform, sr = torchaudio.load(audio_file)
        # torchaudio returns [channels, samples], convert to numpy [samples, channels]
        audio_np = waveform.numpy().T  # -> [samples, channels]
        if audio_np.shape[1] == 1:
            audio_np = audio_np.squeeze(1)  # -> [samples] for mono
        return audio_np.astype(np.float32), sr
    except Exception as ta_err:
        raise RuntimeError(
            f"Cannot read '{audio_file}': soundfile ({sf_err}) "
            f"and torchaudio ({ta_err}) both failed."
        ) from ta_err


class IoAudioMixin:
    """Mixin containing audio file loading and normalization helpers.

    Depends on host members:
    - Method: ``is_silence`` (provided by ``MemoryUtilsMixin`` in this decomposition).
    """

    def _normalize_audio_to_stereo_48k(
        self, audio: torch.Tensor, sr: int
    ) -> torch.Tensor:
        """Normalize audio tensor to stereo at 48kHz.

        Args:
            audio: Tensor in [channels, samples] or [samples] format.
            sr: Source sample rate.

        Returns:
            Tensor in [2, samples] at 48kHz, clamped to [-1.0, 1.0].
        """
        if audio.shape[0] == 1:
            audio = torch.cat([audio, audio], dim=0)

        audio = audio[:2]

        if sr != 48000:
            import torchaudio

            audio = torchaudio.transforms.Resample(sr, 48000)(audio)

        return torch.clamp(audio, -1.0, 1.0)

    @staticmethod
    def _numpy_to_channels_first(audio_np: np.ndarray) -> torch.Tensor:
        """Convert numpy audio array to channels-first torch tensor."""
        if audio_np.ndim == 1:
            return torch.from_numpy(audio_np).unsqueeze(0)
        return torch.from_numpy(audio_np.T)

    def process_target_audio(self, audio_file: Optional[str]) -> Optional[torch.Tensor]:
        """Load and normalize target audio file.

        Args:
            audio_file: Path to target audio file.

        Returns:
            Normalized stereo 48kHz tensor, or ``None`` on error/empty input.
        """
        if audio_file is None:
            return None

        try:
            audio_np, sr = _read_audio_file(audio_file)
            audio = self._numpy_to_channels_first(audio_np)
            return self._normalize_audio_to_stereo_48k(audio, sr)
        except Exception:
            logger.exception("[process_target_audio] Error processing target audio")
            return None

    def process_reference_audio(
        self, audio_file: Optional[str]
    ) -> Optional[torch.Tensor]:
        """Load and normalize reference audio, then sample 3x10s segments.

        Args:
            audio_file: Path to reference audio file.

        Returns:
            30-second stereo tensor from sampled front/middle/back segments,
            or ``None`` for empty/silent/error cases.
        """
        if audio_file is None:
            return None

        try:
            audio_np, sr = _read_audio_file(audio_file)
            audio = self._numpy_to_channels_first(audio_np)

            logger.debug(
                f"[process_reference_audio] Reference audio shape: {audio.shape}"
            )
            logger.debug(f"[process_reference_audio] Reference audio sample rate: {sr}")
            logger.debug(
                f"[process_reference_audio] Reference audio duration: {audio.shape[-1] / sr:.6f} seconds"
            )

            audio = self._normalize_audio_to_stereo_48k(audio, sr)
            if self.is_silence(audio):
                return None

            target_frames = 30 * 48000
            segment_frames = 10 * 48000

            if audio.shape[-1] < target_frames:
                repeat_times = math.ceil(target_frames / audio.shape[-1])
                audio = audio.repeat(1, repeat_times)

            total_frames = audio.shape[-1]
            segment_size = total_frames // 3

            front_start = random.randint(0, max(0, segment_size - segment_frames))
            front_audio = audio[:, front_start : front_start + segment_frames]

            middle_start = segment_size + random.randint(
                0, max(0, segment_size - segment_frames)
            )
            middle_audio = audio[:, middle_start : middle_start + segment_frames]

            back_start = 2 * segment_size + random.randint(
                0, max(0, (total_frames - 2 * segment_size) - segment_frames)
            )
            back_audio = audio[:, back_start : back_start + segment_frames]

            return torch.cat([front_audio, middle_audio, back_audio], dim=-1)
        except Exception as exc:
            logger.warning(
                f"[process_reference_audio] Invalid or unsupported reference audio: {exc}"
            )
            return None

    def process_src_audio(self, audio_file: Optional[str]) -> Optional[torch.Tensor]:
        """Load and normalize source audio for remix/extract flows.

        Args:
            audio_file: Path to source audio file.

        Returns:
            Normalized stereo 48kHz tensor, or ``None`` on error/empty input.
        """
        if audio_file is None:
            return None

        try:
            audio_np, sr = _read_audio_file(audio_file)
            audio = self._numpy_to_channels_first(audio_np)
            return self._normalize_audio_to_stereo_48k(audio, sr)
        except Exception:
            logger.exception("[process_src_audio] Error processing source audio")
            return None
