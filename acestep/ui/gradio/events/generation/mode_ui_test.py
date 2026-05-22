"""Unit tests for mode_ui state-clearing behavior on mode switch.

Verifies that compute_mode_ui_updates correctly clears stale
text2music_audio_code_string and src_audio values when switching
between modes, preventing the state-leakage noise bug.

Also verifies that think_checkbox is restored to True when switching
back to Custom/Simple modes after Remix/Repaint forced it off.

Also verifies that task_type (a gr.State) is correctly set on every
mode switch so that stale "repaint" task_type cannot leak into Custom
mode generation and trigger the "requires source audio" error.
"""

import unittest
from types import SimpleNamespace

try:
    from acestep.constants import GENERATION_MODES_BASE, GENERATION_MODES_TURBO, MODE_TO_TASK_TYPE
    from acestep.ui.gradio.events.generation.mode_ui import compute_mode_ui_updates
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment dependency guard
    compute_mode_ui_updates = None
    _IMPORT_ERROR = exc

# Output indices for the two new state-clearing outputs
_IDX_TASK_TYPE = 5       # Index of task_type (gr.State) in compute_mode_ui_updates return tuple
_IDX_SRC_AUDIO_ROW = 6
_IDX_AUDIO_CODES = 47
_IDX_SRC_AUDIO = 48
_IDX_FLOW_EDIT_COLUMN = 49
_IDX_FLOW_EDIT_MORPH = 50
_IDX_THINK_CHECKBOX = 14
_IDX_REMIX_STRENGTH = 17
_IDX_COVER_NOISE = 18
_EXPECTED_TUPLE_LENGTH = 51
_IDX_BPM = 21
_IDX_KEY = 22
_IDX_TIMESIG = 23
_IDX_VOCAL_LANG = 24
_IDX_DURATION = 25


@unittest.skipIf(compute_mode_ui_updates is None,
                 f"compute_mode_ui_updates import unavailable: {_IMPORT_ERROR}")
class ModeUiStateClearingTests(unittest.TestCase):
    """Tests that mode switches clear stale UI state to prevent noise."""

    def test_tuple_length(self):
        """compute_mode_ui_updates should return exactly 51 elements."""
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

    def test_remix_mode_uses_cover_task_and_source_audio_controls(self):
        """Remix should keep the standard cover task and source-audio controls."""
        llm_handler = SimpleNamespace(llm_initialized=True)
        result = compute_mode_ui_updates("Remix", llm_handler=llm_handler, previous_mode="Custom")
        self.assertEqual(result[_IDX_TASK_TYPE], "cover")
        self.assertTrue(result[_IDX_SRC_AUDIO_ROW].get("visible"))
        self.assertEqual(result[_IDX_AUDIO_CODES].get("value"), "")
        self.assertFalse(result[_IDX_AUDIO_CODES].get("visible"))
        self.assertNotIn("value", result[_IDX_SRC_AUDIO])
        self.assertTrue(result[_IDX_COVER_NOISE].get("visible"))
        self.assertEqual(result[_IDX_REMIX_STRENGTH].get("value"), 0.0)
        self.assertEqual(result[_IDX_COVER_NOISE].get("value"), 0.2)

        think_update = result[_IDX_THINK_CHECKBOX]
        self.assertFalse(think_update.get("value"))
        self.assertFalse(think_update.get("interactive"))

    def test_generation_modes_do_not_expose_raw_remix_as_top_level_mode(self):
        """Raw remix should be selected by no_fsq, not by a separate mode."""
        self.assertNotIn("Remix (Raw)", GENERATION_MODES_TURBO)
        self.assertNotIn("Remix (Raw)", GENERATION_MODES_BASE)
        self.assertNotIn("Remix (Raw)", MODE_TO_TASK_TYPE)

    def test_repaint_mode_preserves_src_audio(self):
        """In Repaint mode, src_audio should not be cleared (it's needed)."""
        result = compute_mode_ui_updates("Repaint")
        src_update = result[_IDX_SRC_AUDIO]
        self.assertNotIn("value", src_update)

    def test_repaint_mode_hides_and_disables_edit(self):
        """Repaint has its own local edit path, so flow-edit should be unavailable."""
        result = compute_mode_ui_updates("Repaint")

        self.assertFalse(result[_IDX_FLOW_EDIT_COLUMN].get("visible"))
        self.assertFalse(result[_IDX_FLOW_EDIT_MORPH].get("visible"))
        self.assertFalse(result[_IDX_FLOW_EDIT_MORPH].get("value"))

    def test_remix_mode_shows_edit(self):
        """Remix keeps the flow-edit overlay available."""
        result = compute_mode_ui_updates("Remix")

        self.assertTrue(result[_IDX_FLOW_EDIT_COLUMN].get("visible"))
        self.assertTrue(result[_IDX_FLOW_EDIT_MORPH].get("visible"))
        self.assertTrue(result[_IDX_FLOW_EDIT_MORPH].get("interactive"))

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

    def test_non_extract_modes_do_not_force_auto_fields_interactive(self):
        """Mode switches should not re-enable auto-managed metadata fields."""
        result = compute_mode_ui_updates("Remix", previous_mode="Custom")
        for idx in (_IDX_BPM, _IDX_KEY, _IDX_TIMESIG, _IDX_VOCAL_LANG, _IDX_DURATION):
            self.assertNotIn("interactive", result[idx])

    def test_leaving_extract_sets_auto_fields_non_interactive(self):
        """Leaving Extract should reset optional fields in locked auto state."""
        result = compute_mode_ui_updates("Custom", previous_mode="Extract")
        for idx in (_IDX_BPM, _IDX_KEY, _IDX_TIMESIG, _IDX_VOCAL_LANG, _IDX_DURATION):
            self.assertFalse(result[idx].get("interactive"))


