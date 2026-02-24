"""Audio IO and normalization helpers for handler decomposition."""

import math
import random
from typing import Optional

import torch
from loguru import logger


class IoAudioMixin:
    """Mixin containing audio file loading and normalization helpers.

    Depends on host members:
    - Method: ``is_silence`` (provided by ``MemoryUtilsMixin`` in this decomposition).
    """

    def _normalize_audio_to_stereo_48k(self, audio: torch.Tensor, sr: int) -> torch.Tensor:
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
            import soundfile as sf
            audio_np, sr = sf.read(audio_file, dtype="float32")
            if audio_np.ndim == 1:
                audio = torch.from_numpy(audio_np).unsqueeze(0)
            else:
                audio = torch.from_numpy(audio_np.T)
            return self._normalize_audio_to_stereo_48k(audio, sr)
        except (OSError, RuntimeError, ValueError):
            logger.exception("[process_target_audio] Error processing target audio")
            return None

    def process_reference_audio(self, audio_file: Optional[str]) -> Optional[torch.Tensor]:
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
            import torchaudio
            audio, sr = torchaudio.load(audio_file)
            logger.debug(f"[process_reference_audio] Reference audio shape: {audio.shape}")
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

            middle_start = segment_size + random.randint(0, max(0, segment_size - segment_frames))
            middle_audio = audio[:, middle_start : middle_start + segment_frames]

            back_start = 2 * segment_size + random.randint(
                0, max(0, (total_frames - 2 * segment_size) - segment_frames)
            )
            back_audio = audio[:, back_start : back_start + segment_frames]

            return torch.cat([front_audio, middle_audio, back_audio], dim=-1)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(f"[process_reference_audio] Invalid or unsupported reference audio: {exc}")
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
            import torchaudio
            audio, sr = torchaudio.load(audio_file)
            return self._normalize_audio_to_stereo_48k(audio, sr)
        except (OSError, RuntimeError, ValueError):
            logger.exception("[process_src_audio] Error processing source audio")
            return None
