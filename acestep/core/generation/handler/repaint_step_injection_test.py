"""Unit tests for repaint step injection and boundary blending."""

import unittest

import torch

from acestep.core.generation.handler.repaint_step_injection import (
    apply_repaint_boundary_blend,
    apply_repaint_step_injection,
    build_soft_repaint_mask,
)


class TestApplyRepaintStepInjection(unittest.TestCase):
    """Tests for per-step source latent replacement in non-repaint regions."""

    def setUp(self):
        self.B, self.T, self.C = 2, 100, 64
        self.xt = torch.randn(self.B, self.T, self.C)
        self.clean_src = torch.randn(self.B, self.T, self.C)
        self.noise = torch.randn(self.B, self.T, self.C)
        self.mask = torch.ones(self.B, self.T, dtype=torch.bool)
        self.mask[0, :20] = False
        self.mask[0, 40:] = False
        self.mask[1, :10] = False
        self.mask[1, 60:] = False

    def test_non_repaint_regions_match_noised_source(self):
        t_next = 0.5
        result = apply_repaint_step_injection(
            self.xt, self.clean_src, self.mask, t_next, self.noise,
        )
        expected = t_next * self.noise + (1.0 - t_next) * self.clean_src
        torch.testing.assert_close(result[0, :20], expected[0, :20])
        torch.testing.assert_close(result[0, 40:], expected[0, 40:])

    def test_repaint_regions_unchanged(self):
        result = apply_repaint_step_injection(
            self.xt, self.clean_src, self.mask, 0.3, self.noise,
        )
        torch.testing.assert_close(result[0, 20:40], self.xt[0, 20:40])
        torch.testing.assert_close(result[1, 10:60], self.xt[1, 10:60])

    def test_all_true_mask_is_noop(self):
        full_mask = torch.ones(self.B, self.T, dtype=torch.bool)
        result = apply_repaint_step_injection(
            self.xt, self.clean_src, full_mask, 0.5, self.noise,
        )
        torch.testing.assert_close(result, self.xt)

    def test_t_zero_returns_clean_source_in_preserved(self):
        result = apply_repaint_step_injection(
            self.xt, self.clean_src, self.mask, 0.0, self.noise,
        )
        torch.testing.assert_close(result[0, :20], self.clean_src[0, :20])

    def test_t_one_returns_pure_noise_in_preserved(self):
        result = apply_repaint_step_injection(
            self.xt, self.clean_src, self.mask, 1.0, self.noise,
        )
        torch.testing.assert_close(result[0, :20], self.noise[0, :20])


class TestBuildSoftRepaintMask(unittest.TestCase):
    """Tests for soft crossfade mask construction."""

    def test_core_region_is_one(self):
        mask = torch.zeros(1, 100, dtype=torch.bool)
        mask[0, 20:40] = True
        soft = build_soft_repaint_mask(mask, crossfade_frames=5)
        self.assertTrue((soft[0, 20:40] == 1.0).all())

    def test_far_preserved_is_zero(self):
        mask = torch.zeros(1, 100, dtype=torch.bool)
        mask[0, 20:40] = True
        soft = build_soft_repaint_mask(mask, crossfade_frames=5)
        self.assertTrue((soft[0, :15] == 0.0).all())
        self.assertTrue((soft[0, 45:] == 0.0).all())

    def test_crossfade_zone_is_monotonic(self):
        mask = torch.zeros(1, 100, dtype=torch.bool)
        mask[0, 20:60] = True
        soft = build_soft_repaint_mask(mask, crossfade_frames=8)
        left_ramp = soft[0, 12:20]
        for i in range(len(left_ramp) - 1):
            self.assertLess(left_ramp[i].item(), left_ramp[i + 1].item())
        right_ramp = soft[0, 60:68]
        for i in range(len(right_ramp) - 1):
            self.assertGreater(right_ramp[i].item(), right_ramp[i + 1].item())

    def test_all_true_mask_returns_ones(self):
        mask = torch.ones(2, 50, dtype=torch.bool)
        soft = build_soft_repaint_mask(mask, crossfade_frames=10)
        self.assertTrue((soft == 1.0).all())

    def test_all_false_mask_returns_zeros(self):
        mask = torch.zeros(2, 50, dtype=torch.bool)
        soft = build_soft_repaint_mask(mask, crossfade_frames=10)
        self.assertTrue((soft == 0.0).all())

    def test_zero_crossfade_is_hard_mask(self):
        mask = torch.zeros(1, 100, dtype=torch.bool)
        mask[0, 30:70] = True
        soft = build_soft_repaint_mask(mask, crossfade_frames=0)
        torch.testing.assert_close(soft, mask.float())

    def test_crossfade_clamped_at_boundaries(self):
        mask = torch.zeros(1, 50, dtype=torch.bool)
        mask[0, 2:48] = True
        soft = build_soft_repaint_mask(mask, crossfade_frames=10)
        self.assertTrue((soft[0] >= 0.0).all())
        self.assertTrue((soft[0] <= 1.0).all())
        self.assertTrue((soft[0, :2] < 1.0).all())


class TestApplyRepaintBoundaryBlend(unittest.TestCase):
    """Tests for post-loop boundary blending."""

    def test_preserved_region_uses_source(self):
        B, T, C = 1, 100, 16
        x_gen = torch.ones(B, T, C)
        clean = torch.zeros(B, T, C)
        mask = torch.zeros(B, T, dtype=torch.bool)
        mask[0, 30:60] = True
        result = apply_repaint_boundary_blend(x_gen, clean, mask, crossfade_frames=5)
        torch.testing.assert_close(result[0, :25], clean[0, :25])
        torch.testing.assert_close(result[0, 65:], clean[0, 65:])

    def test_core_repaint_uses_generated(self):
        B, T, C = 1, 100, 16
        x_gen = torch.ones(B, T, C) * 2.0
        clean = torch.zeros(B, T, C)
        mask = torch.zeros(B, T, dtype=torch.bool)
        mask[0, 30:60] = True
        result = apply_repaint_boundary_blend(x_gen, clean, mask, crossfade_frames=5)
        torch.testing.assert_close(result[0, 30:60], x_gen[0, 30:60])

    def test_full_repaint_mask_returns_generated(self):
        B, T, C = 2, 50, 8
        x_gen = torch.randn(B, T, C)
        clean = torch.randn(B, T, C)
        mask = torch.ones(B, T, dtype=torch.bool)
        result = apply_repaint_boundary_blend(x_gen, clean, mask, crossfade_frames=10)
        torch.testing.assert_close(result, x_gen)

    def test_blending_zone_is_interpolated(self):
        B, T, C = 1, 100, 4
        x_gen = torch.ones(B, T, C)
        clean = torch.zeros(B, T, C)
        mask = torch.zeros(B, T, dtype=torch.bool)
        mask[0, 20:80] = True
        result = apply_repaint_boundary_blend(x_gen, clean, mask, crossfade_frames=5)
        blend_zone = result[0, 15:20, 0]
        for i in range(len(blend_zone)):
            val = blend_zone[i].item()
            self.assertGreater(val, 0.0)
            self.assertLess(val, 1.0)


if __name__ == "__main__":
    unittest.main()