@unittest.skipIf(compute_mode_ui_updates is None,
                 f"compute_mode_ui_updates import unavailable: {_IMPORT_ERROR}")
class ModeUiTaskTypeTests(unittest.TestCase):
    """Regression tests for task_type (gr.State) being correctly set on mode switches.

    These tests guard against the bug where switching from Repaint back to Custom
    mode left a stale ``task_type="repaint"`` value that caused the backend to raise
    "Task 'repaint' requires source audio, but none was provided."

    Because ``task_type`` is now a ``gr.State`` (not a hidden ``gr.Textbox``), the
    mode switch handler must return the raw string value directly rather than a
    ``gr.update()`` dict.  These tests confirm the returned value is a plain ``str``.
    """

    def test_repaint_to_custom_resets_task_type_to_text2music(self):
        """Switching Repaint → Custom must reset task_type to 'text2music'.

        This is the primary regression test for the bug described in the issue:
        going from Repaint back to Custom left task_type='repaint' in the UI
        state, causing generation to fail with "requires source audio".
        """
        result = compute_mode_ui_updates("Custom", previous_mode="Repaint")
        task_type_value = result[_IDX_TASK_TYPE]
        self.assertEqual(task_type_value, "text2music",
                         "task_type must be reset to 'text2music' when switching to Custom mode")
        self.assertIsInstance(task_type_value, str,
                              "task_type output must be a raw string (gr.State), not a gr.update() dict")

    def test_custom_mode_task_type_is_text2music(self):
        """Custom mode sets task_type to 'text2music'."""
        result = compute_mode_ui_updates("Custom")
        self.assertEqual(result[_IDX_TASK_TYPE], "text2music")

    def test_repaint_mode_task_type_is_repaint(self):
        """Repaint mode sets task_type to 'repaint'."""
        result = compute_mode_ui_updates("Repaint", previous_mode="Custom")
        self.assertEqual(result[_IDX_TASK_TYPE], "repaint")

    def test_remix_mode_task_type_is_cover(self):
        """Remix mode sets task_type to 'cover'."""
        result = compute_mode_ui_updates("Remix", previous_mode="Custom")
        self.assertEqual(result[_IDX_TASK_TYPE], "cover")

    def test_simple_mode_task_type_is_text2music(self):
        """Simple mode sets task_type to 'text2music'."""
        result = compute_mode_ui_updates("Simple", previous_mode="Custom")
        self.assertEqual(result[_IDX_TASK_TYPE], "text2music")

    def test_task_type_output_is_plain_string_not_dict(self):
        """task_type output must be a raw string, not a gr.update() dict.

        Using gr.State requires returning the raw value, not a gr.update() wrapper.
        Returning a gr.update() dict for a gr.State could cause Gradio to fail to
        update the state value, leaving stale values from previous modes.
        """
        for mode in ("Custom", "Repaint", "Remix", "Simple"):
            with self.subTest(mode=mode):
                result = compute_mode_ui_updates(mode)
                task_type_value = result[_IDX_TASK_TYPE]
                self.assertIsInstance(
                    task_type_value, str,
                    f"task_type for mode '{mode}' must be a plain string, got {type(task_type_value)}"
                )
                self.assertNotIsInstance(
                    task_type_value, dict,
                    f"task_type for mode '{mode}' must not be a gr.update() dict"
                )


try:
    from acestep.ui.gradio.events.generation.mode_ui import handle_extract_src_audio_change
    _EXTRACT_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment dependency guard
    handle_extract_src_audio_change = None
    _EXTRACT_IMPORT_ERROR = exc


@unittest.skipIf(handle_extract_src_audio_change is None,
                 f"handle_extract_src_audio_change import unavailable: {_EXTRACT_IMPORT_ERROR}")
class ExtractSrcAudioDurationTests(unittest.TestCase):
    """Regression tests for issue #1118 — Gradio temp-path 'safe root' rejection.

    Gradio uploads land under the system temp dir (e.g. AppData\\Local\\Temp\\gradio
    on Windows), which is outside the project safe-root. The handler must read
    duration without invoking the training-module path-safety guard.
    """

    def test_returns_noop_for_non_extract_lego_mode(self):
        """Non-Extract/Lego modes should return an empty update without inspecting the file."""
        result = handle_extract_src_audio_change("/anywhere/file.wav", "Custom")
        self.assertNotIn("value", result)

    def test_returns_noop_for_empty_src_audio(self):
        """Empty src_audio should short-circuit without raising."""
        result = handle_extract_src_audio_change("", "Extract")
        self.assertNotIn("value", result)

    def test_reads_duration_from_gradio_temp_path_without_safe_path(self):
        """A Gradio temp path outside the project safe root must NOT raise."""
        from unittest.mock import patch, MagicMock
        fake_info = MagicMock(duration=42.7)
        gradio_temp_path = r"C:\Users\test\AppData\Local\Temp\gradio\abc\song.wav"
        with patch("soundfile.info", return_value=fake_info) as mock_info:
            result = handle_extract_src_audio_change(gradio_temp_path, "Extract")
            mock_info.assert_called_once_with(gradio_temp_path)
        # gr.update(value=...) returns a plain dict; assert directly.
        self.assertEqual(result.get("value"), 42.7)

    def test_swallows_invalid_audio_errors(self):
        """A bad/unreadable file should be logged-and-skipped, not raised."""
        from unittest.mock import patch
        with patch("soundfile.info", side_effect=RuntimeError("bad file")):
            result = handle_extract_src_audio_change("/tmp/bogus.wav", "Lego")
        self.assertNotIn("value", result)


if __name__ == "__main__":
    unittest.main()
