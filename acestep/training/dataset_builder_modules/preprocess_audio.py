import json
import shutil
import subprocess

import numpy as np
import torch
import torchaudio


def _load_via_ffmpeg(audio_path: str) -> tuple[torch.Tensor, int]:
    """Decode with the ffmpeg binary when torchaudio's TorchCodec build cannot.

    TorchCodec wheels only link FFmpeg 4–8. A newer system FFmpeg (for example
    Homebrew FFmpeg 9, libavutil.61) makes torchaudio.load raise before any
    samples are read. The ffmpeg CLI on PATH can still decode the file.
    """
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are not on PATH")

    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels",
            "-of",
            "json",
            audio_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    sample_rate = int(stream["sample_rate"])
    channels = int(stream["channels"])
    if channels < 1:
        raise RuntimeError(f"ffprobe reported no audio channels for {audio_path}")

    decoded = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            audio_path,
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    pcm = np.frombuffer(decoded.stdout, dtype=np.float32).copy()
    if pcm.size % channels != 0:
        raise RuntimeError(f"ffmpeg output size is not divisible by {channels} channels")
    audio = torch.from_numpy(pcm.reshape(-1, channels).T).contiguous()
    return audio, sample_rate


def load_audio_stereo(audio_path: str, target_sample_rate: int, max_duration: float):
    """Load audio, resample, convert to stereo, and truncate."""
    try:
        audio, sr = torchaudio.load(audio_path)
    except Exception as exc:
        try:
            audio, sr = _load_via_ffmpeg(audio_path)
        except Exception as fallback_exc:
            raise RuntimeError(
                f"Could not decode {audio_path}. torchaudio failed ({exc}); "
                f"ffmpeg fallback failed ({fallback_exc})."
            ) from fallback_exc

    if sr != target_sample_rate:
        resampler = torchaudio.transforms.Resample(sr, target_sample_rate)
        audio = resampler(audio)

    if audio.shape[0] == 1:
        audio = audio.repeat(2, 1)
    elif audio.shape[0] > 2:
        audio = audio[:2, :]

    max_samples = int(max_duration * target_sample_rate)
    if audio.shape[1] > max_samples:
        audio = audio[:, :max_samples]

    return audio, sr
