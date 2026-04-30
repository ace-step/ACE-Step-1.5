"""Pipeline-level tests for ``flow_edit_pipeline.flowedit_generate_audio``.

Covers the model-side glue: ``prepare_condition`` is invoked twice (once
for src, once for tar) and conditioning hints
(``precomputed_lm_hints_25Hz`` / ``audio_codes``) are forwarded to both.
"""

import unittest

import torch

from acestep.models.common.flow_edit_pipeline import flowedit_generate_audio
from acestep.models.common._flow_edit_test_support import StubModel


class _CapturingModel(StubModel):
    """Stub model whose ``prepare_condition`` records the kwargs it saw."""

    def __init__(self, channels: int = 16):
        super().__init__(channels=channels)
        self.captured_calls = []

    def prepare_condition(self, **kwargs):
        self.captured_calls.append(kwargs)
        bsz = kwargs["src_latents"].shape[0]
        seq = kwargs["src_latents"].shape[1]
        return (
            torch.randn(bsz, 4, self.channels),
            torch.ones(bsz, 4),
            torch.randn(bsz, seq, self.channels * 2),
        )


class FlowEditPipelineConditionForwardingTests(unittest.TestCase):

    def test_lm_hints_and_audio_codes_forwarded_to_both_calls(self):
        """Regression for codex P2 round-1 finding: hints must reach prepare_condition.

        Pre-fix the pipeline ate ``precomputed_lm_hints_25Hz`` and
        ``audio_codes`` via ``**kwargs``, so both calls fell back to
        tokenising ``src_latents``.  This breaks cover/edit flows that
        rely on those hints.
        """
        model = _CapturingModel()
        bsz, seq, ch = 1, 8, model.channels
        src = torch.randn(bsz, seq, ch)
        text_hs = torch.randn(bsz, 4, ch)
        text_am = torch.ones(bsz, 4)
        lyric_hs = torch.randn(bsz, 4, ch)
        lyric_am = torch.ones(bsz, 4)
        refer = torch.zeros(0, 4, ch)
        refer_om = torch.zeros(0, dtype=torch.long)
        chunk_masks = torch.ones(bsz, seq, ch)
        is_covers = torch.zeros(bsz, dtype=torch.long)
        silence = torch.zeros(bsz, seq, ch)

        sentinel_hints = torch.full((bsz, seq, ch), 0.42)
        sentinel_codes = torch.tensor([[1, 2, 3]])

        flowedit_generate_audio(
            model,
            text_hidden_states=text_hs, text_attention_mask=text_am,
            lyric_hidden_states=lyric_hs, lyric_attention_mask=lyric_am,
            refer_audio_acoustic_hidden_states_packed=refer,
            refer_audio_order_mask=refer_om,
            src_latents=src, chunk_masks=chunk_masks,
            is_covers=is_covers, silence_latent=silence,
            target_text_hidden_states=text_hs,
            target_text_attention_mask=text_am,
            target_lyric_hidden_states=lyric_hs,
            target_lyric_attention_mask=lyric_am,
            infer_steps=2,
            diffusion_guidance_scale=1.0,
            edit_n_min=0.0, edit_n_max=1.0, edit_n_avg=1,
            use_progress_bar=False,
            precomputed_lm_hints_25Hz=sentinel_hints,
            audio_codes=sentinel_codes,
        )

        self.assertEqual(len(model.captured_calls), 2)
        for call in model.captured_calls:
            self.assertIs(call["precomputed_lm_hints_25Hz"], sentinel_hints)
            self.assertIs(call["audio_codes"], sentinel_codes)


if __name__ == "__main__":
    unittest.main()
