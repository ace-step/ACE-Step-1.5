"""VAE encode orchestration helpers for tiled audio-to-latent conversion."""

import math
from typing import Optional

import torch
from loguru import logger

from acestep.gpu_config import get_gpu_memory_gb


class VaeEncodeMixin:
    """High-level VAE encode entrypoints and runtime chunk policy."""

    def tiled_encode(self, audio, chunk_size=None, overlap=None, offload_latent_to_cpu=True):
        """Encode audio to latents using overlap-discard tiling.

        Args:
            audio: Tensor shaped ``[batch, channels, samples]`` or ``[channels, samples]``.
            chunk_size: Audio chunk size in samples; auto-selected when ``None``.
            overlap: Overlap in samples; defaults to 2 seconds at 48kHz.
            offload_latent_to_cpu: Whether to offload chunk outputs to CPU.

        Returns:
            Latent tensor shaped ``[batch, latent_channels, latent_frames]``.
        """
        # ---- MLX fast path (macOS Apple Silicon) ----
        if self.use_mlx_vae and self.mlx_vae is not None:
            input_was_2d = audio.dim() == 2
            if input_was_2d:
                audio = audio.unsqueeze(0)
            try:
                result = self._mlx_vae_encode_sample(audio)
                if input_was_2d:
                    result = result.squeeze(0)
                return result
            except Exception as exc:
                logger.warning(
                    f"[tiled_encode] MLX VAE encode failed ({type(exc).__name__}: {exc}), "
                    f"falling back to PyTorch VAE..."
                )
                if input_was_2d:
                    audio = audio.squeeze(0)

        # ---- PyTorch path (CUDA / MPS / CPU) ----
        if chunk_size is None:
            gpu_memory = get_gpu_memory_gb()
            if gpu_memory <= 0 and self.device == "mps":
                mem_gb = self._get_effective_mps_memory_gb()
                if mem_gb is not None:
                    gpu_memory = mem_gb
            chunk_size = 48000 * 15 if gpu_memory <= 8 else 48000 * 30
        if overlap is None:
            overlap = 48000 * 2

        input_was_2d = audio.dim() == 2
        if input_was_2d:
            audio = audio.unsqueeze(0)

        batch_size, _channels, samples = audio.shape

        if samples <= chunk_size:
            vae_input = audio.to(self.device).to(self.vae.dtype)
            with torch.inference_mode():
                latents = self.vae.encode(vae_input).latent_dist.sample()
            if input_was_2d:
                latents = latents.squeeze(0)
            return latents

        stride = chunk_size - 2 * overlap
        if stride <= 0:
            raise ValueError(f"chunk_size {chunk_size} must be > 2 * overlap {overlap}")

        num_steps = math.ceil(samples / stride)
        if offload_latent_to_cpu:
            result = self._tiled_encode_offload_cpu(audio, batch_size, samples, stride, overlap, num_steps, chunk_size)
        else:
            result = self._tiled_encode_gpu(audio, batch_size, samples, stride, overlap, num_steps, chunk_size)

        if input_was_2d:
            result = result.squeeze(0)
        return result
