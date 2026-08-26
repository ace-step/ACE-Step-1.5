"""Prompt and text-input helpers for handler decomposition."""

import re
from typing import Any, Dict, List, Optional, Tuple, Union

import torch
from loguru import logger

from acestep.constants import DEFAULT_DIT_INSTRUCTION, LYRIC_GEN_PROMPT, SFT_GEN_PROMPT


class PromptMixin:
    """Mixin containing prompt formatting and text-encoder helpers.

    Depends on host members:
    - Attributes: ``text_tokenizer``, ``text_encoder``, ``device``, ``dtype``.
    - Methods: ``_parse_metas`` (from ``MetadataMixin``), ``_load_model_context``
      (from ``InitServiceMixin``).
    """

    def _format_instruction(self, instruction: str) -> str:
        """Ensure instruction ends with a colon."""
        if not instruction.endswith(":"):
            instruction = instruction + ":"
        return instruction

    def _format_lyrics(self, lyrics: str, language: str) -> str:
        """Format lyrics text with language header."""
        return LYRIC_GEN_PROMPT.format(language, lyrics)

    def _pad_sequences(
        self, sequences: List[torch.Tensor], max_length: int, pad_value: int = 0
    ) -> torch.Tensor:
        """Pad sequence tensors to the same length."""
        return torch.stack(
            [
                torch.nn.functional.pad(seq, (0, max_length - len(seq)), "constant", pad_value)
                for seq in sequences
            ]
        )

    def extract_caption_from_sft_format(self, caption: str) -> str:
        """Extract caption body from SFT-formatted prompt when present."""
        try:
            if "# Instruction" in caption and "# Caption" in caption:
                pattern = r"#\s*Caption\s*\n(.*?)(?:\n\s*#\s*Metas|$)"
                match = re.search(pattern, caption, re.DOTALL)
                if match:
                    return match.group(1).strip()
            return caption
        except (AttributeError, TypeError, re.error):
            logger.exception("[extract_caption_from_sft_format] Error extracting caption")
            return caption

    def build_dit_inputs(
        self,
        task: str,
        instruction: Optional[str],
        caption: str,
        lyrics: str,
        metas: Optional[Union[str, Dict[str, Any]]] = None,
        vocal_language: str = "en",
    ) -> Tuple[str, str]:
        """Build caption and lyric input text for DiT branches.

        Args:
            task: Task name (currently informational; reserved for task-specific formatting).
            instruction: Instruction text; falls back to default when empty.
            caption: Caption fallback value.
            lyrics: Raw lyric text.
            metas: Optional metadata (string or dict) that may include caption/language.
            vocal_language: Fallback lyric language when not present in metadata.

        Returns:
            Tuple of ``(caption_input, lyrics_input)`` for caption and lyric encoder branches.
        """
        final_instruction = self._format_instruction(instruction or DEFAULT_DIT_INSTRUCTION)
        actual_caption = caption
        actual_language = vocal_language

        if metas is not None:
            try:
                if isinstance(metas, str):
                    parsed_metas = self._parse_metas([metas])
                    meta_dict = parsed_metas[0] if parsed_metas and isinstance(parsed_metas[0], dict) else {}
                elif isinstance(metas, dict):
                    meta_dict = metas
                else:
                    meta_dict = {}
            except (TypeError, ValueError, KeyError, IndexError):
                logger.exception("[build_dit_inputs] Error parsing metas")
                meta_dict = {}
            if "caption" in meta_dict and meta_dict["caption"]:
                actual_caption = str(meta_dict["caption"])
            if "language" in meta_dict and meta_dict["language"]:
                actual_language = str(meta_dict["language"])

        parsed_meta = self._parse_metas([metas])[0]
        caption_input = SFT_GEN_PROMPT.format(final_instruction, actual_caption, parsed_meta)
        lyrics_input = self._format_lyrics(lyrics, actual_language)
        return caption_input, lyrics_input

    def _get_text_hidden_states(self, text_prompt: str) -> Tuple[torch.Tensor, torch.Tensor]:
        """Get hidden states and attention mask from text encoder."""
        if self.text_tokenizer is None or self.text_encoder is None:
            raise ValueError("Text encoder not initialized")

        try:
            with self._load_model_context("text_encoder"):
                text_inputs = self.text_tokenizer(
                    text_prompt,
                    padding="longest",
                    truncation=True,
                    max_length=256,
                    return_tensors="pt",
                )
                text_input_ids = text_inputs.input_ids.to(self.device)
                text_attention_mask = text_inputs.attention_mask.to(self.device).bool()

                with torch.inference_mode():
                    text_outputs = self.text_encoder(text_input_ids)
                    if hasattr(text_outputs, "last_hidden_state"):
                        text_hidden_states = text_outputs.last_hidden_state
                    elif isinstance(text_outputs, tuple):
                        text_hidden_states = text_outputs[0]
                    else:
                        text_hidden_states = text_outputs

                text_hidden_states = text_hidden_states.to(self.dtype)
                return text_hidden_states, text_attention_mask
        except (AttributeError, RuntimeError, TypeError, ValueError):
            logger.exception("[_get_text_hidden_states] Failed to encode text prompt")
            raise

    def _extract_caption_and_language(
        self,
        metas: List[Union[str, Dict[str, Any]]],
        captions: List[str],
        vocal_languages: List[str],
    ) -> Tuple[List[str], List[str]]:
        """Extract caption/language values from metas with fallback values."""
        actual_captions = list(captions)
        actual_languages = list(vocal_languages)

        for i, meta in enumerate(metas):
            if i >= len(actual_captions):
                break

            meta_dict = None
            if isinstance(meta, str):
                parsed = self._parse_metas([meta])
                if parsed and isinstance(parsed[0], dict):
                    meta_dict = parsed[0]
            elif isinstance(meta, dict):
                meta_dict = meta

            if meta_dict:
                if "caption" in meta_dict and meta_dict["caption"]:
                    actual_captions[i] = str(meta_dict["caption"])
                if "language" in meta_dict and meta_dict["language"]:
                    actual_languages[i] = str(meta_dict["language"])
        return actual_captions, actual_languages
