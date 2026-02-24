"""Unit tests for batch_queue module."""

import unittest

from acestep.ui.gradio.events.results.batch_queue import (
    store_batch_in_queue,
    update_batch_indicator,
    update_navigation_buttons,
)


class UpdateNavigationButtonsTests(unittest.TestCase):
    """Tests for update_navigation_buttons."""

    def test_first_batch(self):
        """At first batch, prev should be False."""
        can_prev, can_next = update_navigation_buttons(0, 3)
        self.assertFalse(can_prev)
        self.assertTrue(can_next)

    def test_last_batch(self):
        """At last batch, next should be False."""
        can_prev, can_next = update_navigation_buttons(2, 3)
        self.assertTrue(can_prev)
        self.assertFalse(can_next)

    def test_middle_batch(self):
        """At a middle batch, both should be True."""
        can_prev, can_next = update_navigation_buttons(1, 3)
        self.assertTrue(can_prev)
        self.assertTrue(can_next)

    def test_single_batch(self):
        """With only one batch, both should be False."""
        can_prev, can_next = update_navigation_buttons(0, 1)
        self.assertFalse(can_prev)
        self.assertFalse(can_next)


class StoreBatchInQueueTests(unittest.TestCase):
    """Tests for store_batch_in_queue."""

    def test_store_first_batch(self):
        """Storing the first batch should create a new queue entry."""
        queue = {}
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=0,
            audio_paths=["/tmp/audio1.mp3"],
            generation_info="test info",
            seeds="42",
        )
        self.assertIsInstance(result, dict)
        self.assertIn(0, result)
        self.assertEqual(result[0]["audio_paths"], ["/tmp/audio1.mp3"])
        self.assertEqual(result[0]["generation_info"], "test info")

    def test_store_preserves_existing_batches(self):
        """Storing a new batch should not remove existing batches."""
        queue = {
            0: {
                "audio_paths": ["/tmp/old.mp3"],
                "generation_info": "old info",
                "seeds": "1",
                "status": "completed",
            }
        }
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=1,
            audio_paths=["/tmp/new.mp3"],
            generation_info="new info",
            seeds="99",
        )
        self.assertIn(0, result)
        self.assertIn(1, result)
        self.assertEqual(result[0]["audio_paths"], ["/tmp/old.mp3"])
        self.assertEqual(result[1]["audio_paths"], ["/tmp/new.mp3"])

    def test_store_with_scores_and_codes(self):
        """Storing with scores and codes should preserve them."""
        queue = {}
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=0,
            audio_paths=["/tmp/a.mp3"],
            generation_info="info",
            seeds="42",
            codes=["code1"],
            scores=["8.5/10"],
        )
        self.assertEqual(result[0]["codes"], ["code1"])
        self.assertEqual(result[0]["scores"], ["8.5/10"])

    def test_store_defaults_scores_to_empty(self):
        """Storing without scores should default to 8 empty strings."""
        queue = {}
        result = store_batch_in_queue(
            batch_queue=queue,
            batch_index=0,
            audio_paths=["/tmp/a.mp3"],
            generation_info="info",
            seeds="42",
        )
        self.assertEqual(result[0]["scores"], [""] * 8)


if __name__ == "__main__":
    unittest.main()
