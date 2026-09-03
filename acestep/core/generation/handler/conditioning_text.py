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
                        if hints.dim() == 2:
                            hints = hints.unsqueeze(0)
                        # 用 _get_silence_latent_slice 而不是 self.silence_latent[:, :pad_length, :]:
                        # 后者在 silence_latent 的帧数不足 pad_length 时会静默给出一个更短的
                        # 切片, cat 之后 hints 达不到 max_latent_length, 一直到下面 torch.stack
                        # 才炸 —— 而 stack 那一行要把它和 silence_latent_tiled 并排, 后者是走
                        # _get_silence_latent_slice 平铺出来的、长度精确, 于是报
                        #   stack expects each tensor to be equal size,
                        #   but got [15010, 64] at entry 0 and [17500, 64] at entry 1
                        #
                        # conditioning_target.py 里的 _get_silence_latent_slice 本来就是为这个
                        # 问题加的(见它的 docstring: audio_duration 为 null 且生成的 code 数
                        # 超过存储的 silence latent 尺寸), 但当时只改了 target 那条路径,
                        # text 这条漏了。本次现场正是 task_type=text2music、duration=None,
                        # 同一个触发条件。
                        pad_chunk = self._get_silence_latent_slice(pad_length).unsqueeze(0)
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
            stack_items = [h if h is not None else silence_latent_tiled
                           for h in precomputed_lm_hints_25hz_list]
            # 上面的 padding 已经保证长度一致, 这里再兜一道: torch.stack 原生的报错
            # 只说 "entry 0 / entry 1" 和两个形状, 不说是哪一批、哪个 batch 位、
            # 期望多长 —— 这个 bug 上次就是因此只能靠猜(fp 71c68dad)。真出问题时
            # 直接说清楚, 而不是把诊断成本推给下一次排查。
            bad = [(i, tuple(t.shape)) for i, t in enumerate(stack_items)
                   if t.shape[0] != max_latent_length]
            if bad:
                raise RuntimeError(
                    "precomputed LM hints 长度与 max_latent_length(%d) 不一致: %s; "
                    "silence_latent 可用帧=%s, silence_latent_tiled=%s"
                    % (max_latent_length, bad,
                       getattr(self.silence_latent, "shape", None),
                       tuple(silence_latent_tiled.shape)))
            return torch.stack(stack_items)
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
        global_captions: Optional[List[str]] = None,
        chunk_mask_modes: Optional[List[str]] = None,
    ) -> Tuple[List[str], torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, Optional[torch.Tensor], Optional[torch.Tensor]]:
        """Tokenize caption/lyric prompts and optional non-cover branch prompts."""
        actual_captions, actual_languages = self._extract_caption_and_language(parsed_metas, captions, vocal_languages)

        # Detect is_lego_sft from the loaded model config (set on the SFT-stems checkpoint).
        is_lego_sft = (
            hasattr(self, "model")
            and self.model is not None
            and getattr(self.model.config, "is_lego_sft", False)
        )

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

            # SFT-stems lego: build the training-compatible caption block.
            #
            # Training format — full mode ("Generate the {TAG} track based on the audio context:"):
            #   "Global: {global_caption}\nLocal: {local_caption}\nMask Control: true"
            #   where global_caption = full song description, local_caption = per-stem description
            #
            # Training format — chunk mode ("Generate a segment of the {TAG} track..."):
            #   "Local: {local_caption}\nMask Control: true"    (no Global prefix)
            #
            # The caller passes:
            #   - captions[i]        → local/per-track description  (→ Local:)
            #   - global_captions[i] → global/full-song description (→ Global:)
            if is_lego_sft:
                local_cap = actual_caption
                global_cap = (global_captions[i] if global_captions and i < len(global_captions) else "") or ""
                instr_lower = instruction.lower()
                is_chunk_mode = "a segment" in instr_lower
                chunk_mode_i = (chunk_mask_modes[i] if chunk_mask_modes and i < len(chunk_mask_modes) else "auto")
                mask_control_str = "Mask Control: false" if chunk_mode_i == "auto" else "Mask Control: true"
                if is_chunk_mode:
                    actual_caption = f"Local: {local_cap}\n{mask_control_str}"
                else:
                    actual_caption = f"Global: {global_cap}\nLocal: {local_cap}\n{mask_control_str}"

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
