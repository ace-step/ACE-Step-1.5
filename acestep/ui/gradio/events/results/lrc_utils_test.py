"""Unit tests for lrc_utils module."""

import unittest

from acestep.ui.gradio.events.results.lrc_utils import (
    parse_lrc_to_subtitles,
    _format_vtt_timestamp,
    save_lrc_to_file,
)


class ParseLrcToSubtitlesTests(unittest.TestCase):
    """Tests for parse_lrc_to_subtitles."""

    def test_empty_input_returns_empty_list(self):
        """Empty or None input should return an empty list."""
        self.assertEqual(parse_lrc_to_subtitles(""), [])
        self.assertEqual(parse_lrc_to_subtitles(None), [])
        self.assertEqual(parse_lrc_to_subtitles("   "), [])

    def test_single_line(self):
        """A single LRC line should produce one subtitle entry."""
        lrc = "[00:05.00]Hello world"
        result = parse_lrc_to_subtitles(lrc, total_duration=30.0)
        self.assertGreaterEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "Hello world")
        # Start time is in timestamp[0]
        self.assertAlmostEqual(result[0]["timestamp"][0], 5.0, places=1)

    def test_multiple_lines(self):
        """Multiple LRC lines should produce multiple subtitle entries."""
        lrc = "[00:05.00]Line one\n[00:10.00]Line two\n[00:15.00]Line three"
        result = parse_lrc_to_subtitles(lrc, total_duration=30.0)
        self.assertEqual(len(result), 3)
        texts = [s["text"] for s in result]
        self.assertIn("Line one", texts)
        self.assertIn("Line two", texts)
        self.assertIn("Line three", texts)

    def test_lines_without_timestamps_are_ignored(self):
        """Lines without LRC timestamps should be skipped."""
        lrc = "No timestamp here\n[00:05.00]Valid line"
        result = parse_lrc_to_subtitles(lrc, total_duration=30.0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "Valid line")

    def test_empty_text_lines_are_ignored(self):
        """Lines with timestamps but no text should be skipped."""
        lrc = "[00:05.00]\n[00:10.00]Has text"
        result = parse_lrc_to_subtitles(lrc, total_duration=30.0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "Has text")

    def test_three_digit_centiseconds(self):
        """LRC with 3-digit milliseconds should be parsed correctly."""
        lrc = "[01:23.456]Three digit"
        result = parse_lrc_to_subtitles(lrc, total_duration=120.0)
        self.assertEqual(len(result), 1)
        expected_time = 1 * 60 + 23 + 0.456
        self.assertAlmostEqual(result[0]["timestamp"][0], expected_time, places=2)

    def test_two_digit_centiseconds(self):
        """LRC with 2-digit centiseconds should be parsed correctly."""
        lrc = "[00:30.50]Two digit"
        result = parse_lrc_to_subtitles(lrc, total_duration=60.0)
        self.assertEqual(len(result), 1)
        expected_time = 30.5
        self.assertAlmostEqual(result[0]["timestamp"][0], expected_time, places=2)

    def test_subtitle_has_timestamp_pair(self):
        """Each subtitle entry should have a [start, end] timestamp pair."""
        lrc = "[00:05.00]Line one\n[00:10.00]Line two"
        result = parse_lrc_to_subtitles(lrc, total_duration=30.0)
        for entry in result:
            self.assertIn("timestamp", entry)
            self.assertEqual(len(entry["timestamp"]), 2)
            self.assertLess(entry["timestamp"][0], entry["timestamp"][1])


class FormatVttTimestampTests(unittest.TestCase):
    """Tests for _format_vtt_timestamp."""

    def test_zero_seconds(self):
        """0 seconds should format as 00:00:00.000."""
        self.assertEqual(_format_vtt_timestamp(0), "00:00:00.000")

    def test_simple_seconds(self):
        """Simple seconds value should format correctly."""
        result = _format_vtt_timestamp(65.5)
        self.assertEqual(result, "00:01:05.500")

    def test_hours(self):
        """Values over 3600 should include hours."""
        result = _format_vtt_timestamp(3661.123)
        self.assertEqual(result, "01:01:01.123")


class SaveLrcToFileTests(unittest.TestCase):
    """Tests for save_lrc_to_file."""

    def test_empty_lrc_returns_skip(self):
        """Empty LRC text should return a gr.skip() dict."""
        result = save_lrc_to_file("")
        self.assertIsInstance(result, dict)

    def test_none_lrc_returns_skip(self):
        """None LRC text should return a gr.skip() dict."""
        result = save_lrc_to_file(None)
        self.assertIsInstance(result, dict)

    def test_valid_lrc_returns_update_dict(self):
        """Valid LRC text should return a gr.update dict with a file path."""
        lrc_text = "[00:05.00]Hello world\n[00:10.00]Goodbye"
        result = save_lrc_to_file(lrc_text)
        self.assertIsInstance(result, dict)
        # gr.update returns a dict with __type__ == 'update'
        self.assertEqual(result.get("__type__"), "update")
        # Should have a value pointing to a .lrc file
        self.assertIn("value", result)
        self.assertTrue(result["value"].endswith(".lrc"))


if __name__ == "__main__":
    unittest.main()
