"""VAE decode orchestration helpers for tiled latent-to-audio conversion."""

from typing import Optional

import torch
from loguru import logger


class VaeDecodeMixin:
    """High-level VAE decode entrypoints and fallback policies."""

    # MPS-safe chunk parameters (class-level for testability)
    _MPS_DECODE_CHUNK_SIZE = 32
    _MPS_DECODE_OVERLAP = 8

    def tiled_decode(
        self,
        latents,
        chunk_size: Optional[int] = None,
        overlap: int = 64,
        offload_wav_to_cpu: Optional[bool] = None,
    ):
        """Decode latents using tiling to reduce VRAM usage.

        Uses overlap-discard chunking to avoid boundary artifacts while
        constraining peak decode memory.

        Args:
            latents: Tensor shaped ``[batch, channels, latent_frames]``.
            chunk_size: Chunk size in latent frames. When ``None``, an
                auto-tuned value is selected by runtime policy.
            overlap: Overlap in latent frames between adjacent windows.
            offload_wav_to_cpu: Whether decoded waveform chunks should be
                offloaded to CPU immediately to reduce VRAM pressure.

        Returns:
            Decoded waveform tensor shaped ``[batch, audio_channels, samples]``.
        """
        # ---- MLX fast path (macOS Apple Silicon) ----
        if self.use_mlx_vae and self.mlx_vae is not None:
            try:
                result = self._mlx_vae_decode(latents)
                return result
            except Exception as exc:
                logger.warning(
                    f"[tiled_decode] MLX VAE decode failed ({type(exc).__name__}: {exc}), "
                    f"falling back to PyTorch VAE..."
                )

        # ---- PyTorch path (CUDA / MPS / CPU) ----
        if chunk_size is None:
            chunk_size = self._get_auto_decode_chunk_size()
        if offload_wav_to_cpu is None:
            offload_wav_to_cpu = self._should_offload_wav_to_cpu()

        logger.info(
            f"[tiled_decode] chunk_size={chunk_size}, offload_wav_to_cpu={offload_wav_to_cpu}, "
            f"latents_shape={latents.shape}"
        )

        # MPS Conv1d has a hard output-size limit during temporal upsampling.
        _is_mps = self.device == "mps"
        if _is_mps:
            _mps_chunk = self._MPS_DECODE_CHUNK_SIZE
            _mps_overlap = self._MPS_DECODE_OVERLAP
            _needs_reduction = (chunk_size > _mps_chunk) or (overlap > _mps_overlap)
            if _needs_reduction:
                logger.info(
                    f"[tiled_decode] VAE decode via PyTorch MPS; reducing chunk_size from {chunk_size} "
                    f"to {min(chunk_size, _mps_chunk)} and overlap from {overlap} "
                    f"to {min(overlap, _mps_overlap)} to avoid MPS conv output limit."
                )
                chunk_size = min(chunk_size, _mps_chunk)
                overlap = min(overlap, _mps_overlap)

        try:
            return self._tiled_decode_inner(latents, chunk_size, overlap, offload_wav_to_cpu)
        except (NotImplementedError, RuntimeError) as exc:
            if not _is_mps:
                raise
            logger.warning(
                f"[tiled_decode] MPS decode failed ({type(exc).__name__}: {exc}), "
                f"falling back to CPU VAE decode..."
            )
            return self._tiled_decode_cpu_fallback(latents)

    def _tiled_decode_cpu_fallback(self, latents):
        """Last-resort CPU VAE decode when MPS fails unexpectedly."""
        _first_param = next(self.vae.parameters())
        vae_device = _first_param.device
        vae_dtype = _first_param.dtype
        try:
            self.vae = self.vae.cpu().float()
            latents_cpu = latents.to(device="cpu", dtype=torch.float32)
            decoder_output = self.vae.decode(latents_cpu)
            result = decoder_output.sample
            del decoder_output
            return result
        finally:
            # Always restore VAE to original device/dtype
            self.vae = self.vae.to(vae_dtype).to(vae_device)

    def _decode_on_cpu(self, latents):
        """Move VAE to CPU, decode there, then restore original device."""
        logger.warning("[_decode_on_cpu] Moving VAE to CPU for decode (VRAM too tight for GPU decode)")

        try:
            original_device = next(self.vae.parameters()).device
        except StopIteration:
            original_device = torch.device("cpu")

        vae_cpu_dtype = self._get_vae_dtype("cpu")
        self._recursive_to_device(self.vae, "cpu", vae_cpu_dtype)
        self._empty_cache()

        latents_cpu = latents.cpu().to(vae_cpu_dtype)
        try:
            with torch.inference_mode():
                decoder_output = self.vae.decode(latents_cpu)
                result = decoder_output.sample
                del decoder_output
        finally:
            if original_device.type != "cpu":
                vae_gpu_dtype = self._get_vae_dtype(str(original_device))
                self._recursive_to_device(self.vae, original_device, vae_gpu_dtype)

        logger.info(f"[_decode_on_cpu] CPU decode complete, result shape={result.shape}")
        return result
