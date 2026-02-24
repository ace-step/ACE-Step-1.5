"""Unit tests for training_utils.py."""

import unittest
from unittest.mock import patch

from acestep.ui.gradio.events.training.training_utils import (
    _format_duration,
    _safe_join,
    _safe_slider,
    _training_loss_figure,
    SAFE_TRAINING_ROOT,
)


class TestFormatDuration(unittest.TestCase):
    """Tests for _format_duration."""

    def test_seconds_only(self):
        self.assertEqual(_format_duration(45), "45s")

    def test_minutes_and_seconds(self):
        self.assertEqual(_format_duration(125), "2m 5s")

    def test_hours(self):
        self.assertEqual(_format_duration(3661), "1h 1m")

    def test_zero(self):
        self.assertEqual(_format_duration(0), "0s")


class TestSafeJoin(unittest.TestCase):
    """Tests for _safe_join."""

    def test_valid_relative_path(self):
        result = _safe_join("/base", "subdir/file.txt")
        # Should be under /base
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("/base"))

    def test_absolute_path_rejected(self):
        result = _safe_join("/base", "/etc/passwd")
        self.assertIsNone(result)

    def test_traversal_rejected(self):
        result = _safe_join("/base/root", "../../etc/passwd")
        self.assertIsNone(result)

    def test_empty_path(self):
        result = _safe_join("/base", "")
        self.assertIsNone(result)

    def test_none_path(self):
        result = _safe_join("/base", None)
        self.assertIsNone(result)


class TestSafeSlider(unittest.TestCase):
    """Tests for _safe_slider."""

    def test_minimum_max_value(self):
        slider = _safe_slider(0, value=0)
        # max_value should be at least 1
        self.assertIsNotNone(slider)

    def test_with_visible(self):
        slider = _safe_slider(10, value=5, visible=True)
        self.assertIsNotNone(slider)


class TestTrainingLossFigure(unittest.TestCase):
    """Tests for _training_loss_figure."""

    def test_empty_data_returns_figure(self):
        fig = _training_loss_figure({}, [], [])
        self.assertIsNotNone(fig)

    def test_with_data_returns_figure(self):
        fig = _training_loss_figure(
            {},
            [1, 2, 3, 4, 5],
            [0.5, 0.4, 0.3, 0.25, 0.2],
        )
        self.assertIsNotNone(fig)

    def test_with_ema_and_validation(self):
        state = {
            "plot_ema": [0.5, 0.45, 0.35, 0.28, 0.22],
            "plot_val_steps": [3, 5],
            "plot_val_loss": [0.35, 0.25],
            "plot_best_step": 5,
        }
        fig = _training_loss_figure(
            state,
            [1, 2, 3, 4, 5],
            [0.5, 0.4, 0.3, 0.25, 0.2],
        )
        self.assertIsNotNone(fig)


class TestSafeTrainingRoot(unittest.TestCase):
    """Tests for SAFE_TRAINING_ROOT constant."""

    def test_is_absolute(self):
        import os
        self.assertTrue(os.path.isabs(SAFE_TRAINING_ROOT))


if __name__ == "__main__":
    unittest.main()
