"""Native MLX VAE decode helpers for latent-to-audio conversion."""

import math
import time as _time

import numpy as np
import torch
from loguru import logger
from tqdm import tqdm


class MlxVaeDecodeNativeMixin:
    """Decode MLX latents with optional overlap-discard tiling."""

    def _resolve_mlx_decode_fn(self):
        """Resolve the active MLX decode callable from compiled or model state.

        Returns:
            Any: Callable that decodes ``[1, T, C]`` MLX latents.

        Raises:
            RuntimeError: If no compiled callable exists and ``self.mlx_vae`` is missing.
        """
        decode_fn = getattr(self, "_mlx_compiled_decode", None)
        if decode_fn is not None:
            return decode_fn
        if self.mlx_vae is None:
            raise RuntimeError("MLX VAE decode requested but mlx_vae is not initialized.")
        return self.mlx_vae.decode

    def _mlx_vae_decode(self, latents_torch):
        """Decode batched PyTorch latents using native MLX VAE decode.

        Args:
            latents_torch: Latent tensor shaped ``[batch, channels, frames]``.

        Returns:
            torch.Tensor: Decoded audio shaped ``[batch, channels, samples]``.
        """
        import mlx.core as mx

        t_start = _time.time()
        latents_np = latents_torch.detach().cpu().float().numpy()
        latents_nlc = np.transpose(latents_np, (0, 2, 1))
        batch_size = latents_nlc.shape[0]
        latent_frames = latents_nlc.shape[1]

        vae_dtype = getattr(self, "_mlx_vae_dtype", mx.float32)
        latents_mx = mx.array(latents_nlc).astype(vae_dtype)
        t_convert = _time.time()

        decode_fn = self._resolve_mlx_decode_fn()
        audio_parts = []
        for idx in range(batch_size):
            decoded = self._mlx_decode_single(latents_mx[idx : idx + 1], decode_fn=decode_fn)
            if decoded.dtype != mx.float32:
                decoded = decoded.astype(mx.float32)
            mx.eval(decoded)
            audio_parts.append(np.array(decoded))
            mx.clear_cache()

        t_decode = _time.time()
        audio_nlc = np.concatenate(audio_parts, axis=0)
        audio_ncl = np.transpose(audio_nlc, (0, 2, 1))
        elapsed = _time.time() - t_start
        logger.info(
            f"[MLX-VAE] Decoded {batch_size} sample(s), {latent_frames} latent frames -> "
            f"audio in {elapsed:.2f}s "
            f"(convert={t_convert - t_start:.3f}s, decode={t_decode - t_convert:.2f}s, "
            f"dtype={vae_dtype})"
        )
        return torch.from_numpy(audio_ncl)

    def _mlx_decode_single(self, z_nlc, decode_fn=None):
        """Decode a single MLX latent sample with optional tiling.

        Args:
            z_nlc: MLX array in ``[1, frames, channels]`` layout.
            decode_fn: Optional decode callable; falls back to compiled decode.

        Returns:
            Any: MLX array in ``[1, samples, channels]`` layout.
        """
        import mlx.core as mx

        if decode_fn is None:
            decode_fn = self._resolve_mlx_decode_fn()

        latent_frames = z_nlc.shape[1]
        mlx_chunk = 2048
        mlx_overlap = 64

        if latent_frames <= mlx_chunk:
            return decode_fn(z_nlc)

        stride = mlx_chunk - 2 * mlx_overlap
        num_steps = math.ceil(latent_frames / stride)
        decoded_parts = []
        upsample_factor = None

        for idx in tqdm(range(num_steps), desc="Decoding audio chunks", disable=self.disable_tqdm):
            core_start = idx * stride
            core_end = min(core_start + stride, latent_frames)
            win_start = max(0, core_start - mlx_overlap)
            win_end = min(latent_frames, core_end + mlx_overlap)

            chunk = z_nlc[:, win_start:win_end, :]
            audio_chunk = decode_fn(chunk)
            mx.eval(audio_chunk)
            if upsample_factor is None:
                upsample_factor = audio_chunk.shape[1] / chunk.shape[1]

            trim_start = int(round((core_start - win_start) * upsample_factor))
            trim_end = int(round((win_end - core_end) * upsample_factor))
            audio_len = audio_chunk.shape[1]
            end_idx = audio_len - trim_end if trim_end > 0 else audio_len
            decoded_parts.append(audio_chunk[:, trim_start:end_idx, :])

        return mx.concatenate(decoded_parts, axis=1)
