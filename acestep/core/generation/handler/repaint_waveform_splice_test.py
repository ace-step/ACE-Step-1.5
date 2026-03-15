"""Tests for repaint_waveform_splice module."""

import unittest

import torch

from acestep.core.generation.handler.repaint_waveform_splice import (
    _build_waveform_crossfade_mask,
    apply_repaint_waveform_splice,
)


class TestBuildWaveformCrossfadeMask(unittest.TestCase):
    """Tests for _build_waveform_crossfade_mask."""

    def test_mask_ones_inside_repaint_region(self):
        mask = _build_waveform_crossfade_mask(100, 20, 60, 0, torch.device("cpu"))
        self.assertTrue(torch.all(mask[20:60] == 1.0))
        self.assertTrue(torch.all(mask[:20] == 0.0))
        self.assertTrue(torch.all(mask[60:] == 0.0))

    def test_crossfade_ramp_at_left_boundary(self):
        mask = _build_waveform_crossfade_mask(200, 50, 150, 10, torch.device("cpu"))
        ramp = mask[40:50]
        self.assertEqual(ramp.shape[0], 10)
        self.assertTrue(torch.all(ramp > 0.0))
        self.assertTrue(torch.all(ramp < 1.0))
        diffs = ramp[1:] - ramp[:-1]
        self.assertTrue(torch.all(diffs > 0), "Left ramp must be monotonically increasing")

    def test_crossfade_ramp_at_right_boundary(self):
        mask = _build_waveform_crossfade_mask(200, 50, 150, 10, torch.device("cpu"))
        ramp = mask[150:160]
        self.assertEqual(ramp.shape[0], 10)
        self.assertTrue(torch.all(ramp > 0.0))
        self.assertTrue(torch.all(ramp < 1.0))
        diffs = ramp[1:] - ramp[:-1]
        self.assertTrue(torch.all(diffs < 0), "Right ramp must be monotonically decreasing")

    def test_crossfade_clamps_to_boundaries(self):
        mask = _build_waveform_crossfade_mask(100, 5, 95, 20, torch.device("cpu"))
        self.assertTrue(torch.all(mask >= 0.0))
        self.assertTrue(torch.all(mask <= 1.0))
        self.assertTrue(torch.all(mask[5:95] == 1.0))

    def test_zero_crossfade_is_hard_step(self):
        mask = _build_waveform_crossfade_mask(100, 30, 70, 0, torch.device("cpu"))
        self.assertTrue(torch.all(mask[:30] == 0.0))
        self.assertTrue(torch.all(mask[30:70] == 1.0))
        self.assertTrue(torch.all(mask[70:] == 0.0))


class TestApplyRepaintWaveformSplice(unittest.TestCase):
    """Tests for apply_repaint_waveform_splice."""

    def _make_tensors(self, B=1, C=2, samples=4800):
        pred = torch.ones(B, C, samples) * 2.0
        src = torch.ones(B, C, samples) * 5.0
        return pred, src

    def test_non_repaint_regions_match_src(self):
        pred, src = self._make_tensors(samples=9600)
        result = apply_repaint_waveform_splice(
            pred, src, [0.05], [0.15], sample_rate=48000, crossfade_duration=0.0,
        )
        start = int(0.05 * 48000)
        end = int(0.15 * 48000)
        torch.testing.assert_close(result[0, :, :start], src[0, :, :start])
        torch.testing.assert_close(result[0, :, end:], src[0, :, end:])

    def test_repaint_region_uses_pred(self):
        pred, src = self._make_tensors(samples=9600)
        result = apply_repaint_waveform_splice(
            pred, src, [0.05], [0.15], sample_rate=48000, crossfade_duration=0.0,
        )
        start = int(0.05 * 48000)
        end = int(0.15 * 48000)
        torch.testing.assert_close(result[0, :, start:end], pred[0, :, start:end])

    def test_crossfade_produces_intermediate_values(self):
        pred, src = self._make_tensors(samples=9600)
        result = apply_repaint_waveform_splice(
            pred, src, [0.05], [0.15], sample_rate=48000, crossfade_duration=0.005,
        )
        cf_samples = int(0.005 * 48000)
        start = int(0.05 * 48000)
        left_zone = result[0, 0, start - cf_samples:start]
        self.assertTrue(torch.all(left_zone > 2.0))
        self.assertTrue(torch.all(left_zone < 5.0))

    def test_full_repaint_returns_pred_unchanged(self):
        pred, src = self._make_tensors(samples=4800)
        result = apply_repaint_waveform_splice(
            pred, src, [0.0], [0.1], sample_rate=48000, crossfade_duration=0.01,
        )
        torch.testing.assert_close(result, pred)

    def test_length_mismatch_pred_longer(self):
        pred = torch.ones(1, 2, 5000) * 2.0
        src = torch.ones(1, 2, 4800) * 5.0
        result = apply_repaint_waveform_splice(
            pred, src, [0.02], [0.08], sample_rate=48000, crossfade_duration=0.0,
        )
        self.assertEqual(result.shape[-1], 5000)
        torch.testing.assert_close(result[..., 4800:], pred[..., 4800:])

    def test_length_mismatch_src_longer(self):
        pred = torch.ones(1, 2, 4800) * 2.0
        src = torch.ones(1, 2, 5000) * 5.0
        result = apply_repaint_waveform_splice(
            pred, src, [0.02], [0.08], sample_rate=48000, crossfade_duration=0.0,
        )
        self.assertEqual(result.shape[-1], 4800)

    def test_batch_independent_splice(self):
        pred = torch.ones(2, 2, 9600) * 2.0
        src = torch.ones(2, 2, 9600) * 5.0
        result = apply_repaint_waveform_splice(
            pred, src, [0.02, 0.05], [0.08, 0.15], sample_rate=48000,
            crossfade_duration=0.0,
        )
        s0, e0 = int(0.02 * 48000), int(0.08 * 48000)
        s1, e1 = int(0.05 * 48000), int(0.15 * 48000)
        torch.testing.assert_close(result[0, :, :s0], src[0, :, :s0])
        torch.testing.assert_close(result[0, :, s0:e0], pred[0, :, s0:e0])
        torch.testing.assert_close(result[1, :, :s1], src[1, :, :s1])
        torch.testing.assert_close(result[1, :, s1:e1], pred[1, :, s1:e1])

    def test_zero_crossfade_duration(self):
        pred, src = self._make_tensors(samples=9600)
        result = apply_repaint_waveform_splice(
            pred, src, [0.05], [0.15], sample_rate=48000, crossfade_duration=0.0,
        )
        start = int(0.05 * 48000)
        self.assertAlmostEqual(result[0, 0, start - 1].item(), 5.0)
        self.assertAlmostEqual(result[0, 0, start].item(), 2.0)


if __name__ == "__main__":
    unittest.main()
