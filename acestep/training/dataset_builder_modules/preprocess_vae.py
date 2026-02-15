"""VAE encoding helpers for training preprocessing.

Provides both a simple one-shot ``vae_encode`` (kept for backward
compatibility) and a tiled variant ``tiled_vae_encode`` that processes
long audio in overlapping chunks to cap peak VRAM usage.
"""

import math
from typing import Optional

import torch


# Target sample rate for ACE-Step models (used for chunk-size heuristics)
_TARGET_SR = 48000


def vae_encode(vae, audio, dtype):
    """VAE encode audio to get target latents (one-shot, no tiling).

    For long audio this may OOM on low-VRAM GPUs.  Prefer
    :func:`tiled_vae_encode` when peak memory is a concern.

    Args:
        vae: ``AutoencoderOobleck`` model (on device, eval mode).
        audio: ``[B, C, S]`` audio tensor.
        dtype: Target dtype for the output latents.

    Returns:
        Latent tensor ``[B, T, 64]``.
    """
    model_device = next(vae.parameters()).device
    if audio.device != model_device:
        audio = audio.to(model_device)

    latent = vae.encode(audio).latent_dist.sample()
    target_latents = latent.transpose(1, 2).to(dtype)
    return target_latents


def tiled_vae_encode(
    vae,
    audio: torch.Tensor,
    dtype: torch.dtype,
    chunk_size: Optional[int] = None,
    overlap: int = 96000,
) -> torch.Tensor:
    """Encode audio through the VAE using overlap-discard tiling.

    Processes long audio in chunks to avoid OOM on the monolithic
    ``vae.encode()`` call.  Short audio (shorter than *chunk_size*) is
    encoded directly without tiling overhead.

    Args:
        vae: ``AutoencoderOobleck`` VAE model (on device, eval mode).
        audio: Audio tensor ``[B, C, S]`` (batch, channels, samples).
        dtype: Target dtype for the output latents.
        chunk_size: Audio samples per chunk.  ``None`` = auto-select
            based on available GPU memory (30 s for >=8 GB, 15 s
            otherwise).
        overlap: Overlap in audio samples between adjacent chunks
            (default 2 s at 48 kHz = 96 000).

    Returns:
        Latent tensor ``[B, T, 64]``, cast to *dtype*.
    """
    vae_device = next(vae.parameters()).device
    vae_dtype = vae.dtype

    # Auto-select chunk size based on GPU VRAM
    if chunk_size is None:
        gpu_mem_gb = 0.0
        if torch.cuda.is_available():
            try:
                props = torch.cuda.get_device_properties(vae_device)
                gpu_mem_gb = props.total_mem / (1024 ** 3)
            except Exception:
                pass
        chunk_size = _TARGET_SR * 15 if gpu_mem_gb <= 8 else _TARGET_SR * 30

    B, C, S = audio.shape

    # Short audio -- direct encode (no tiling needed)
    if S <= chunk_size:
        vae_input = audio.to(vae_device, dtype=vae_dtype)
        with torch.inference_mode():
            latents = vae.encode(vae_input).latent_dist.sample()
        return latents.transpose(1, 2).to(dtype)

    # Calculate stride (core region per chunk, excluding overlap)
    stride = chunk_size - 2 * overlap
    if stride <= 0:
        raise ValueError(
            f"chunk_size ({chunk_size}) must be > 2 * overlap ({overlap})"
        )

    num_steps = math.ceil(S / stride)
    downsample_factor: Optional[float] = None
    latent_write_pos = 0
    final_latents: Optional[torch.Tensor] = None

    for i in range(num_steps):
        core_start = i * stride
        core_end = min(core_start + stride, S)

        # Window with overlap on both sides
        win_start = max(0, core_start - overlap)
        win_end = min(S, core_end + overlap)

        chunk = audio[:, :, win_start:win_end].to(vae_device, dtype=vae_dtype)

        with torch.inference_mode():
            latent_chunk = vae.encode(chunk).latent_dist.sample()

        # Determine downsample factor from the first chunk
        if downsample_factor is None:
            downsample_factor = chunk.shape[-1] / latent_chunk.shape[-1]
            total_latent_len = int(round(S / downsample_factor))
            final_latents = torch.zeros(
                B, latent_chunk.shape[1], total_latent_len,
                dtype=latent_chunk.dtype, device="cpu",
            )

        # Trim the overlap regions from the latent
        added_start = core_start - win_start
        trim_start = int(round(added_start / downsample_factor))

        added_end = win_end - core_end
        trim_end = int(round(added_end / downsample_factor))

        lat_len = latent_chunk.shape[-1]
        end_idx = lat_len - trim_end if trim_end > 0 else lat_len
        latent_core = latent_chunk[:, :, trim_start:end_idx]

        # Copy to pre-allocated CPU tensor
        core_len = latent_core.shape[-1]
        assert final_latents is not None
        final_latents[:, :, latent_write_pos:latent_write_pos + core_len] = (
            latent_core.cpu()
        )
        latent_write_pos += core_len

        del chunk, latent_chunk, latent_core

    # Trim to actual written length
    assert final_latents is not None
    final_latents = final_latents[:, :, :latent_write_pos]

    # Transpose to (B, T, 64) and cast -- matches vae_encode output format
    return final_latents.transpose(1, 2).to(dtype)
