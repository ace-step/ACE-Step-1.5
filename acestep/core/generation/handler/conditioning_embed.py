"""Reference/text embedding preprocessing helpers for conditioned generation."""

from typing import Dict, List, Tuple

import torch
from loguru import logger


class ConditioningEmbedMixin:
    """Mixin containing reference/text embedding preprocessing steps.

    Depends on host members:
    - Attributes: ``device``, ``dtype``, ``silence_latent``, ``text_encoder``.
    - Methods: ``_ensure_silence_latent_on_device``, ``_load_model_context``,
      ``tiled_encode``.
    """

    def infer_refer_latent(self, refer_audioss: List[List[torch.Tensor]]) -> Tuple[torch.Tensor, torch.Tensor]:
        """Infer packed reference-audio latents and order mask."""
        refer_audio_order_mask = []
        refer_audio_latents = []
        self._ensure_silence_latent_on_device()

        def _normalize_audio_2d(a: torch.Tensor) -> torch.Tensor:
            if not isinstance(a, torch.Tensor):
                raise TypeError(f"refer_audio must be a torch.Tensor, got {type(a)!r}")
            if a.dim() == 3 and a.shape[0] == 1:
                a = a.squeeze(0)
            if a.dim() == 1:
                a = a.unsqueeze(0)
            if a.dim() != 2:
                raise ValueError(f"refer_audio must be 1D/2D/3D(1,2,T); got shape={tuple(a.shape)}")
            if a.shape[0] == 1:
                a = torch.cat([a, a], dim=0)
            return a[:2]

        def _ensure_latent_3d(z: torch.Tensor) -> torch.Tensor:
            if z.dim() == 4 and z.shape[0] == 1:
                z = z.squeeze(0)
            if z.dim() == 2:
                z = z.unsqueeze(0)
            return z

        refer_encode_cache: Dict[int, torch.Tensor] = {}
        for batch_idx, refer_audios in enumerate(refer_audioss):
            if len(refer_audios) == 1 and torch.all(refer_audios[0] == 0.0):
                refer_audio_latent = _ensure_latent_3d(self.silence_latent[:, :750, :])
                refer_audio_latents.append(refer_audio_latent)
                refer_audio_order_mask.append(batch_idx)
            else:
                for refer_audio in refer_audios:
                    cache_key = refer_audio.data_ptr()
                    if cache_key in refer_encode_cache:
                        refer_audio_latent = refer_encode_cache[cache_key].clone()
                    else:
                        refer_audio = _normalize_audio_2d(refer_audio)
                        with torch.inference_mode():
                            refer_audio_latent = self.tiled_encode(refer_audio, offload_latent_to_cpu=True)
                        refer_audio_latent = refer_audio_latent.to(self.device).to(self.dtype)
                        if refer_audio_latent.dim() == 2:
                            refer_audio_latent = refer_audio_latent.unsqueeze(0)
                        refer_audio_latent = _ensure_latent_3d(refer_audio_latent.transpose(1, 2))
                        refer_encode_cache[cache_key] = refer_audio_latent
                    refer_audio_latents.append(refer_audio_latent)
                    refer_audio_order_mask.append(batch_idx)

        refer_audio_latents = torch.cat(refer_audio_latents, dim=0)
        refer_audio_order_mask = torch.tensor(refer_audio_order_mask, device=self.device, dtype=torch.long)
        return refer_audio_latents, refer_audio_order_mask

    def infer_text_embeddings(self, text_token_idss):
        """Infer text-token embeddings via text encoder."""
        with torch.inference_mode():
            return self.text_encoder(input_ids=text_token_idss, lyric_attention_mask=None).last_hidden_state

    def infer_lyric_embeddings(self, lyric_token_ids):
        """Infer lyric-token embeddings via text encoder embedding table."""
        with torch.inference_mode():
            return self.text_encoder.embed_tokens(lyric_token_ids)

    def preprocess_batch(self, batch) -> Tuple:
        """Preprocess an already prepared batch for DiT model input."""
        target_latents = batch["target_latents"]
        src_latents = batch["src_latents"]
        attention_mask = batch["latent_masks"]
        audio_codes = batch.get("audio_codes", None)
        audio_attention_mask = attention_mask

        dtype = target_latents.dtype
        device = target_latents.device

        keys = batch["keys"]
        with self._load_model_context("vae"):
            refer_audio_acoustic_hidden_states_packed, refer_audio_order_mask = self.infer_refer_latent(
                batch["refer_audioss"]
            )
        if refer_audio_acoustic_hidden_states_packed.dtype != dtype:
            refer_audio_acoustic_hidden_states_packed = refer_audio_acoustic_hidden_states_packed.to(dtype)

        chunk_mask = batch["chunk_masks"]
        chunk_mask = chunk_mask.to(device).unsqueeze(-1).repeat(1, 1, target_latents.shape[2])
        spans = batch["spans"]

        text_token_idss = batch["text_token_idss"]
        text_attention_mask = batch["text_attention_masks"]
        lyric_token_idss = batch["lyric_token_idss"]
        lyric_attention_mask = batch["lyric_attention_masks"]
        text_inputs = batch["text_inputs"]

        logger.info("[preprocess_batch] Inferring prompt embeddings...")
        with self._load_model_context("text_encoder"):
            text_hidden_states = self.infer_text_embeddings(text_token_idss)
            logger.info("[preprocess_batch] Inferring lyric embeddings...")
            lyric_hidden_states = self.infer_lyric_embeddings(lyric_token_idss)

            is_covers = batch["is_covers"]
            precomputed_lm_hints_25hz = batch.get("precomputed_lm_hints_25Hz", None)
            non_cover_text_input_ids = batch.get("non_cover_text_input_ids", None)
            non_cover_text_attention_masks = batch.get("non_cover_text_attention_masks", None)
            non_cover_text_hidden_states = None
            if non_cover_text_input_ids is not None:
                logger.info("[preprocess_batch] Inferring non-cover text embeddings...")
                non_cover_text_hidden_states = self.infer_text_embeddings(non_cover_text_input_ids)

        return (
            keys,
            text_inputs,
            src_latents,
            target_latents,
            text_hidden_states,
            text_attention_mask,
            lyric_hidden_states,
            lyric_attention_mask,
            audio_attention_mask,
            refer_audio_acoustic_hidden_states_packed,
            refer_audio_order_mask,
            chunk_mask,
            spans,
            is_covers,
            audio_codes,
            lyric_token_idss,
            precomputed_lm_hints_25hz,
            non_cover_text_hidden_states,
            non_cover_text_attention_masks,
        )
