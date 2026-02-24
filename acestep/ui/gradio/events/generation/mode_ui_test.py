"""Unit tests for mode_ui state-clearing behavior on mode switch.

Verifies that compute_mode_ui_updates correctly clears stale
text2music_audio_code_string and src_audio values when switching
between modes, preventing the state-leakage noise bug.
"""

import unittest
from types import SimpleNamespace

try:
    from acestep.ui.gradio.events.generation.mode_ui import compute_mode_ui_updates
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment dependency guard
    compute_mode_ui_updates = None
    _IMPORT_ERROR = exc

# Output indices for the two new state-clearing outputs
_IDX_AUDIO_CODES = 42
_IDX_SRC_AUDIO = 43
_EXPECTED_TUPLE_LENGTH = 44


@unittest.skipIf(compute_mode_ui_updates is None,
                 f"compute_mode_ui_updates import unavailable: {_IMPORT_ERROR}")
class ModeUiStateClearingTests(unittest.TestCase):
    """Tests that mode switches clear stale UI state to prevent noise."""

    def test_tuple_length(self):
        """compute_mode_ui_updates should return exactly 44 elements."""
        result = compute_mode_ui_updates("Custom")
        self.assertEqual(len(result), _EXPECTED_TUPLE_LENGTH)

    def test_custom_mode_preserves_audio_codes(self):
        """In Custom mode, audio_codes textbox should be visible but not cleared."""
        result = compute_mode_ui_updates("Custom")
        codes_update = result[_IDX_AUDIO_CODES]
        # Should only set visibility, not clear the value
        self.assertTrue(codes_update.get("visible"))
        self.assertNotIn("value", codes_update)

    def test_remix_mode_clears_audio_codes(self):
        """Switching to Remix should clear the audio_codes textbox value."""
        result = compute_mode_ui_updates("Remix", previous_mode="Custom")
        codes_update = result[_IDX_AUDIO_CODES]
        self.assertEqual(codes_update.get("value"), "")
        self.assertFalse(codes_update.get("visible"))

    def test_simple_mode_clears_audio_codes(self):
        """Switching to Simple should clear the audio_codes textbox value."""
        result = compute_mode_ui_updates("Simple", previous_mode="Custom")
        codes_update = result[_IDX_AUDIO_CODES]
        self.assertEqual(codes_update.get("value"), "")

    def test_repaint_mode_clears_audio_codes(self):
        """Switching to Repaint should clear the audio_codes textbox value."""
        result = compute_mode_ui_updates("Repaint", previous_mode="Custom")
        codes_update = result[_IDX_AUDIO_CODES]
        self.assertEqual(codes_update.get("value"), "")

    def test_custom_mode_clears_src_audio(self):
        """Switching to Custom should clear src_audio (no source audio needed)."""
        result = compute_mode_ui_updates("Custom", previous_mode="Remix")
        src_update = result[_IDX_SRC_AUDIO]
        self.assertIsNone(src_update.get("value"))

    def test_simple_mode_clears_src_audio(self):
        """Switching to Simple should clear src_audio."""
        result = compute_mode_ui_updates("Simple", previous_mode="Remix")
        src_update = result[_IDX_SRC_AUDIO]
        self.assertIsNone(src_update.get("value"))

    def test_remix_mode_preserves_src_audio(self):
        """In Remix mode, src_audio should not be cleared (it's needed)."""
        result = compute_mode_ui_updates("Remix")
        src_update = result[_IDX_SRC_AUDIO]
        # Should be a no-op update (no value key)
        self.assertNotIn("value", src_update)

    def test_repaint_mode_preserves_src_audio(self):
        """In Repaint mode, src_audio should not be cleared (it's needed)."""
        result = compute_mode_ui_updates("Repaint")
        src_update = result[_IDX_SRC_AUDIO]
        self.assertNotIn("value", src_update)

    def test_round_trip_remix_to_custom_clears_both(self):
        """Switching Remix -> Custom should clear both codes and src_audio."""
        result = compute_mode_ui_updates("Custom", previous_mode="Remix")
        codes_update = result[_IDX_AUDIO_CODES]
        src_update = result[_IDX_SRC_AUDIO]
        # Custom mode should not clear codes (it uses them)
        self.assertTrue(codes_update.get("visible"))
        # But src_audio should be cleared
        self.assertIsNone(src_update.get("value"))

    def test_round_trip_custom_to_remix_clears_codes(self):
        """Switching Custom -> Remix should clear stale audio codes."""
        result = compute_mode_ui_updates("Remix", previous_mode="Custom")
        codes_update = result[_IDX_AUDIO_CODES]
        self.assertEqual(codes_update.get("value"), "")


if __name__ == "__main__":
    unittest.main()
