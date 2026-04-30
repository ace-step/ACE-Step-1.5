"""Velocity-clamp / EMA / APG-momentum unit tests for ``flow_edit_helpers``.

Schedule / CFG / packing / noise tests live in
``flow_edit_helpers_test.py`` (split per the AGENTS.md 200 LOC cap).
"""

import unittest

import torch

from acestep.models.common.apg_guidance import MomentumBuffer
from acestep.models.common.flow_edit_helpers import (
    apply_velocity_clamp,
    apply_velocity_ema,
    restore_and_advance_momentum,
    snapshot_momentum,
)


class ApplyVelocityClampTests(unittest.TestCase):
    """Velocity-norm clamp must be a no-op when threshold is 0."""

    def test_threshold_zero_is_noop(self):
        torch.manual_seed(0)
        vt = torch.randn(2, 4, 8)
        xt = torch.randn(2, 4, 8)
        self.assertTrue(torch.equal(apply_velocity_clamp(vt, xt, 0.0), vt))

    def test_clamp_reduces_outlier_norms(self):
        vt = torch.full((1, 4, 8), 100.0)
        xt = torch.full((1, 4, 8), 1.0)
        out = apply_velocity_clamp(vt, xt, 2.0)
        out_norm = torch.norm(out, dim=(1, 2)).item()
        xt_norm = torch.norm(xt, dim=(1, 2)).item()
        self.assertAlmostEqual(out_norm, 2.0 * xt_norm, places=2)


class ApplyVelocityEmaTests(unittest.TestCase):
    """EMA smoothing: per-timestep blend, not per-MC-draw (regression for codex P2)."""

    def test_ema_no_prev_returns_vt(self):
        vt = torch.randn(1, 4, 8)
        self.assertTrue(torch.equal(apply_velocity_ema(vt, None, 0.5), vt))

    def test_ema_zero_factor_returns_vt(self):
        vt = torch.randn(1, 4, 8)
        prev = torch.randn(1, 4, 8)
        self.assertTrue(torch.equal(apply_velocity_ema(vt, prev, 0.0), vt))

    def test_ema_with_prev_blends(self):
        vt = torch.ones(1, 4, 8)
        prev = torch.zeros(1, 4, 8)
        out = apply_velocity_ema(vt, prev, 0.3)
        # 0.7*1 + 0.3*0 = 0.7
        self.assertTrue(torch.allclose(out, torch.full_like(vt, 0.7)))


class MomentumSnapshotTests(unittest.TestCase):
    """Snapshot/restore must isolate APG momentum across MC draws."""

    def test_snapshot_then_advance_matches_single_update(self):
        """One pre-step snapshot + one final update == one direct update."""
        buf_a, buf_b = MomentumBuffer(), MomentumBuffer()
        buf_a.update(torch.tensor([1.0, 2.0]))
        snap_a, snap_b = snapshot_momentum(buf_a, buf_b)
        # Simulate inner loop "polluting" buf_a with a diff that should NOT
        # carry forward — we restore-and-advance with avg_diff outside.
        buf_a.update(torch.tensor([99.0, 99.0]))
        ref = MomentumBuffer()
        ref.update(torch.tensor([1.0, 2.0]))
        ref.update(torch.tensor([3.0, 4.0]))
        restore_and_advance_momentum(
            buf_a, buf_b, snap_a, snap_b,
            avg_diff_src=torch.tensor([3.0, 4.0]),
            avg_diff_tar=torch.tensor([5.0, 6.0]),
        )
        self.assertTrue(torch.equal(buf_a.running_average, ref.running_average))

    def test_no_cfg_diff_just_rolls_back(self):
        """When CFG is inactive (avg_diff is None) the buffer rolls back."""
        buf_a, buf_b = MomentumBuffer(), MomentumBuffer()
        buf_a.update(torch.tensor([1.0]))
        snap_a, snap_b = snapshot_momentum(buf_a, buf_b)
        buf_a.update(torch.tensor([42.0]))
        restore_and_advance_momentum(buf_a, buf_b, snap_a, snap_b, None, None)
        self.assertTrue(torch.equal(buf_a.running_average, snap_a))


if __name__ == "__main__":
    unittest.main()
