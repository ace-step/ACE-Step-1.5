"""Target-latent preparation helpers for handler batch conditioning."""

from typing import List, Optional, Tuple

import torch
from loguru import logger


class ConditioningTargetMixin:
    """Mixin containing target-audio to latent preparation helpers.

    Depends on host members:
    - Attributes: ``device``, ``dtype``, ``sample_rate``, ``silence_latent``.
    - Methods: ``_ensure_silence_latent_on_device ``, ``_load_model_context``,
      ``is_silence``, ``_encode_audio_to_latents``, ``_decode_audio_codes_to_latents``.
    """

    def _prepare_target_latents_and_wavs(
        self,
        batch_size: int,
        target_wavs: torch.Tensor,
        audio_code_hints: List[Optional[str]],
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, int, torch.Tensor]:
        """Encode target audio/codes to latents and pad batch tensors."""
        self._ensure_silence_latent_on_device()

        with torch.inference_mode():
            target_latents_list = []
            latent_lengths = []
            target_wavs_list = [target_wavs[i].clone() for i in range(batch_size)]
            if target_wavs.device != self.device:
                target_wavs = target_wavs.to(self.device)

            with self._load_model_context("vae"):
                _cached_wav_ref: Optional[torch.Tensor] = None
                _cached_latent: Optional[torch.Tensor] = None

                for i in range(batch_size):
                    code_hint = audio_code_hints[i]
                    if code_hint:
                        logger.info(f"[generate_music] Decoding audio codes for item {i}...")
                        decoded_latents = self._decode_audio_codes_to_latents(code_hint)
                        if decoded_latents is not None:
                            decoded_latents = decoded_latents.squeeze(0)
                            target_latents_list.append(decoded_latents)
                            latent_lengths.append(decoded_latents.shape[0])
                            frames_from_codes = max(1, int(decoded_latents.shape[0] * 1920))
                            target_wavs_list[i] = torch.zeros(2, frames_from_codes)
                            continue

                    current_wav = target_wavs_list[i].to(self.device).unsqueeze(0)
                    if self.is_silence(current_wav):
                        expected_latent_length = current_wav.shape[-1] // 1920
                        target_latent = self.silence_latent[0, :expected_latent_length, :]
                    else:
                        if (
                            _cached_wav_ref is not None
                            and _cached_latent is not None
                            and _cached_wav_ref.shape == current_wav.shape
                            and torch.equal(_cached_wav_ref, current_wav)
                        ):
                            logger.info(
                                f"[generate_music] Reusing cached VAE latents for item {i} (same audio as previous item)"
                            )
                            target_latent = _cached_latent.clone()
                        else:
                            logger.info(f"[generate_music] Encoding target audio to latents for item {i}...")
                            target_latent = self._encode_audio_to_latents(current_wav.squeeze(0))
                            _cached_wav_ref = current_wav
                            _cached_latent = target_latent
                    target_latents_list.append(target_latent)
                    latent_lengths.append(target_latent.shape[0])

            max_target_frames = max(wav.shape[-1] for wav in target_wavs_list)
            padded_target_wavs = []
            for wav in target_wavs_list:
                if wav.shape[-1] < max_target_frames:
                    pad_frames = max_target_frames - wav.shape[-1]
                    wav = torch.nn.functional.pad(wav, (0, pad_frames), "constant", 0)
                padded_target_wavs.append(wav)
            target_wavs = torch.stack(padded_target_wavs)

            max_latent_length = max(latent.shape[0] for latent in target_latents_list)
            max_latent_length = max(128, max_latent_length)
            silence_latent_tiled = self.silence_latent[0, :max_latent_length, :]

            padded_latents = []
            for latent in target_latents_list:
                latent_length = latent.shape[0]
                if latent_length < max_latent_length:
                    pad_length = max_latent_length - latent_length
                    latent = torch.cat([latent, self.silence_latent[0, :pad_length, :]], dim=0)
                padded_latents.append(latent)

            target_latents = torch.stack(padded_latents)
            latent_masks = torch.stack(
                [
                    torch.cat(
                        [
                            torch.ones(l, dtype=torch.long, device=self.device),
                            torch.zeros(max_latent_length - l, dtype=torch.long, device=self.device),
                        ]
                    )
                    for l in latent_lengths
                ]
            )
            return target_wavs, target_latents, latent_masks, max_latent_length, silence_latent_tiled
