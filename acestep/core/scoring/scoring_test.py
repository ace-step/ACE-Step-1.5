"""Unit tests for DTW utilities and LM score pure functions."""

import math
import unittest

import numpy as np
import torch

from acestep.core.scoring._dtw import dtw_cpu, median_filter
from acestep.core.scoring.lm_score import (
    pmi_score,
    pmi_to_normalized_score,
    calculate_reward_score,
)


class DtwCpuTests(unittest.TestCase):
    """Tests for the Numba-optimized DTW implementation."""

    def test_identity_cost_matrix(self):
        """DTW on a diagonal-zero cost matrix should follow the diagonal."""
        n = 4
        cost = np.ones((n, n), dtype=np.float64)
        np.fill_diagonal(cost, 0.0)
        text_idx, time_idx = dtw_cpu(-cost)
        # Path should be monotonically non-decreasing
        self.assertTrue(np.all(np.diff(text_idx) >= 0))
        self.assertTrue(np.all(np.diff(time_idx) >= 0))

    def test_single_element(self):
        """DTW on a 1x1 matrix should return a single-step path."""
        cost = np.array([[0.5]], dtype=np.float64)
        text_idx, time_idx = dtw_cpu(-cost)
        self.assertEqual(text_idx.tolist(), [0])
        self.assertEqual(time_idx.tolist(), [0])

    def test_rectangular_matrix(self):
        """DTW should handle non-square matrices."""
        cost = np.zeros((2, 5), dtype=np.float64)
        text_idx, time_idx = dtw_cpu(-cost)
        # Path must cover both rows and all columns
        self.assertIn(0, text_idx)
        self.assertIn(1, text_idx)
        self.assertEqual(time_idx[-1], 4)


class MedianFilterTests(unittest.TestCase):
    """Tests for the median filter utility."""

    def test_identity_with_width_one(self):
        """Filter width 1 should return the input unchanged."""
        x = torch.tensor([[1.0, 2.0, 3.0, 4.0, 5.0]])
        result = median_filter(x, filter_width=1)
        torch.testing.assert_close(result, x)

    def test_smoothing_effect(self):
        """Filter width > 1 should smooth spike values."""
        x = torch.tensor([[0.0, 0.0, 10.0, 0.0, 0.0]])
        result = median_filter(x, filter_width=3)
        # The spike at index 2 should be reduced
        self.assertLess(result[0, 2].item(), 10.0)

    def test_short_input_passthrough(self):
        """Inputs shorter than pad width should be returned as-is."""
        x = torch.tensor([[1.0]])
        result = median_filter(x, filter_width=5)
        torch.testing.assert_close(result, x)


class PmiScoreTests(unittest.TestCase):
    """Tests for the PMI pure functions."""

    def test_positive_pmi(self):
        """Conditional > unconditional should yield positive PMI."""
        result = pmi_score(-1.0, -2.0)
        self.assertAlmostEqual(result, 1.0)

    def test_zero_pmi(self):
        """Equal log probs should yield zero PMI."""
        result = pmi_score(-1.5, -1.5)
        self.assertAlmostEqual(result, 0.0)

    def test_negative_pmi(self):
        """Conditional < unconditional should yield negative PMI."""
        result = pmi_score(-3.0, -1.0)
        self.assertAlmostEqual(result, -2.0)


class PmiNormalizedScoreTests(unittest.TestCase):
    """Tests for the PMI-to-sigmoid normalization."""

    def test_zero_pmi_gives_half(self):
        """PMI of zero should map to exactly 0.5."""
        self.assertAlmostEqual(pmi_to_normalized_score(0.0), 0.5)

    def test_positive_pmi_above_half(self):
        """Positive PMI should map above 0.5."""
        self.assertGreater(pmi_to_normalized_score(1.0), 0.5)

    def test_negative_pmi_below_half(self):
        """Negative PMI should map below 0.5."""
        self.assertLess(pmi_to_normalized_score(-1.0), 0.5)

    def test_bounded_zero_one(self):
        """Output should always be in [0, 1]."""
        for pmi_val in [-100, -10, -1, 0, 1, 10, 100]:
            score = pmi_to_normalized_score(float(pmi_val), scale=1.0)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)


class RewardScoreTests(unittest.TestCase):
    """Tests for the reward score aggregation."""

    def test_all_components_present(self):
        """With all three components, result should be a weighted average."""
        scores = {"caption": 0.8, "lyrics": 0.6, "bpm": 0.9}
        total, _ = calculate_reward_score(scores)
        self.assertGreater(total, 0.0)
        self.assertLessEqual(total, 1.0)

    def test_no_scores_returns_zero(self):
        """Empty scores dict should return zero reward."""
        total, explanation = calculate_reward_score({})
        self.assertEqual(total, 0.0)

    def test_caption_only(self):
        """With only caption, reward should equal the caption score."""
        scores = {"caption": 0.75}
        total, _ = calculate_reward_score(scores)
        self.assertAlmostEqual(total, 0.75, places=2)

    def test_metadata_aggregation(self):
        """Multiple metadata fields should be averaged into one component."""
        scores = {"bpm": 1.0, "duration": 0.5}
        total, _ = calculate_reward_score(scores)
        # Only metadata component present, so total = avg(1.0, 0.5) = 0.75
        self.assertAlmostEqual(total, 0.75, places=2)


if __name__ == "__main__":
    unittest.main()
