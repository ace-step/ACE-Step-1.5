"""Unit tests for APG guidance primitives (``MomentumBuffer`` and ``apg_forward``)."""

import unittest

import torch

from acestep.models.common.apg_guidance import MomentumBuffer, apg_forward


class MomentumBufferDefaultsTests(unittest.TestCase):
    """Tests that MomentumBuffer preserves its historical default behavior."""

    def test_default_momentum_matches_hardcoded_recipe_value(self):
        """Default constructor should produce momentum=-0.75 (the ACE-Step default)."""

        buffer = MomentumBuffer()
        self.assertAlmostEqual(-0.75, buffer.momentum)

    def test_explicit_momentum_is_honored(self):
        """Caller-supplied momentum value must replace the default."""

        buffer = MomentumBuffer(momentum=0.25)
        self.assertAlmostEqual(0.25, buffer.momentum)

    def test_update_uses_momentum_scale_on_running_average(self):
        """Running average must be updated as ``momentum * prev + new``."""

        buffer = MomentumBuffer(momentum=0.5)
        buffer.update(torch.tensor([1.0, 2.0]))
        buffer.update(torch.tensor([3.0, 4.0]))
        expected = torch.tensor([0.5, 1.0]) + torch.tensor([3.0, 4.0])
        self.assertTrue(torch.allclose(buffer.running_average, expected))


class ApgForwardDefaultsTests(unittest.TestCase):
    """Tests that ``apg_forward`` preserves its default eta/norm_threshold semantics."""

    def _make_inputs(self):
        """Return reproducible conditional/unconditional prediction tensors."""

        torch.manual_seed(0)
        pred_cond = torch.randn(2, 4, 8)
        pred_uncond = torch.randn(2, 4, 8)
        return pred_cond, pred_uncond

    def test_default_eta_produces_same_output_as_explicit_zero(self):
        """Omitting eta must match eta=0.0 exactly (backward compatibility)."""

        pred_cond, pred_uncond = self._make_inputs()
        implicit = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=3.0,
            momentum_buffer=None,
            dims=[1],
        )
        explicit = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=3.0,
            momentum_buffer=None,
            eta=0.0,
            dims=[1],
        )
        self.assertTrue(torch.allclose(implicit, explicit))

    def test_nonzero_eta_changes_output(self):
        """A nonzero eta must change the guided prediction (sanity check)."""

        pred_cond, pred_uncond = self._make_inputs()
        baseline = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=3.0,
            momentum_buffer=None,
            eta=0.0,
            dims=[1],
        )
        tweaked = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=3.0,
            momentum_buffer=None,
            eta=1.0,
            dims=[1],
        )
        self.assertFalse(torch.allclose(baseline, tweaked))

    def test_default_momentum_buffer_matches_explicit_neg_075(self):
        """Default MomentumBuffer() must produce the same trajectory as momentum=-0.75."""

        pred_cond, pred_uncond = self._make_inputs()
        implicit_out = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=3.0,
            momentum_buffer=MomentumBuffer(),
            dims=[1],
        )
        explicit_out = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=3.0,
            momentum_buffer=MomentumBuffer(momentum=-0.75),
            dims=[1],
        )
        self.assertTrue(torch.allclose(implicit_out, explicit_out))


if __name__ == "__main__":
    unittest.main()
