"""Chunk-level VAE encode helpers for tiled audio-to-latent conversion."""

import torch
from tqdm import tqdm


class VaeEncodeChunksMixin:
    """Implement chunked encode strategies for GPU and CPU-offload modes."""

    def _tiled_encode_gpu(self, audio, batch_size, samples, stride, overlap, num_steps, chunk_size):
        """Standard tiled encode keeping all data on GPU."""
        _ = batch_size, chunk_size
        encoded_latent_list = []
        downsample_factor = None

        for i in tqdm(range(num_steps), desc="Encoding audio chunks", disable=self.disable_tqdm):
            core_start = i * stride
            core_end = min(core_start + stride, samples)
            win_start = max(0, core_start - overlap)
            win_end = min(samples, core_end + overlap)

            audio_chunk = audio[:, :, win_start:win_end].to(self.device).to(self.vae.dtype)
            with torch.inference_mode():
                latent_chunk = self.vae.encode(audio_chunk).latent_dist.sample()

            if downsample_factor is None:
                downsample_factor = audio_chunk.shape[-1] / latent_chunk.shape[-1]

            added_start = core_start - win_start
            trim_start = int(round(added_start / downsample_factor))
            added_end = win_end - core_end
            trim_end = int(round(added_end / downsample_factor))

            latent_len = latent_chunk.shape[-1]
            end_idx = latent_len - trim_end if trim_end > 0 else latent_len
            latent_core = latent_chunk[:, :, trim_start:end_idx]
            encoded_latent_list.append(latent_core)
            del audio_chunk

        return torch.cat(encoded_latent_list, dim=-1)

    def _tiled_encode_offload_cpu(self, audio, batch_size, samples, stride, overlap, num_steps, chunk_size):
        """Tiled encode that offloads latent chunks to CPU immediately."""
        _ = chunk_size
        first_core_end = min(stride, samples)
        first_win_end = min(samples, first_core_end + overlap)

        first_audio_chunk = audio[:, :, 0:first_win_end].to(self.device).to(self.vae.dtype)
        with torch.inference_mode():
            first_latent_chunk = self.vae.encode(first_audio_chunk).latent_dist.sample()

        downsample_factor = first_audio_chunk.shape[-1] / first_latent_chunk.shape[-1]
        latent_channels = first_latent_chunk.shape[1]

        total_latent_length = int(round(samples / downsample_factor))
        final_latents = torch.zeros(
            batch_size,
            latent_channels,
            total_latent_length,
            dtype=first_latent_chunk.dtype,
            device="cpu",
        )

        first_added_end = first_win_end - first_core_end
        first_trim_end = int(round(first_added_end / downsample_factor))
        first_latent_len = first_latent_chunk.shape[-1]
        first_end_idx = first_latent_len - first_trim_end if first_trim_end > 0 else first_latent_len

        first_latent_core = first_latent_chunk[:, :, :first_end_idx]
        latent_write_pos = first_latent_core.shape[-1]
        final_latents[:, :, :latent_write_pos] = first_latent_core.cpu()
        del first_audio_chunk, first_latent_chunk, first_latent_core

        for i in tqdm(range(1, num_steps), desc="Encoding audio chunks", disable=self.disable_tqdm):
            core_start = i * stride
            core_end = min(core_start + stride, samples)
            win_start = max(0, core_start - overlap)
            win_end = min(samples, core_end + overlap)

            audio_chunk = audio[:, :, win_start:win_end].to(self.device).to(self.vae.dtype)
            with torch.inference_mode():
                latent_chunk = self.vae.encode(audio_chunk).latent_dist.sample()

            added_start = core_start - win_start
            trim_start = int(round(added_start / downsample_factor))
            added_end = win_end - core_end
            trim_end = int(round(added_end / downsample_factor))

            latent_len = latent_chunk.shape[-1]
            end_idx = latent_len - trim_end if trim_end > 0 else latent_len
            latent_core = latent_chunk[:, :, trim_start:end_idx]

            core_len = latent_core.shape[-1]
            final_latents[:, :, latent_write_pos : latent_write_pos + core_len] = latent_core.cpu()
            latent_write_pos += core_len
            del audio_chunk, latent_chunk, latent_core

        return final_latents[:, :, :latent_write_pos]
