"""Unit tests for internal helpers in ``batch_management.py``."""

import unittest

from _batch_management_test_support import load_batch_management_module


class _ValueWrapper:
    """Simple object exposing a ``value`` attribute for score extraction tests."""

    def __init__(self, value):
        """Store wrapped value for ``_extract_scores`` compatibility."""
        self.value = value


class BatchManagementHelperTests(unittest.TestCase):
    """Tests for helper functions used by batch-management flows."""

    def test_extract_ui_core_outputs_trims_to_46(self):
        """Helper should return exactly the first 46 entries from long tuples."""
        module, _state = load_batch_management_module(is_windows=False)
        source = tuple(range(60))
        result = module._extract_ui_core_outputs(source)
        self.assertEqual(len(result), 46)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[-1], 45)

    def test_extract_ui_core_outputs_keeps_short_tuples(self):
        """Helper should preserve tuples shorter than 46 outputs unchanged."""
        module, _state = load_batch_management_module(is_windows=False)
        source = tuple(range(12))
        self.assertEqual(module._extract_ui_core_outputs(source), source)

    def test_build_saved_params_keeps_input_fields(self):
        """Saved params snapshot should preserve core generation settings."""
        module, _state = load_batch_management_module(is_windows=False)
        params = module._build_saved_params(
            "cap",
            "lyr",
            120,
            "C",
            "4/4",
            "en",
            8,
            7.0,
            True,
            "42",
            None,
            30,
            2,
            None,
            "",
            0.0,
            10.0,
            "",
            1.0,
            0.0,
            "text2music",
            False,
            0.0,
            1.0,
            1.0,
            "ode",
            "flac",
            0.85,
            True,
            2.0,
            0,
            0.9,
            "",
            True,
            True,
            True,
            False,
            False,
            False,
            False,
            0.5,
            8,
            "track",
            [],
            True,
            -1.0,
            0.0,
            1.0,
        )
        self.assertEqual(params["captions"], "cap")
        self.assertEqual(params["lyrics"], "lyr")
        self.assertEqual(params["track_name"], "track")
        self.assertIn("latent_rescale", params)

    def test_apply_param_defaults_adds_missing_without_overwrite(self):
        """Defaults helper should add absent keys and preserve existing values."""
        module, _state = load_batch_management_module(is_windows=False)
        params = {"captions": "keep", "lm_top_k": 7}
        module._apply_param_defaults(params)
        self.assertEqual(params["captions"], "keep")
        self.assertEqual(params["lm_top_k"], 7)
        self.assertEqual(params["audio_format"], "flac")
        self.assertIn("latent_shift", params)

    def test_extract_scores_handles_wrapped_values_and_missing_indices(self):
        """Score extraction should normalize mixed score payload shapes."""
        module, _state = load_batch_management_module(is_windows=False)
        final_result = [None] * 16
        final_result[12] = _ValueWrapper("9.1")
        final_result[13] = "8.2"
        final_result[14] = object()
        scores = module._extract_scores(final_result)
        self.assertEqual(len(scores), 8)
        self.assertEqual(scores[0], "9.1")
        self.assertEqual(scores[1], "8.2")
        self.assertEqual(scores[2], "")
        self.assertEqual(scores[-1], "")

    def test_log_background_params_records_messages(self):
        """Logging helper should emit expected entries without raising."""
        module, state = load_batch_management_module(is_windows=False)
        module._log_background_params(
            {"captions": "cap", "lyrics": "lyr", "track_name": "trk", "text2music_audio_code_string": ""},
            1,
        )
        self.assertTrue(state["log_info"])
        self.assertTrue(any("BACKGROUND GENERATION BATCH" in line for line in state["log_info"]))


if __name__ == "__main__":
    unittest.main()
