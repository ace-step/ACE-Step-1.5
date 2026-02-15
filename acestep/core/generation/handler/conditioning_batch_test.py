"""Unit tests for batch-conditioning orchestration mixin."""

import unittest
from typing import Any, Dict, List, Optional, Tuple, Union

import torch

from acestep.core.generation.handler.conditioning_batch import ConditioningBatchMixin


class _Host(ConditioningBatchMixin):
    """Minimal host implementing ConditioningBatchMixin dependencies."""

    def __init__(self):
        self.device = "cpu"
        self.dtype = torch.float32
        self.sample_rate = 48000

    def _normalize_audio_code_hints(self, audio_code_hints, batch_size: int) -> List[Optional[str]]:
        if audio_code_hints is None:
            return [None] * batch_size
        return list(audio_code_hints)

    def _create_fallback_vocal_languages(self, batch_size: int) -> List[str]:
        return ["en"] * batch_size

    def _get_vae_dtype(self) -> torch.dtype:
        return torch.float32

    def _parse_metas(self, metas) -> List[str]:
        if metas is None:
            return ["- bpm: N/A\n- timesignature: N/A\n- keyscale: N/A\n- duration: 30 seconds\n"] * 2
        return metas

    def _normalize_instructions(self, instructions, batch_size: int, default: str) -> List[str]:
        if instructions is None:
            return [default] * batch_size
        return list(instructions)

    def _prepare_target_latents_and_wavs(
        self, batch_size: int, target_wavs: torch.Tensor, audio_code_hints: List[Optional[str]]
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, int, torch.Tensor]:
        target_latents = torch.zeros(batch_size, 128, 16, dtype=torch.float32)
        latent_masks = torch.ones(batch_size, 128, dtype=torch.long)
        silence_latent_tiled = torch.zeros(128, 16, dtype=torch.float32)
        return target_wavs, target_latents, latent_masks, 128, silence_latent_tiled

    def _build_chunk_masks_and_src_latents(
        self,
        batch_size: int,
        max_latent_length: int,
        instructions: List[str],
        audio_code_hints: List[Optional[str]],
        target_wavs: torch.Tensor,
        target_latents: torch.Tensor,
        repainting_start: Optional[List[float]],
        repainting_end: Optional[List[float]],
        silence_latent_tiled: torch.Tensor,
    ) -> Tuple[torch.Tensor, List[Tuple[str, int, int]], torch.Tensor, torch.Tensor]:
        chunk_masks = torch.ones(batch_size, max_latent_length, dtype=torch.bool)
        spans: List[Tuple[str, int, int]] = [("full", 0, max_latent_length)] * batch_size
        is_covers = torch.zeros(batch_size, dtype=torch.bool)
        src_latents = target_latents.clone()
        return chunk_masks, spans, is_covers, src_latents

    def _prepare_precomputed_lm_hints(
        self,
        batch_size: int,
        audio_code_hints: List[Optional[str]],
        max_latent_length: int,
        silence_latent_tiled: torch.Tensor,
    ) -> Optional[torch.Tensor]:
        if any(audio_code_hints):
            return torch.zeros(batch_size, max_latent_length, 16, dtype=torch.float32)
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
    ):
        text_inputs = [f"{captions[i]}::{lyrics[i]}" for i in range(batch_size)]
        text_ids = torch.ones(batch_size, 8, dtype=torch.long)
        text_mask = torch.ones(batch_size, 8, dtype=torch.long)
        lyric_ids = torch.ones(batch_size, 12, dtype=torch.long)
        lyric_mask = torch.ones(batch_size, 12, dtype=torch.long)
        non_cover_ids = torch.ones(batch_size, 8, dtype=torch.long) if audio_cover_strength < 1.0 else None
        non_cover_mask = torch.ones(batch_size, 8, dtype=torch.long) if audio_cover_strength < 1.0 else None
        return text_inputs, text_ids, text_mask, lyric_ids, lyric_mask, non_cover_ids, non_cover_mask


class ConditioningBatchMixinTests(unittest.TestCase):
    """Tests for ConditioningBatchMixin orchestration behavior."""

    def test_prepare_batch_builds_expected_keys_and_tensor_types(self):
        """Build batch with defaults and verify expected structure."""
        host = _Host()
        batch = host._prepare_batch(
            captions=["c1", "c2"],
            lyrics=["l1", "l2"],
            keys=["k1", "k2"],
            target_wavs=torch.zeros(2, 2, 96000),
            refer_audios=None,
            metas=None,
            vocal_languages=None,
            instructions=None,
            audio_code_hints=[None, None],
            audio_cover_strength=1.0,
        )

        self.assertIn("target_latents", batch)
        self.assertIn("chunk_masks", batch)
        self.assertIn("text_token_idss", batch)
        self.assertIn("refer_audioss", batch)
        self.assertEqual(batch["target_latents"].dtype, torch.float32)
        self.assertEqual(batch["target_latents"].shape, (2, 128, 16))
        self.assertEqual(len(batch["refer_audioss"]), 2)
        self.assertEqual(batch["refer_audioss"][0][0].shape, (2, 30 * host.sample_rate))

    def test_prepare_batch_populates_non_cover_inputs_when_strength_below_one(self):
        """Populate optional non-cover token fields for blended cover path."""
        host = _Host()
        batch = host._prepare_batch(
            captions=["c1", "c2"],
            lyrics=["l1", "l2"],
            keys=["k1", "k2"],
            target_wavs=torch.zeros(2, 2, 96000),
            refer_audios=[[torch.zeros(2, 96000)], [torch.zeros(2, 96000)]],
            metas=["m1", "m2"],
            vocal_languages=["en", "en"],
            instructions=["i1", "i2"],
            audio_code_hints=["hint", None],
            audio_cover_strength=0.5,
        )

        self.assertIsNotNone(batch["non_cover_text_input_ids"])
        self.assertIsNotNone(batch["non_cover_text_attention_masks"])
        self.assertIsNotNone(batch["precomputed_lm_hints_25Hz"])


if __name__ == "__main__":
    unittest.main()
