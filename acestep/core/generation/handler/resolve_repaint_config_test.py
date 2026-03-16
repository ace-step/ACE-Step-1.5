"""Tests for _resolve_repaint_config()."""

import unittest

from acestep.core.generation.handler.generate_music import _resolve_repaint_config


class TestResolveRepaintConfig(unittest.TestCase):
    """Verify mode/strength -> (injection_ratio, crossfade_frames, wav_crossfade).

    Strength semantics: 0.0 = conservative, 1.0 = aggressive.
    """

    def test_aggressive_returns_zeros(self):
        ratio, frames, wav = _resolve_repaint_config("aggressive", 0.5)
        self.assertEqual(ratio, 0.0)
        self.assertEqual(frames, 0)
        self.assertEqual(wav, 0.0)

    def test_conservative_returns_max(self):
        ratio, frames, wav = _resolve_repaint_config("conservative", 1.0)
        self.assertEqual(ratio, 1.0)
        self.assertEqual(frames, 25)
        self.assertAlmostEqual(wav, 0.05)

    def test_balanced_half(self):
        ratio, frames, wav = _resolve_repaint_config("balanced", 0.5)
        self.assertAlmostEqual(ratio, 0.5)
        self.assertEqual(frames, 12)
        self.assertAlmostEqual(wav, 0.025)

    def test_balanced_zero_equals_conservative(self):
        """strength=0 in balanced mode behaves like conservative."""
        ratio, frames, wav = _resolve_repaint_config("balanced", 0.0)
        self.assertEqual(ratio, 1.0)
        self.assertEqual(frames, 25)
        self.assertAlmostEqual(wav, 0.05)

    def test_balanced_one_equals_aggressive(self):
        """strength=1 in balanced mode behaves like aggressive."""
        ratio, frames, wav = _resolve_repaint_config("balanced", 1.0)
        self.assertEqual(ratio, 0.0)
        self.assertEqual(frames, 0)
        self.assertEqual(wav, 0.0)

    def test_strength_clamped_above_one(self):
        ratio, frames, wav = _resolve_repaint_config("balanced", 1.5)
        self.assertEqual(ratio, 0.0)

    def test_strength_clamped_below_zero(self):
        ratio, frames, wav = _resolve_repaint_config("balanced", -0.3)
        self.assertEqual(ratio, 1.0)

    def test_default_args(self):
        ratio, frames, wav = _resolve_repaint_config()
        self.assertAlmostEqual(ratio, 0.5)
        self.assertEqual(frames, 12)


if __name__ == "__main__":
    unittest.main()
