"""Unit tests for the results_handlers facade module.

Verifies that the thin re-export layer exposes every public symbol that
callers (e.g. ``events/__init__.py``, ``api_server.py``) depend on.
"""

import unittest

from acestep.ui.gradio.events import results_handlers as rh


class FacadeReExportTests(unittest.TestCase):
    """Ensure the facade re-exports all required public symbols."""

    _EXPECTED_SYMBOLS = [
        # constants
        "DEFAULT_RESULTS_DIR",
        "PROJECT_ROOT",
        # generation info
        "clear_audio_outputs_for_new_generation",
        "_build_generation_info",
        # LRC / VTT
        "parse_lrc_to_subtitles",
        "_format_vtt_timestamp",
        "lrc_to_vtt_file",
        "update_audio_subtitles_from_lrc",
        "save_lrc_to_file",
        "generate_lrc_handler",
        # batch queue
        "store_batch_in_queue",
        "update_batch_indicator",
        "update_navigation_buttons",
        "capture_current_params",
        "restore_batch_parameters",
        # scoring
        "calculate_score_handler",
        "calculate_score_handler_with_selection",
        # audio transfer
        "send_audio_to_src_with_metadata",
        "_extract_metadata_for_editing",
        "send_audio_to_remix",
        "send_audio_to_repaint",
        "convert_result_audio_to_codes",
        # generation
        "generate_with_progress",
        "generate_with_batch_management",
        "generate_next_batch_background",
        # navigation
        "navigate_to_previous_batch",
        "navigate_to_next_batch",
    ]

    def test_all_expected_symbols_are_importable(self):
        """Every symbol that callers depend on must be importable from the facade."""
        missing = [s for s in self._EXPECTED_SYMBOLS if not hasattr(rh, s)]
        self.assertEqual(
            missing,
            [],
            f"Missing symbols in results_handlers facade: {missing}",
        )

    def test_symbols_are_callable_or_constant(self):
        """Each symbol should be either callable (function) or a constant (str/int)."""
        for name in self._EXPECTED_SYMBOLS:
            obj = getattr(rh, name)
            self.assertTrue(
                callable(obj) or isinstance(obj, (str, int, float)),
                f"{name} is neither callable nor a constant: {type(obj)}",
            )


if __name__ == "__main__":
    unittest.main()
