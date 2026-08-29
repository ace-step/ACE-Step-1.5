"""Tests for OpenRouter message parsing helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from acestep.openrouter_adapter import _parse_messages


class OpenRouterAdapterParseMessagesTests(unittest.TestCase):
    """Verify plain text heuristics route input into the expected mode."""

    def test_plain_text_without_tags_maps_to_sample_query(self) -> None:
        """A standard single-line prompt should be treated as sample-query input."""
        prompt, lyrics, _audio_blobs, sample_query = _parse_messages(
            [SimpleNamespace(role="user", content="Generate an upbeat pop song about summer travel")]
        )

        self.assertEqual(prompt, "")
        self.assertEqual(lyrics, "")
        self.assertEqual(sample_query, "Generate an upbeat pop song about summer travel")

    def test_tagged_prompt_still_maps_to_prompt(self) -> None:
        """Explicit <prompt> tags must continue to map to prompt mode."""
        prompt, lyrics, _audio_blobs, sample_query = _parse_messages(
            [SimpleNamespace(role="user", content="<prompt>Dreamy lo-fi beat</prompt>")]
        )

        self.assertEqual(prompt, "Dreamy lo-fi beat")
        self.assertEqual(lyrics, "")
        self.assertIsNone(sample_query)

    def test_lyrics_like_text_maps_to_lyrics(self) -> None:
        """Lyrics-style text should still be classified as lyrics mode."""
        content = "[Verse 1]\nWalking down the street\nFeeling the beat\n\n[Chorus]\nDance with me tonight"
        prompt, lyrics, _audio_blobs, sample_query = _parse_messages(
            [SimpleNamespace(role="user", content=content)]
        )

        self.assertEqual(prompt, "")
        self.assertEqual(lyrics, content)
        self.assertIsNone(sample_query)


if __name__ == "__main__":
    unittest.main()
