"""Schedule, CFG, packing, and noise unit tests for ``flow_edit_helpers``.

Velocity / momentum helpers live in
``flow_edit_helpers_velocity_test.py`` (split per the AGENTS.md
200 LOC module cap).
"""

import unittest

import torch

from acestep.models.common.apg_guidance import MomentumBuffer
from acestep.models.common.flow_edit_helpers import (
    apply_cfg_branch,
    build_timestep_schedule,
    draw_fwd_noise,
    pack_for_cfg,
)


class BuildTimestepScheduleTests(unittest.TestCase):
    """Pin schedule construction — must match the base-variant inline logic."""

    def test_linspace_default_no_shift(self):
        t = build_timestep_schedule(8, 1.0, None, torch.device("cpu"), torch.float32)
        self.assertEqual(t.shape, (9,))
        self.assertAlmostEqual(t[0].item(), 1.0)
        self.assertAlmostEqual(t[-1].item(), 0.0)
        diffs = (t[:-1] - t[1:]).tolist()
        self.assertTrue(all(abs(d - diffs[0]) < 1e-6 for d in diffs))

    def test_shift_transform_monotonic_decreasing(self):
        t = build_timestep_schedule(8, 3.0, None, torch.device("cpu"), torch.float32)
        for i in range(len(t) - 1):
            self.assertGreater(t[i].item(), t[i + 1].item() - 1e-6)
        self.assertAlmostEqual(t[0].item(), 1.0)
        self.assertAlmostEqual(t[-1].item(), 0.0)

    def test_user_timesteps_passed_through(self):
        custom = torch.tensor([1.0, 0.7, 0.3, 0.0])
        t = build_timestep_schedule(0, 1.0, custom, torch.device("cpu"), torch.float32)
        self.assertTrue(torch.allclose(t, custom))

    def test_user_timesteps_padded_to_zero(self):
        custom = torch.tensor([0.97, 0.5, 0.1])
        t = build_timestep_schedule(0, 1.0, custom, torch.device("cpu"), torch.float32)
        self.assertEqual(t.shape, (4,))
        self.assertAlmostEqual(t[-1].item(), 0.0)


class ApplyCfgBranchTests(unittest.TestCase):
    """Verify CFG dispatch matches the inline base-variant logic."""

    def setUp(self):
        torch.manual_seed(0)
        self.pred_cond = torch.randn(2, 4, 8)
        self.pred_null = torch.randn(2, 4, 8)
        self.pred_packed = torch.cat([self.pred_cond, self.pred_null], dim=0)

    def test_no_cfg_passes_through_unchanged(self):
        out = apply_cfg_branch(self.pred_cond, do_cfg=False, apply_cfg_now=True,
                               guidance_scale=7.0, momentum_buffer=MomentumBuffer())
        self.assertTrue(torch.equal(out, self.pred_cond))

    def test_cfg_outside_interval_returns_cond_chunk(self):
        out = apply_cfg_branch(self.pred_packed, do_cfg=True, apply_cfg_now=False,
                               guidance_scale=7.0, momentum_buffer=MomentumBuffer())
        self.assertTrue(torch.equal(out, self.pred_cond))

    def test_cfg_inside_interval_uses_apg(self):
        buf = MomentumBuffer()
        out = apply_cfg_branch(self.pred_packed, do_cfg=True, apply_cfg_now=True,
                               guidance_scale=7.0, momentum_buffer=buf)
        # APG amplifies the orthogonal component, so the result must differ
        # from a no-op pass-through of the cond chunk.
        self.assertFalse(torch.equal(out, self.pred_cond))


class DrawFwdNoiseTests(unittest.TestCase):
    """Generator-aware noise draw must respect both single and per-sample seeds."""

    SHAPE = (3, 4, 8)

    def test_no_generator_returns_random(self):
        a = draw_fwd_noise(self.SHAPE, None, torch.device("cpu"), torch.float32)
        b = draw_fwd_noise(self.SHAPE, None, torch.device("cpu"), torch.float32)
        self.assertEqual(a.shape, self.SHAPE)
        self.assertFalse(torch.equal(a, b))

    def test_single_generator_reproducible(self):
        g1 = torch.Generator().manual_seed(42)
        g2 = torch.Generator().manual_seed(42)
        a = draw_fwd_noise(self.SHAPE, g1, torch.device("cpu"), torch.float32)
        b = draw_fwd_noise(self.SHAPE, g2, torch.device("cpu"), torch.float32)
        self.assertTrue(torch.equal(a, b))

    def test_per_sample_generator_list(self):
        gens = [torch.Generator().manual_seed(i) for i in (1, 2, 3)]
        out = draw_fwd_noise(self.SHAPE, gens, torch.device("cpu"), torch.float32)
        self.assertEqual(out.shape, self.SHAPE)
        self.assertFalse(torch.equal(out[0], out[1]))
        self.assertFalse(torch.equal(out[1], out[2]))


class PackForCfgTests(unittest.TestCase):
    """CFG packing must double tensors and inject the null embedding."""

    def setUp(self):
        torch.manual_seed(0)
        self.enc_hs = torch.randn(2, 16, 32)
        self.enc_am = torch.ones(2, 16)
        self.ctx = torch.randn(2, 24, 64)
        self.attn = torch.ones(2, 24)
        self.null = torch.randn(1, 1, 32)

    def test_no_cfg_passes_through(self):
        out = pack_for_cfg(self.enc_hs, self.enc_am, self.ctx, self.attn, self.null, do_cfg=False)
        self.assertTrue(torch.equal(out[0], self.enc_hs))
        self.assertTrue(torch.equal(out[1], self.enc_am))
        self.assertTrue(torch.equal(out[2], self.ctx))
        self.assertTrue(torch.equal(out[3], self.attn))

    def test_cfg_doubles_batch_and_uses_null(self):
        out = pack_for_cfg(self.enc_hs, self.enc_am, self.ctx, self.attn, self.null, do_cfg=True)
        self.assertEqual(out[0].shape[0], 4)
        self.assertEqual(out[1].shape[0], 4)
        self.assertEqual(out[2].shape[0], 4)
        self.assertEqual(out[3].shape[0], 4)
        self.assertTrue(torch.equal(out[0][:2], self.enc_hs))
        self.assertTrue(torch.equal(out[0][2:], self.null.expand_as(self.enc_hs)))


if __name__ == "__main__":
    unittest.main()
