import json
import shutil
import subprocess

import numpy as np
import torch
import torchaudio

# A long clip decodes in well under a minute. The cap stops a stuck ffmpeg
# from blocking preprocessing forever.
_FFMPEG_TIMEOUT_SECONDS = 300


def _run_checked(command: list[str], *, text: bool) -> subprocess.CompletedProcess:
    """Run a command and include its stderr when it fails."""
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=text,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr or ""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        detail = detail.strip() or f"command exited {exc.returncode}"
        raise RuntimeError(detail) from exc


def _probe_audio_stream(ffprobe: str, audio_path: str) -> tuple[int, int]:
    """Return the sample rate and channel count of the first audio stream."""
    probe = _run_checked(
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
            "-i",
            audio_path,
        ],
        text=True,
    )
    try:
        streams = json.loads(probe.stdout)["streams"]
        stream = streams[0]
        sample_rate = int(stream["sample_rate"])
        channels = int(stream["channels"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"ffprobe returned no usable audio stream for {audio_path}"
        ) from exc
    if sample_rate < 1:
        raise RuntimeError(
            f"ffprobe reported sample rate {sample_rate} for {audio_path}"
        )
    if channels < 1:
        raise RuntimeError(f"ffprobe reported no audio channels for {audio_path}")
    return sample_rate, channels


def _load_via_ffmpeg(audio_path: str) -> tuple[torch.Tensor, int]:
    """Decode with the ffmpeg binary when torchaudio's TorchCodec build cannot.

    TorchCodec wheels only link FFmpeg 4-8. A newer system FFmpeg (for example
    Homebrew FFmpeg 9, libavutil.61) makes torchaudio.load raise before any
    samples are read. The ffmpeg CLI on PATH can still decode the file.
    """
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are not on PATH")

    sample_rate, channels = _probe_audio_stream(ffprobe, audio_path)
    decoded = _run_checked(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            audio_path,
            "-map",
            "0:a:0",
            "-ac",
            str(channels),
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-",
        ],
        text=False,
    )
    pcm = np.frombuffer(decoded.stdout, dtype=np.float32).copy()
    if pcm.size == 0:
        raise RuntimeError(f"ffmpeg decoded no samples from {audio_path}")
    if pcm.size % channels != 0:
        raise RuntimeError(
            f"ffmpeg output size is not divisible by {channels} channels"
        )
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
