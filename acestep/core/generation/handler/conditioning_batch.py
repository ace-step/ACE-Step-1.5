"""Batch-conditioning orchestration helpers for handler decomposition."""

from typing import Any, Dict, List, Optional, Union

import torch

from acestep.constants import DEFAULT_DIT_INSTRUCTION


class ConditioningBatchMixin:
    """Mixin containing batch preparation orchestration.

    Depends on host members:
    - Attributes: ``device``, ``dtype``, ``sample_rate``.
    - Methods: ``_normalize_audio_code_hints``, ``_create_fallback_vocal_languages``,
      ``_parse_metas``, ``_normalize_instructions``, ``_prepare_target_latents_and_wavs``,
      ``_build_chunk_masks_and_src_latents``, ``_prepare_precomputed_lm_hints``,
      ``_prepare_text_conditioning_inputs``.
    """

    def _prepare_batch(
        self,
        captions: List[str],
        lyrics: List[str],
        keys: Optional[List[str]] = None,
        target_wavs: Optional[torch.Tensor] = None,
        refer_audios: Optional[List[List[torch.Tensor]]] = None,
        metas: Optional[List[Union[str, Dict[str, Any]]]] = None,
        vocal_languages: Optional[List[str]] = None,
        repainting_start: Optional[List[float]] = None,
        repainting_end: Optional[List[float]] = None,
        instructions: Optional[List[str]] = None,
        audio_code_hints: Optional[List[Optional[str]]] = None,
        audio_cover_strength: float = 1.0,
        cover_noise_strength: float = 0.0,
    ) -> Dict[str, Any]:
        """Prepare model-ready conditioning batch tensors and metadata.

        Args:
            captions: Per-item captions.
            lyrics: Per-item lyric strings.
            keys: Optional per-item keys.
            target_wavs: Target audio tensor batch.
            refer_audios: Optional nested reference-audio tensors.
            metas: Optional per-item metadata strings/dicts.
            vocal_languages: Optional per-item vocal language codes.
            repainting_start: Optional repaint start times.
            repainting_end: Optional repaint end times.
            instructions: Optional per-item generation instructions.
            audio_code_hints: Optional per-item serialized audio-code hints.
            audio_cover_strength: Blend factor for cover/non-cover conditioning.

        Returns:
            Batch dictionary containing padded tensors and conditioning metadata
            consumed by ``preprocess_batch`` and downstream generation.
        """
        batch_size = len(captions)
        audio_code_hints = self._normalize_audio_code_hints(audio_code_hints, batch_size)

        if refer_audios is None:
            refer_audios = [[torch.zeros(2, 30 * self.sample_rate)] for _ in range(batch_size)]
        for ii, refer_audio_list in enumerate(refer_audios):
            if isinstance(refer_audio_list, list):
                for idx, _ in enumerate(refer_audio_list):
                    refer_audio_list[idx] = refer_audio_list[idx].to(self.device).to(self._get_vae_dtype())
            elif isinstance(refer_audio_list, torch.Tensor):
                refer_audios[ii] = refer_audios[ii].to(self.device)

        if vocal_languages is None:
            vocal_languages = self._create_fallback_vocal_languages(batch_size)
        parsed_metas = self._parse_metas(metas)

        target_wavs, target_latents, latent_masks, max_latent_length, silence_latent_tiled = (
            self._prepare_target_latents_and_wavs(batch_size, target_wavs, audio_code_hints)
        )
        wav_lengths = torch.tensor([target_wavs.shape[-1]] * batch_size, dtype=torch.long)

        instructions = self._normalize_instructions(instructions, batch_size, DEFAULT_DIT_INSTRUCTION)
        chunk_masks, spans, is_covers, src_latents = self._build_chunk_masks_and_src_latents(
            batch_size,
            max_latent_length,
            instructions,
            audio_code_hints,
            target_wavs,
            target_latents,
            repainting_start,
            repainting_end,
            silence_latent_tiled,
        )
        precomputed_lm_hints_25hz = self._prepare_precomputed_lm_hints(
            batch_size, audio_code_hints, max_latent_length, silence_latent_tiled
        )
        (
            text_inputs,
            padded_text_token_idss,
            padded_text_attention_masks,
            padded_lyric_token_idss,
            padded_lyric_attention_masks,
            padded_non_cover_text_input_ids,
            padded_non_cover_text_attention_masks,
        ) = self._prepare_text_conditioning_inputs(
            batch_size,
            instructions,
            captions,
            lyrics,
            parsed_metas,
            vocal_languages,
            audio_cover_strength,
        )

        batch = {
            "keys": keys,
            "target_wavs": target_wavs.to(self.device),
            "refer_audioss": refer_audios,
            "wav_lengths": wav_lengths.to(self.device),
            "captions": captions,
            "lyrics": lyrics,
            "metas": parsed_metas,
            "vocal_languages": vocal_languages,
            "target_latents": target_latents,
            "src_latents": src_latents,
            "latent_masks": latent_masks,
            "chunk_masks": chunk_masks,
            "spans": spans,
            "text_inputs": text_inputs,
            "text_token_idss": padded_text_token_idss,
            "text_attention_masks": padded_text_attention_masks,
            "lyric_token_idss": padded_lyric_token_idss,
            "lyric_attention_masks": padded_lyric_attention_masks,
            "is_covers": is_covers,
            "precomputed_lm_hints_25Hz": precomputed_lm_hints_25hz,
            "non_cover_text_input_ids": padded_non_cover_text_input_ids,
            "non_cover_text_attention_masks": padded_non_cover_text_attention_masks,
        }
        for k, v in batch.items():
            if isinstance(v, torch.Tensor):
                batch[k] = v.to(self.device)
                if torch.is_floating_point(batch[k]):
                    batch[k] = batch[k].to(self.dtype)
        return batch
