"""Unit tests for mode_ui state-clearing behavior on mode switch.

Verifies that compute_mode_ui_updates correctly clears stale
text2music_audio_code_string and src_audio values when switching
between modes, preventing the state-leakage noise bug.

Also verifies that think_checkbox is restored to True when switching
back to Custom/Simple modes after Remix/Repaint forced it off.
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
_IDX_THINK_CHECKBOX = 14
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
        """Switching Remix -> Custom should clear both audio_codes and src_audio.

        analyze_btn in Remix mode writes codes to text2music_audio_code_string.
        These must be cleared when entering Custom mode so stale codes are not
        passed to the DiT (the root cause of garbled audio after tab-switching).
        """
        result = compute_mode_ui_updates("Custom", previous_mode="Remix")
        codes_update = result[_IDX_AUDIO_CODES]
        src_update = result[_IDX_SRC_AUDIO]
        # Codes from analyze_btn in Remix must be cleared
        self.assertEqual(codes_update.get("value"), "")
        self.assertTrue(codes_update.get("visible"))
        # src_audio should also be cleared
        self.assertIsNone(src_update.get("value"))

    def test_repaint_to_custom_clears_audio_codes(self):
        """Switching Repaint -> Custom should clear audio codes (analyze_btn contaminates them)."""
        result = compute_mode_ui_updates("Custom", previous_mode="Repaint")
        codes_update = result[_IDX_AUDIO_CODES]
        self.assertEqual(codes_update.get("value"), "")
        self.assertTrue(codes_update.get("visible"))

    def test_simple_to_custom_preserves_audio_codes(self):
        """Switching Simple -> Custom should NOT clear audio codes (Simple has no analyze_btn)."""
        result = compute_mode_ui_updates("Custom", previous_mode="Simple")
        codes_update = result[_IDX_AUDIO_CODES]
        self.assertNotIn("value", codes_update)
        self.assertTrue(codes_update.get("visible"))

    def test_round_trip_custom_to_remix_clears_codes(self):
        """Switching Custom -> Remix should clear stale audio codes."""
        result = compute_mode_ui_updates("Remix", previous_mode="Custom")
        codes_update = result[_IDX_AUDIO_CODES]
        self.assertEqual(codes_update.get("value"), "")

    def test_remix_mode_forces_think_checkbox_off(self):
        """Remix mode should force think_checkbox to False and non-interactive."""
        llm_handler = SimpleNamespace(llm_initialized=True)
        result = compute_mode_ui_updates("Remix", llm_handler=llm_handler, previous_mode="Custom")
        think_update = result[_IDX_THINK_CHECKBOX]
        self.assertFalse(think_update.get("value"))
        self.assertFalse(think_update.get("interactive"))

    def test_repaint_mode_forces_think_checkbox_off(self):
        """Repaint mode should force think_checkbox to False and non-interactive."""
        llm_handler = SimpleNamespace(llm_initialized=True)
        result = compute_mode_ui_updates("Repaint", llm_handler=llm_handler, previous_mode="Custom")
        think_update = result[_IDX_THINK_CHECKBOX]
        self.assertFalse(think_update.get("value"))
        self.assertFalse(think_update.get("interactive"))

    def test_remix_to_custom_restores_think_checkbox(self):
        """Switching Remix -> Custom should restore think_checkbox to True when LM is initialized.

        This is the core regression test for the tab-switch noise bug:
        think_checkbox was stuck at False after returning from Remix mode,
        causing the LLM to be skipped and producing garbled audio.
        """
        llm_handler = SimpleNamespace(llm_initialized=True)
        result = compute_mode_ui_updates("Custom", llm_handler=llm_handler, previous_mode="Remix")
        think_update = result[_IDX_THINK_CHECKBOX]
        self.assertTrue(think_update.get("value"),
                        "think_checkbox must be restored to True when switching back to Custom mode")
        self.assertTrue(think_update.get("interactive"))

    def test_repaint_to_custom_restores_think_checkbox(self):
        """Switching Repaint -> Custom should restore think_checkbox to True."""
        llm_handler = SimpleNamespace(llm_initialized=True)
        result = compute_mode_ui_updates("Custom", llm_handler=llm_handler, previous_mode="Repaint")
        think_update = result[_IDX_THINK_CHECKBOX]
        self.assertTrue(think_update.get("value"))

    def test_remix_to_simple_restores_think_checkbox(self):
        """Switching Remix -> Simple should restore think_checkbox to True when LM is initialized."""
        llm_handler = SimpleNamespace(llm_initialized=True)
        result = compute_mode_ui_updates("Simple", llm_handler=llm_handler, previous_mode="Remix")
        think_update = result[_IDX_THINK_CHECKBOX]
        self.assertTrue(think_update.get("value"))

    def test_no_lm_keeps_think_checkbox_off(self):
        """Without LM initialized, think_checkbox should remain False even in Custom mode."""
        llm_handler = SimpleNamespace(llm_initialized=False)
        result = compute_mode_ui_updates("Custom", llm_handler=llm_handler, previous_mode="Remix")
        think_update = result[_IDX_THINK_CHECKBOX]
        self.assertFalse(think_update.get("value"))
        self.assertFalse(think_update.get("interactive"))


if __name__ == "__main__":
    unittest.main()
