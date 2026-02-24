"""Chunk-level VAE decode helpers used by tiled decode orchestration."""

import math

import torch
from loguru import logger
from tqdm import tqdm


class VaeDecodeChunksMixin:
    """Implement chunked decode strategies for GPU and CPU-offload modes."""

    def _tiled_decode_inner(self, latents, chunk_size, overlap, offload_wav_to_cpu):
        """Run tiled decode with adaptive overlap and OOM fallbacks."""
        bsz, _channels, latent_frames = latents.shape

        # Batch-sequential decode keeps peak VRAM stable across batch sizes.
        if bsz > 1:
            logger.info(f"[tiled_decode] Batch size {bsz} > 1; decoding samples sequentially to save VRAM")
            per_sample_results = []
            for b_idx in range(bsz):
                single = latents[b_idx : b_idx + 1]
                decoded = self._tiled_decode_inner(single, chunk_size, overlap, offload_wav_to_cpu)
                per_sample_results.append(decoded.cpu() if decoded.device.type != "cpu" else decoded)
                self._empty_cache()
            result = torch.cat(per_sample_results, dim=0)
            if latents.device.type != "cpu" and not offload_wav_to_cpu:
                result = result.to(latents.device)
            return result

        effective_overlap = overlap
        while chunk_size - 2 * effective_overlap <= 0 and effective_overlap > 0:
            effective_overlap = effective_overlap // 2
        if effective_overlap != overlap:
            logger.warning(
                f"[tiled_decode] Reduced overlap from {overlap} to {effective_overlap} for chunk_size={chunk_size}"
            )
        overlap = effective_overlap

        if latent_frames <= chunk_size:
            try:
                decoder_output = self.vae.decode(latents)
                result = decoder_output.sample
                del decoder_output
                return result
            except torch.cuda.OutOfMemoryError:
                logger.warning("[tiled_decode] OOM on direct decode, falling back to CPU VAE decode")
                self._empty_cache()
                return self._decode_on_cpu(latents)

        stride = chunk_size - 2 * overlap
        if stride <= 0:
            raise ValueError(f"chunk_size {chunk_size} must be > 2 * overlap {overlap}")

        num_steps = math.ceil(latent_frames / stride)

        if offload_wav_to_cpu:
            try:
                return self._tiled_decode_offload_cpu(latents, bsz, latent_frames, stride, overlap, num_steps)
            except torch.cuda.OutOfMemoryError:
                logger.warning(
                    f"[tiled_decode] OOM during offload_cpu decode with chunk_size={chunk_size}, "
                    "falling back to CPU VAE decode"
                )
                self._empty_cache()
                return self._decode_on_cpu(latents)

        try:
            return self._tiled_decode_gpu(latents, stride, overlap, num_steps)
        except torch.cuda.OutOfMemoryError:
            logger.warning(
                f"[tiled_decode] OOM during GPU decode with chunk_size={chunk_size}, "
                "falling back to CPU offload path"
            )
            self._empty_cache()
            try:
                return self._tiled_decode_offload_cpu(latents, bsz, latent_frames, stride, overlap, num_steps)
            except torch.cuda.OutOfMemoryError:
                logger.warning("[tiled_decode] OOM even with offload path, falling back to full CPU VAE decode")
                self._empty_cache()
                return self._decode_on_cpu(latents)

    def _tiled_decode_gpu(self, latents, stride, overlap, num_steps):
        """Decode chunks and keep decoded audio tensors on GPU."""
        decoded_audio_list = []
        upsample_factor = None

        for i in tqdm(range(num_steps), desc="Decoding audio chunks", disable=self.disable_tqdm):
            core_start = i * stride
            core_end = min(core_start + stride, latents.shape[-1])
            win_start = max(0, core_start - overlap)
            win_end = min(latents.shape[-1], core_end + overlap)

            latent_chunk = latents[:, :, win_start:win_end]
            decoder_output = self.vae.decode(latent_chunk)
            audio_chunk = decoder_output.sample
            del decoder_output

            if upsample_factor is None:
                upsample_factor = audio_chunk.shape[-1] / latent_chunk.shape[-1]

            added_start = core_start - win_start
            trim_start = int(round(added_start * upsample_factor))
            added_end = win_end - core_end
            trim_end = int(round(added_end * upsample_factor))

            audio_len = audio_chunk.shape[-1]
            end_idx = audio_len - trim_end if trim_end > 0 else audio_len
            audio_core = audio_chunk[:, :, trim_start:end_idx]
            decoded_audio_list.append(audio_core)

        return torch.cat(decoded_audio_list, dim=-1)

    def _tiled_decode_offload_cpu(self, latents, bsz, latent_frames, stride, overlap, num_steps):
        """Decode chunks on GPU and copy trimmed audio cores to a CPU buffer."""
        first_core_end = min(stride, latent_frames)
        first_win_end = min(latent_frames, first_core_end + overlap)
        first_latent_chunk = latents[:, :, 0:first_win_end]
        first_decoder_output = self.vae.decode(first_latent_chunk)
        first_audio_chunk = first_decoder_output.sample
        del first_decoder_output

        upsample_factor = first_audio_chunk.shape[-1] / first_latent_chunk.shape[-1]
        audio_channels = first_audio_chunk.shape[1]

        total_audio_length = int(round(latent_frames * upsample_factor))
        final_audio = torch.zeros(bsz, audio_channels, total_audio_length, dtype=first_audio_chunk.dtype, device="cpu")

        first_added_end = first_win_end - first_core_end
        first_trim_end = int(round(first_added_end * upsample_factor))
        first_audio_len = first_audio_chunk.shape[-1]
        first_end_idx = first_audio_len - first_trim_end if first_trim_end > 0 else first_audio_len

        first_audio_core = first_audio_chunk[:, :, :first_end_idx]
        audio_write_pos = first_audio_core.shape[-1]
        final_audio[:, :, :audio_write_pos] = first_audio_core.cpu()

        del first_audio_chunk, first_audio_core, first_latent_chunk

        for i in tqdm(range(1, num_steps), desc="Decoding audio chunks", disable=self.disable_tqdm):
            core_start = i * stride
            core_end = min(core_start + stride, latent_frames)
            win_start = max(0, core_start - overlap)
            win_end = min(latent_frames, core_end + overlap)

            latent_chunk = latents[:, :, win_start:win_end]
            decoder_output = self.vae.decode(latent_chunk)
            audio_chunk = decoder_output.sample
            del decoder_output

            added_start = core_start - win_start
            trim_start = int(round(added_start * upsample_factor))
            added_end = win_end - core_end
            trim_end = int(round(added_end * upsample_factor))

            audio_len = audio_chunk.shape[-1]
            end_idx = audio_len - trim_end if trim_end > 0 else audio_len
            audio_core = audio_chunk[:, :, trim_start:end_idx]

            core_len = audio_core.shape[-1]
            final_audio[:, :, audio_write_pos : audio_write_pos + core_len] = audio_core.cpu()
            audio_write_pos += core_len

            del audio_chunk, audio_core, latent_chunk

        return final_audio[:, :, :audio_write_pos]
