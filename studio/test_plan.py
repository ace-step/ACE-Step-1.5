"""Tests for studio planning helpers."""

import unittest

from plan import (
    choose_parallel_batch,
    folder_name_for_prompt,
    instrumental_caption,
    normalize_quality,
)


class PlanTests(unittest.TestCase):
    def test_unknown_quality_uses_high(self):
        self.assertEqual("high", normalize_quality(None))
        self.assertEqual("high", normalize_quality("lossless"))
        self.assertEqual("standard", normalize_quality("Standard"))

    def test_caption_is_instrumental(self):
        caption = instrumental_caption("  warm   analog  jazz  ")
        self.assertTrue(caption.startswith("Instrumental music with no vocals"))
        self.assertIn("warm analog jazz", caption)

    def test_folder_name_summarizes_the_opening_line(self):
        village = folder_name_for_prompt(
            "Peaceful Indian village morning lo-fi instrumental. Imagine sitting."
        )
        cafe = folder_name_for_prompt(
            "Relaxed Indian café lo-fi instrumental for a peaceful evening."
        )
        self.assertEqual("peaceful-indian-village-morning-lo-fi", village)
        self.assertEqual("relaxed-indian-cafe-lo-fi-peaceful-evening", cafe)
        self.assertNotIn(" ", village)
        self.assertNotIn("/", cafe)

    def test_empty_prompt_still_has_a_folder_name(self):
        self.assertEqual("track", folder_name_for_prompt("   "))

    def test_empty_prompt_is_rejected(self):
        with self.assertRaises(ValueError):
            instrumental_caption("   ")

    def test_xl_parallel_batch_stays_small(self):
        self.assertEqual(1, choose_parallel_batch(2.0, 10, True))
        self.assertEqual(2, choose_parallel_batch(8.0, 10, True))
        self.assertEqual(2, choose_parallel_batch(20.0, 10, True))

    def test_batch_never_exceeds_request(self):
        self.assertEqual(1, choose_parallel_batch(20.0, 1, False))
        self.assertEqual(4, choose_parallel_batch(20.0, 10, False))


if __name__ == "__main__":
    unittest.main()
