"""Unit tests for Gradio generation task-type helpers."""

import unittest

from acestep.ui.gradio.events.results.generation_task_type import resolve_no_fsq_task_type


class GenerationTaskTypeTests(unittest.TestCase):
    """Validate UI task-type resolution before inference."""

    def test_no_fsq_cover_uses_raw_cover_task(self):
        """Checking no_fsq in Remix should select the non-FSQ backend task."""
        self.assertEqual(resolve_no_fsq_task_type("cover", True), "cover-nofsq")

    def test_unchecked_cover_uses_standard_cover_task(self):
        """Unchecked Remix should keep the default FSQ cover behavior."""
        self.assertEqual(resolve_no_fsq_task_type("cover", False), "cover")

    def test_no_fsq_does_not_affect_non_cover_tasks(self):
        """Hidden checked state should not alter other generation modes."""
        self.assertEqual(resolve_no_fsq_task_type("repaint", True), "repaint")
        self.assertEqual(resolve_no_fsq_task_type("text2music", True), "text2music")


if __name__ == "__main__":
    unittest.main()
