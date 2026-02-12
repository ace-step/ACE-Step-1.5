"""Decode-related handler helpers."""

import math

import torch
from loguru import logger
from tqdm import tqdm


class DecodeMixin:
    """Mixin containing latent-to-audio decode helpers."""

    def _require_decode_attr(self, attr_name: str):
        if not hasattr(self, attr_name):
            raise AttributeError(f"DecodeMixin host is missing required attribute '{attr_name}'")
        return getattr(self, attr_name)

    def _mlx_vae_decode(self, latents_torch):
        """Decode latents using native MLX VAE.

        Args:
            latents_torch: PyTorch tensor [B, C, T] in NCL format.
                Internally transposed to NLC for MLX decode.

        Returns:
            PyTorch tensor [B, C_audio, T_audio] (NCL format).
        """
        import numpy as np
        import mlx.core as mx
        import time as _time

        self._require_decode_attr("mlx_vae")
        self._require_decode_attr("disable_tqdm")

        t_start = _time.time()

        latents_np = latents_torch.detach().cpu().float().numpy()
        latents_nlc = np.transpose(latents_np, (0, 2, 1))  # NCL -> NLC

        B = latents_nlc.shape[0]
        T = latents_nlc.shape[1]

        # Convert to model dtype (float16 for speed, float32 fallback)
        vae_dtype = getattr(self, "_mlx_vae_dtype", mx.float32)
        latents_mx = mx.array(latents_nlc).astype(vae_dtype)

        t_convert = _time.time()

        # Use compiled decode (kernel-fused) when available
        decode_fn = getattr(self, "_mlx_compiled_decode", self.mlx_vae.decode)

        # Process batch items sequentially (peak memory stays constant)
        audio_parts = []
        for b in range(B):
            single = latents_mx[b : b + 1]  # [1, T, C]
            decoded = self._mlx_decode_single(single, decode_fn=decode_fn)
            # Cast back to float32 for downstream torch compatibility
            if decoded.dtype != mx.float32:
                decoded = decoded.astype(mx.float32)
            mx.eval(decoded)
            audio_parts.append(np.array(decoded))
            mx.clear_cache()  # Free intermediate buffers between samples

        t_decode = _time.time()

        audio_nlc = np.concatenate(audio_parts, axis=0)  # [B, T_audio, C_audio]
        audio_ncl = np.transpose(audio_nlc, (0, 2, 1))  # NLC -> NCL

        t_elapsed = _time.time() - t_start
        logger.info(
            f"[MLX-VAE] Decoded {B} sample(s), {T} latent frames -> "
            f"audio in {t_elapsed:.2f}s "
            f"(convert={t_convert - t_start:.3f}s, decode={t_decode - t_convert:.2f}s, "
            f"dtype={vae_dtype})"
        )

        return torch.from_numpy(audio_ncl)

    def _mlx_decode_single(self, z_nlc, decode_fn=None):
        """Decode a single sample with optional tiling for very long sequences.

        Args:
            z_nlc: MLX array [1, T, C] in NLC format.
            decode_fn: Compiled or plain decode callable. Falls back to
                ``self._mlx_compiled_decode`` or ``self.mlx_vae.decode``.

        Returns:
            MLX array [1, T_audio, C_audio] in NLC format.
        """
        import mlx.core as mx

        self._require_decode_attr("mlx_vae")
        self._require_decode_attr("disable_tqdm")

        if decode_fn is None:
            decode_fn = getattr(self, "_mlx_compiled_decode", self.mlx_vae.decode)

        T = z_nlc.shape[1]
        # MLX unified memory: much larger chunk OK than PyTorch MPS.
        # 2048 latent frames ~= 87 seconds of audio, covering nearly all use cases.
        MLX_CHUNK = 2048
        MLX_OVERLAP = 64

        if T <= MLX_CHUNK:
            # No tiling needed; caller handles mx.eval()
            return decode_fn(z_nlc)

        # Overlap-discard tiling for very long sequences
        stride = MLX_CHUNK - 2 * MLX_OVERLAP
        num_steps = math.ceil(T / stride)
        decoded_parts = []
        upsample_factor = None

        for i in tqdm(range(num_steps), desc="Decoding audio chunks", disable=self.disable_tqdm):
            core_start = i * stride
            core_end = min(core_start + stride, T)
            win_start = max(0, core_start - MLX_OVERLAP)
            win_end = min(T, core_end + MLX_OVERLAP)

            chunk = z_nlc[:, win_start:win_end, :]
            audio_chunk = decode_fn(chunk)
            mx.eval(audio_chunk)

            if upsample_factor is None:
                upsample_factor = audio_chunk.shape[1] / chunk.shape[1]

            added_start = core_start - win_start
            trim_start = int(round(added_start * upsample_factor))
            added_end = win_end - core_end
            trim_end = int(round(added_end * upsample_factor))

            audio_len = audio_chunk.shape[1]
            end_idx = audio_len - trim_end if trim_end > 0 else audio_len
            # Guard against boundary/rounding collapse (or inconsistent decode lengths)
            # that can produce empty/invalid slices.
            trim_start = max(0, min(trim_start, audio_len))
            end_idx = max(0, min(end_idx, audio_len))
            if end_idx <= trim_start:
                if audio_len == 0:
                    continue
                trim_start = min(trim_start, audio_len - 1)
                end_idx = trim_start + 1
            decoded_parts.append(audio_chunk[:, trim_start:end_idx, :])

        return mx.concatenate(decoded_parts, axis=1)
