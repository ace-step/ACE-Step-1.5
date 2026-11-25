"""Encode audio tensors to compressed formats via a temporary WAV and the ffmpeg CLI.

Avoids ``torchaudio.save``, which in torchaudio 2.9+ ignores ``backend=`` and
always requires torchcodec (unavailable on ROCm/XPU and broken on some ABIs).
"""

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from loguru import logger

FFMPEG_TIMEOUT_SECONDS = 120

# Output format -> ffmpeg audio encoder name.
FFMPEG_CODECS = {
    "opus": "libopus",
    "aac": "aac",
}


def tensor_to_soundfile_array(audio_tensor: torch.Tensor) -> np.ndarray:
    """Convert a channels-first tensor into a C-contiguous array for soundfile.

    Args:
        audio_tensor: Audio as ``[channels, samples]`` or ``[samples]``.

    Returns:
        Float array shaped ``[samples, channels]`` (or ``[samples]`` for mono 1-D).
    """
    audio = audio_tensor.detach().cpu()
    if audio.dim() == 2:
        audio = audio.transpose(0, 1)
    return audio.contiguous().numpy()


def encode_with_ffmpeg(
    audio_tensor: torch.Tensor,
    output_path: Path,
    sample_rate: int,
    audio_format: str,
) -> None:
    """Write ``audio_tensor`` to ``output_path`` using ffmpeg for the given format.

    Args:
        audio_tensor: Channels-first audio tensor.
        output_path: Destination file; ffmpeg picks the container from its suffix.
        sample_rate: Sample rate of ``audio_tensor`` in Hz.
        audio_format: Key of ``FFMPEG_CODECS`` (e.g. ``"opus"``, ``"aac"``).

    Raises:
        ValueError: If ``audio_format`` has no configured ffmpeg codec.
        RuntimeError: If ffmpeg is missing, times out, or exits with an error.
    """
    codec = FFMPEG_CODECS.get(audio_format)
    if codec is None:
        raise ValueError(f"No ffmpeg codec configured for format '{audio_format}'")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
        temp_wav_path = Path(temp_wav.name)

    try:
        sf.write(
            str(temp_wav_path),
            tensor_to_soundfile_array(audio_tensor),
            int(sample_rate),
            format="WAV",
        )
        _run_ffmpeg(temp_wav_path, output_path, codec, audio_format)
    finally:
        try:
            temp_wav_path.unlink(missing_ok=True)
        except OSError:
            logger.warning(f"[audio_ffmpeg_export] Failed to remove temp WAV: {temp_wav_path}")


def _run_ffmpeg(input_path: Path, output_path: Path, codec: str, audio_format: str) -> None:
    """Run ffmpeg to transcode ``input_path`` with ``codec``, mapping failures to RuntimeError."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(input_path),
        "-codec:a", codec,
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_SECONDS)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"ffmpeg executable not found. Install ffmpeg or add it to PATH "
            f"to export {audio_format} files."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"ffmpeg {audio_format} export timed out after {FFMPEG_TIMEOUT_SECONDS} seconds."
        ) from e
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
        raise RuntimeError(f"ffmpeg {audio_format} export failed: {stderr}") from e
