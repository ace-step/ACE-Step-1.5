"""Unit tests for TaskUtilsMixin helper methods."""

import unittest

from acestep.core.generation.handler.task_utils import TaskUtilsMixin


class _Host(TaskUtilsMixin):
    """Minimal host implementing TaskUtilsMixin dependencies."""


class DetermineTaskTypeTests(unittest.TestCase):
    """Validate task-mode boolean computation in determine_task_type."""

    def setUp(self):
        self.host = _Host()

    def test_repaint_task_enables_repainting(self):
        """Repaint task should set can_use_repainting=True."""
        is_repaint, is_lego, is_cover, can_repaint = self.host.determine_task_type("repaint", None)
        self.assertTrue(is_repaint)
        self.assertFalse(is_lego)
        self.assertFalse(is_cover)
        self.assertTrue(can_repaint)

    def test_lego_task_enables_repainting_for_chunk_mask(self):
        """Lego task should set can_use_repainting=True so the chunk mask is computed
        from repainting_start/end, marking which positions have active audio to generate.

        Source audio silencing is prevented separately in _build_chunk_masks_and_src_latents
        via instruction-text detection, not here.
        """
        is_repaint, is_lego, is_cover, can_repaint = self.host.determine_task_type("lego", None)
        self.assertFalse(is_repaint)
        self.assertTrue(is_lego)
        self.assertFalse(is_cover)
        self.assertTrue(can_repaint, "lego must use the repainting path to get a proper chunk mask")

    def test_cover_task_is_not_repaint(self):
        """Cover task should not set can_use_repainting=True."""
        is_repaint, is_lego, is_cover, can_repaint = self.host.determine_task_type("cover", None)
        self.assertFalse(is_repaint)
        self.assertFalse(is_lego)
        self.assertTrue(is_cover)
        self.assertFalse(can_repaint)

    def test_text2music_task_is_not_repaint(self):
        """Text-to-music task should not set can_use_repainting=True."""
        is_repaint, is_lego, is_cover, can_repaint = self.host.determine_task_type("text2music", None)
        self.assertFalse(is_repaint)
        self.assertFalse(is_lego)
        self.assertFalse(is_cover)
        self.assertFalse(can_repaint)

    def test_audio_codes_upgrade_task_to_cover(self):
        """Providing audio codes should set is_cover_task=True regardless of task_type."""
        is_repaint, is_lego, is_cover, can_repaint = self.host.determine_task_type(
            "text2music", "<|audio_code_1|>"
        )
        self.assertFalse(is_repaint)
        self.assertFalse(is_lego)
        self.assertTrue(is_cover)
        self.assertFalse(can_repaint)

    def test_lego_with_audio_codes_enables_repainting(self):
        """Lego with audio codes should still have can_use_repainting=True for chunk mask."""
        is_repaint, is_lego, is_cover, can_repaint = self.host.determine_task_type(
            "lego", "<|audio_code_1|>"
        )
        self.assertTrue(is_lego)
        self.assertTrue(is_cover)
        self.assertTrue(can_repaint, "lego must use the repainting path for chunk mask")


if __name__ == "__main__":
    unittest.main()
