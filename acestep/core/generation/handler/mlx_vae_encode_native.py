"""Native MLX VAE encode helpers for audio-to-latent conversion."""

import math
import time as _time

import numpy as np
import torch
from loguru import logger
from tqdm import tqdm


class MlxVaeEncodeNativeMixin:
    """Encode MLX audio samples into latent tensors with overlap-discard tiling."""

    def _resolve_mlx_encode_fn(self):
        """Resolve the active MLX encode callable from compiled or model state.

        Returns:
            Any: Callable that encodes ``[1, S, C]`` MLX audio samples.

        Raises:
            RuntimeError: If no compiled callable exists and ``self.mlx_vae`` is missing.
        """
        encode_fn = getattr(self, "_mlx_compiled_encode_sample", None)
        if encode_fn is not None:
            return encode_fn
        if self.mlx_vae is None:
            raise RuntimeError("MLX VAE encode requested but mlx_vae is not initialized.")
        return self.mlx_vae.encode_and_sample

    def _mlx_vae_encode_sample(self, audio_torch):
        """Encode batched PyTorch audio to MLX latents.

        Args:
            audio_torch: Audio tensor shaped ``[batch, channels, samples]``.

        Returns:
            torch.Tensor: Latent tensor shaped ``[batch, channels, frames]``.
        """
        import mlx.core as mx

        audio_np = audio_torch.detach().cpu().float().numpy()
        audio_nlc = np.transpose(audio_np, (0, 2, 1))
        batch_size = audio_nlc.shape[0]
        sample_frames = audio_nlc.shape[1]

        mlx_encode_chunk = 48000 * 30
        mlx_encode_overlap = 48000 * 2
        if sample_frames <= mlx_encode_chunk:
            chunks_per_sample = 1
        else:
            stride = mlx_encode_chunk - 2 * mlx_encode_overlap
            chunks_per_sample = math.ceil(sample_frames / stride)
        total_work = batch_size * chunks_per_sample

        t_start = _time.time()
        vae_dtype = getattr(self, "_mlx_vae_dtype", mx.float32)
        encode_fn = self._resolve_mlx_encode_fn()

        latent_parts = []
        pbar = tqdm(
            total=total_work,
            desc=f"MLX VAE Encode (native, n={batch_size})",
            disable=self.disable_tqdm,
            unit="chunk",
        )
        for idx in range(batch_size):
            single = mx.array(audio_nlc[idx : idx + 1])
            if single.dtype != vae_dtype:
                single = single.astype(vae_dtype)
            latent = self._mlx_encode_single(single, pbar=pbar, encode_fn=encode_fn)
            if latent.dtype != mx.float32:
                latent = latent.astype(mx.float32)
            mx.eval(latent)
            latent_parts.append(np.array(latent))
            mx.clear_cache()
        pbar.close()

        elapsed = _time.time() - t_start
        logger.info(
            f"[MLX-VAE] Encoded {batch_size} sample(s), {sample_frames} audio frames -> "
            f"latent in {elapsed:.2f}s (dtype={vae_dtype})"
        )

        latent_nlc = np.concatenate(latent_parts, axis=0)
        latent_ncl = np.transpose(latent_nlc, (0, 2, 1))
        return torch.from_numpy(latent_ncl)

    def _mlx_encode_single(self, audio_nlc, pbar=None, encode_fn=None):
        """Encode one MLX audio sample with optional overlap-discard tiling.

        Args:
            audio_nlc: MLX array in ``[1, samples, channels]`` layout.
            pbar: Optional progress-bar object with ``update``.
            encode_fn: Optional encode callable; falls back to compiled encode.

        Returns:
            Any: MLX array in ``[1, frames, channels]`` layout.
        """
        import mlx.core as mx

        if encode_fn is None:
            encode_fn = self._resolve_mlx_encode_fn()

        sample_frames = audio_nlc.shape[1]
        mlx_encode_chunk = 48000 * 30
        mlx_encode_overlap = 48000 * 2

        if sample_frames <= mlx_encode_chunk:
            result = encode_fn(audio_nlc)
            mx.eval(result)
            if pbar is not None:
                pbar.update(1)
            return result

        stride = mlx_encode_chunk - 2 * mlx_encode_overlap
        num_steps = math.ceil(sample_frames / stride)
        encoded_parts = []
        downsample_factor = None

        for idx in range(num_steps):
            core_start = idx * stride
            core_end = min(core_start + stride, sample_frames)
            win_start = max(0, core_start - mlx_encode_overlap)
            win_end = min(sample_frames, core_end + mlx_encode_overlap)

            chunk = audio_nlc[:, win_start:win_end, :]
            latent_chunk = encode_fn(chunk)
            mx.eval(latent_chunk)
            if downsample_factor is None:
                downsample_factor = chunk.shape[1] / latent_chunk.shape[1]

            trim_start = int(round((core_start - win_start) / downsample_factor))
            trim_end = int(round((win_end - core_end) / downsample_factor))
            latent_len = latent_chunk.shape[1]
            end_idx = latent_len - trim_end if trim_end > 0 else latent_len
            encoded_parts.append(latent_chunk[:, trim_start:end_idx, :])
            if pbar is not None:
                pbar.update(1)

        return mx.concatenate(encoded_parts, axis=1)
