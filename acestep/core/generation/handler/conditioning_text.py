"""Text-token and hint preparation helpers for batch conditioning."""

from typing import List, Optional, Tuple

import torch
from loguru import logger

from acestep.constants import DEFAULT_DIT_INSTRUCTION, SFT_GEN_PROMPT


class ConditioningTextMixin:
    """Mixin containing prompt tokenization and LM-hint preparation.

    Depends on host members:
    - Attributes: ``text_tokenizer``, ``device``, ``dtype``, ``silence_latent``.
    - Methods: ``_decode_audio_codes_to_latents``, ``_extract_caption_and_language``,
      ``_format_instruction``, ``_format_lyrics``, ``_pad_sequences``.
    """

    def _prepare_precomputed_lm_hints(
        self,
        batch_size: int,
        audio_code_hints: List[Optional[str]],
        max_latent_length: int,
        silence_latent_tiled: torch.Tensor,
    ) -> Optional[torch.Tensor]:
        """Decode audio-code hints into padded 25Hz latent hints."""
        precomputed_lm_hints_25hz_list = []
        for i in range(batch_size):
            if audio_code_hints[i] is not None:
                logger.info(f"[generate_music] Decoding audio codes for LM hints for item {i}...")
                hints = self._decode_audio_codes_to_latents(audio_code_hints[i])
                if hints is not None:
                    if hints.shape[1] < max_latent_length:
                        pad_length = max_latent_length - hints.shape[1]
                        pad = self.silence_latent
                        if pad.dim() == 2:
                            pad = pad.unsqueeze(0)
                        if hints.dim() == 2:
                            hints = hints.unsqueeze(0)
                        pad_chunk = pad[:, :pad_length, :]
                        if pad_chunk.device != hints.device or pad_chunk.dtype != hints.dtype:
                            pad_chunk = pad_chunk.to(device=hints.device, dtype=hints.dtype)
                        hints = torch.cat([hints, pad_chunk], dim=1)
                    elif hints.shape[1] > max_latent_length:
                        hints = hints[:, :max_latent_length, :]
                    precomputed_lm_hints_25hz_list.append(hints[0])
                else:
                    precomputed_lm_hints_25hz_list.append(None)
            else:
                precomputed_lm_hints_25hz_list.append(None)

        if any(h is not None for h in precomputed_lm_hints_25hz_list):
            return torch.stack([h if h is not None else silence_latent_tiled for h in precomputed_lm_hints_25hz_list])
        return None

    def _prepare_text_conditioning_inputs(
        self,
        batch_size: int,
        instructions: List[str],
        captions: List[str],
        lyrics: List[str],
        parsed_metas: List[str],
        vocal_languages: List[str],
        audio_cover_strength: float,
    ) -> Tuple[List[str], torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, Optional[torch.Tensor], Optional[torch.Tensor]]:
        """Tokenize caption/lyric prompts and optional non-cover branch prompts."""
        actual_captions, actual_languages = self._extract_caption_and_language(parsed_metas, captions, vocal_languages)

        text_inputs = []
        text_token_idss = []
        text_attention_masks = []
        lyric_token_idss = []
        lyric_attention_masks = []

        for i in range(batch_size):
            instruction = self._format_instruction(
                instructions[i] if i < len(instructions) else DEFAULT_DIT_INSTRUCTION
            )
            actual_caption = actual_captions[i]
            actual_language = actual_languages[i]
            text_prompt = SFT_GEN_PROMPT.format(instruction, actual_caption, parsed_metas[i])

            if i == 0:
                logger.info(f"\n{'='*70}")
                logger.info("🔍 [DEBUG] DiT TEXT ENCODER INPUT (Inference)")
                logger.info(f"{'='*70}")
                logger.info(f"text_prompt:\n{text_prompt}")
                logger.info(f"{'='*70}")
                logger.info(f"lyrics_text:\n{self._format_lyrics(lyrics[i], actual_language)}")
                logger.info(f"{'='*70}\n")

            text_inputs_dict = self.text_tokenizer(
                text_prompt,
                padding="longest",
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            text_token_ids = text_inputs_dict.input_ids[0]
            text_attention_mask = text_inputs_dict.attention_mask[0].bool()

            lyrics_text = self._format_lyrics(lyrics[i], actual_language)
            lyrics_inputs_dict = self.text_tokenizer(
                lyrics_text,
                padding="longest",
                truncation=True,
                max_length=2048,
                return_tensors="pt",
            )
            lyric_token_ids = lyrics_inputs_dict.input_ids[0]
            lyric_attention_mask = lyrics_inputs_dict.attention_mask[0].bool()

            text_inputs.append(text_prompt + "\n\n" + lyrics_text)
            text_token_idss.append(text_token_ids)
            text_attention_masks.append(text_attention_mask)
            lyric_token_idss.append(lyric_token_ids)
            lyric_attention_masks.append(lyric_attention_mask)

        max_text_length = max(len(seq) for seq in text_token_idss)
        padded_text_token_idss = self._pad_sequences(text_token_idss, max_text_length, self.text_tokenizer.pad_token_id)
        padded_text_attention_masks = self._pad_sequences(text_attention_masks, max_text_length, 0)

        max_lyric_length = max(len(seq) for seq in lyric_token_idss)
        padded_lyric_token_idss = self._pad_sequences(lyric_token_idss, max_lyric_length, self.text_tokenizer.pad_token_id)
        padded_lyric_attention_masks = self._pad_sequences(lyric_attention_masks, max_lyric_length, 0)

        padded_non_cover_text_input_ids = None
        padded_non_cover_text_attention_masks = None
        if audio_cover_strength < 1.0:
            non_cover_text_input_ids = []
            non_cover_text_attention_masks = []
            for i in range(batch_size):
                text_prompt = SFT_GEN_PROMPT.format(
                    self._format_instruction(DEFAULT_DIT_INSTRUCTION), actual_captions[i], parsed_metas[i]
                )
                text_inputs_dict = self.text_tokenizer(
                    text_prompt,
                    padding="longest",
                    truncation=True,
                    max_length=256,
                    return_tensors="pt",
                )
                non_cover_text_input_ids.append(text_inputs_dict.input_ids[0])
                non_cover_text_attention_masks.append(text_inputs_dict.attention_mask[0].bool())
            padded_non_cover_text_input_ids = self._pad_sequences(
                non_cover_text_input_ids, max_text_length, self.text_tokenizer.pad_token_id
            )
            padded_non_cover_text_attention_masks = self._pad_sequences(non_cover_text_attention_masks, max_text_length, 0)

        return (
            text_inputs,
            padded_text_token_idss,
            padded_text_attention_masks,
            padded_lyric_token_idss,
            padded_lyric_attention_masks,
            padded_non_cover_text_input_ids,
            padded_non_cover_text_attention_masks,
        )
