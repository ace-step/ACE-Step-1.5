"""Loop-contract tests for ``flowedit_sampling_loop`` (#1156).

Uses the deterministic stub decoder in ``_flow_edit_test_support``;
pipeline-level forwarding tests live in ``flow_edit_pipeline_test.py``.
Real-audio smoke test runs separately on a GPU machine.
"""

import unittest

import torch

from acestep.models.common.flow_edit import flowedit_sampling_loop

from acestep.models.common._flow_edit_test_support import StubModel, make_inputs


class FlowEditSamplingLoopContractTests(unittest.TestCase):

    def test_n_max_zero_only_post_window(self):
        """``n_max=0`` skips the edit branch and Euler-steps from xt_src."""
        model = StubModel()
        src, enc_hs_a, enc_am_a, ctx_a, attn = make_inputs()
        _, enc_hs_b, enc_am_b, ctx_b, _ = make_inputs()
        out = flowedit_sampling_loop(
            model,
            src_encoder_hidden_states=enc_hs_a, src_encoder_attention_mask=enc_am_a,
            src_context_latents=ctx_a,
            tar_encoder_hidden_states=enc_hs_b, tar_encoder_attention_mask=enc_am_b,
            tar_context_latents=ctx_b,
            src_latents=src, attention_mask=attn,
            null_condition_emb=model.null_condition_emb,
            retake_generators=torch.Generator().manual_seed(7),
            infer_steps=4,
            diffusion_guidance_scale=1.0,
            n_min=0.0, n_max=0.0, n_avg=1,
            use_progress_bar=False,
        )
        self.assertFalse(torch.equal(out["target_latents"], src))

    def test_n_min_equals_n_max_equals_one_returns_src(self):
        """``n_min=n_max=1`` skips both branches → output equals source."""
        model = StubModel()
        src, enc_hs_a, enc_am_a, ctx_a, attn = make_inputs()
        _, enc_hs_b, enc_am_b, ctx_b, _ = make_inputs()
        out = flowedit_sampling_loop(
            model,
            src_encoder_hidden_states=enc_hs_a, src_encoder_attention_mask=enc_am_a,
            src_context_latents=ctx_a,
            tar_encoder_hidden_states=enc_hs_b, tar_encoder_attention_mask=enc_am_b,
            tar_context_latents=ctx_b,
            src_latents=src, attention_mask=attn,
            null_condition_emb=model.null_condition_emb,
            retake_generators=torch.Generator().manual_seed(7),
            infer_steps=4,
            diffusion_guidance_scale=1.0,
            n_min=1.0, n_max=1.0, n_avg=1,
            use_progress_bar=False,
        )
        self.assertTrue(torch.equal(out["target_latents"], src))

    def test_determinism_same_seed_same_output(self):
        """Bit-equal outputs given identical seeds."""
        model = StubModel()
        src, enc_hs_a, enc_am_a, ctx_a, attn = make_inputs()
        _, enc_hs_b, enc_am_b, ctx_b, _ = make_inputs()

        def _run():
            return flowedit_sampling_loop(
                model,
                src_encoder_hidden_states=enc_hs_a, src_encoder_attention_mask=enc_am_a,
                src_context_latents=ctx_a,
                tar_encoder_hidden_states=enc_hs_b, tar_encoder_attention_mask=enc_am_b,
                tar_context_latents=ctx_b,
                src_latents=src, attention_mask=attn,
                null_condition_emb=model.null_condition_emb,
                retake_generators=torch.Generator().manual_seed(13),
                infer_steps=4,
                diffusion_guidance_scale=1.0,
                n_min=0.2, n_max=0.8, n_avg=2,
                use_progress_bar=False,
            )["target_latents"]

        a = _run()
        b = _run()
        self.assertTrue(torch.equal(a, b))

    def test_invalid_n_avg_raises(self):
        model = StubModel()
        src, enc_hs_a, enc_am_a, ctx_a, attn = make_inputs()
        with self.assertRaises(ValueError):
            flowedit_sampling_loop(
                model,
                src_encoder_hidden_states=enc_hs_a, src_encoder_attention_mask=enc_am_a,
                src_context_latents=ctx_a,
                tar_encoder_hidden_states=enc_hs_a, tar_encoder_attention_mask=enc_am_a,
                tar_context_latents=ctx_a,
                src_latents=src, attention_mask=attn,
                null_condition_emb=model.null_condition_emb,
                infer_steps=4, n_avg=0, use_progress_bar=False,
                diffusion_guidance_scale=1.0,
            )

    def test_invalid_window_raises(self):
        model = StubModel()
        src, enc_hs_a, enc_am_a, ctx_a, attn = make_inputs()
        with self.assertRaises(ValueError):
            flowedit_sampling_loop(
                model,
                src_encoder_hidden_states=enc_hs_a, src_encoder_attention_mask=enc_am_a,
                src_context_latents=ctx_a,
                tar_encoder_hidden_states=enc_hs_a, tar_encoder_attention_mask=enc_am_a,
                tar_context_latents=ctx_a,
                src_latents=src, attention_mask=attn,
                null_condition_emb=model.null_condition_emb,
                infer_steps=4, n_min=0.7, n_max=0.3, use_progress_bar=False,
                diffusion_guidance_scale=1.0,
            )

    def test_apg_momentum_does_not_advance_per_draw(self):
        """Regression for codex P2 round-2 finding.

        Pre-fix the inner ``n_avg`` loop called ``apg_forward`` n_avg
        times per step, advancing APG's running average n_avg times per
        scheduler step.  Post-fix the buffer is snapshot-and-restored
        around each draw, then advanced once with the averaged diff
        outside the loop.  We exercise CFG (``guidance_scale > 1``) so
        APG actually runs and assert the n_avg=4 output stays in the
        same magnitude ballpark as n_avg=1.
        """
        model = StubModel()
        src, enc_hs_a, enc_am_a, ctx_a, attn = make_inputs()
        _, enc_hs_b, enc_am_b, ctx_b, _ = make_inputs()

        def _run(n_avg):
            return flowedit_sampling_loop(
                model,
                src_encoder_hidden_states=enc_hs_a, src_encoder_attention_mask=enc_am_a,
                src_context_latents=ctx_a,
                tar_encoder_hidden_states=enc_hs_b, tar_encoder_attention_mask=enc_am_b,
                tar_context_latents=ctx_b,
                src_latents=src, attention_mask=attn,
                null_condition_emb=model.null_condition_emb,
                retake_generators=torch.Generator().manual_seed(7),
                infer_steps=2,
                diffusion_guidance_scale=2.0,
                n_min=0.0, n_max=0.5, n_avg=n_avg,
                use_progress_bar=False,
            )["target_latents"]

        a1, a4 = _run(1), _run(4)
        self.assertFalse(torch.isnan(a1).any())
        self.assertFalse(torch.isnan(a4).any())
        ratio = a4.abs().max().item() / max(a1.abs().max().item(), 1e-6)
        self.assertLess(ratio, 5.0,
            f"n_avg=4 output is {ratio:.2f}× n_avg=1 — APG momentum likely "
            "advancing per draw instead of per step.")

    def test_ema_does_not_leak_inside_inner_loop(self):
        """Regression for codex P2 round-1 finding.

        Bit-equal outputs across runs with identical seeds, non-zero EMA,
        and ``n_avg=4``.  Pre-fix this would have been flaky since
        ``prev_vt_*`` mutated mid-loop made the result depend on draw
        order.
        """
        model = StubModel()
        src, enc_hs_a, enc_am_a, ctx_a, attn = make_inputs()
        _, enc_hs_b, enc_am_b, ctx_b, _ = make_inputs()

        def _run():
            return flowedit_sampling_loop(
                model,
                src_encoder_hidden_states=enc_hs_a, src_encoder_attention_mask=enc_am_a,
                src_context_latents=ctx_a,
                tar_encoder_hidden_states=enc_hs_b, tar_encoder_attention_mask=enc_am_b,
                tar_context_latents=ctx_b,
                src_latents=src, attention_mask=attn,
                null_condition_emb=model.null_condition_emb,
                retake_generators=torch.Generator().manual_seed(99),
                infer_steps=4,
                diffusion_guidance_scale=1.0,
                velocity_ema_factor=0.3,
                n_min=0.0, n_max=1.0, n_avg=4,
                use_progress_bar=False,
            )["target_latents"]

        self.assertTrue(torch.equal(_run(), _run()))


if __name__ == "__main__":
    unittest.main()
