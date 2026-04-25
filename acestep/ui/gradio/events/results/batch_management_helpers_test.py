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
            "cap",           # captions
            "lyr",           # lyrics
            120,             # bpm
            "C",             # key_scale
            "4/4",           # time_signature
            "en",            # vocal_language
            8,               # inference_steps
            7.0,             # guidance_scale
            True,            # random_seed_checkbox
            "42",            # seed
            None,            # reference_audio
            30,              # audio_duration
            2,               # batch_size_input
            None,            # src_audio
            "",              # text2music_audio_code_string
            0.0,             # repainting_start
            10.0,            # repainting_end
            "",              # instruction_display_gen
            1.0,             # audio_cover_strength
            0.0,             # cover_noise_strength
            "text2music",    # task_type
            False,           # no_fsq
            False,           # use_adg
            0.0,             # cfg_interval_start
            1.0,             # cfg_interval_end
            1.0,             # shift
            "ode",           # infer_method
            "euler",         # sampler_mode
            0.0,             # velocity_norm_threshold
            0.0,             # velocity_ema_factor
            True,            # dcw_enabled
            "double",        # dcw_mode
            0.05,            # dcw_scaler
            0.02,            # dcw_high_scaler
            "haar",          # dcw_wavelet
            "flac",          # audio_format
            "128k",          # mp3_bitrate
            48000,           # mp3_sample_rate
            0.85,            # lm_temperature
            True,            # think_checkbox
            2.0,             # lm_cfg_scale
            0,               # lm_top_k
            0.9,             # lm_top_p
            "",              # lm_negative_prompt
            True,            # use_cot_metas
            True,            # use_cot_caption
            True,            # use_cot_language
            False,           # constrained_decoding_debug
            False,           # allow_lm_batch
            False,           # auto_score
            False,           # auto_lrc
            0.5,             # score_scale
            8,               # lm_batch_chunk_size
            "track",         # track_name
            [],              # complete_track_classes
            True,            # enable_normalization
            -1.0,            # normalization_db
            0.0,             # fade_in_duration
            0.0,             # fade_out_duration
            0.0,             # latent_shift
            1.0,             # latent_rescale
        )
        self.assertEqual(params["captions"], "cap")
        self.assertEqual(params["lyrics"], "lyr")
        self.assertEqual(params["track_name"], "track")
        self.assertEqual(params["mp3_bitrate"], "128k")
        self.assertEqual(params["mp3_sample_rate"], 48000)
        self.assertEqual(params["sampler_mode"], "euler")
        self.assertFalse(params["no_fsq"])
        self.assertEqual(params["dcw_enabled"], True)
        self.assertEqual(params["dcw_mode"], "double")
        self.assertEqual(params["dcw_wavelet"], "haar")
        self.assertIn("latent_rescale", params)
        self.assertIn("fade_in_duration", params)
        self.assertIn("fade_out_duration", params)

    def test_apply_param_defaults_adds_missing_without_overwrite(self):
        """Defaults helper should add absent keys and preserve existing values."""
        module, _state = load_batch_management_module(is_windows=False)
        params = {"captions": "keep", "lm_top_k": 7}
        module._apply_param_defaults(params)
        self.assertEqual(params["captions"], "keep")
        self.assertEqual(params["lm_top_k"], 7)
        self.assertEqual(params["audio_format"], "flac")
        self.assertEqual(params["mp3_bitrate"], "128k")
        self.assertEqual(params["mp3_sample_rate"], 48000)
        self.assertIn("latent_shift", params)
        self.assertIn("fade_in_duration", params)
        self.assertIn("fade_out_duration", params)
        self.assertEqual(params["fade_in_duration"], 0.0)
        self.assertEqual(params["fade_out_duration"], 0.0)
        self.assertEqual(params["dcw_enabled"], True)
        self.assertEqual(params["dcw_mode"], "double")
        self.assertEqual(params["dcw_scaler"], 0.02)
        self.assertEqual(params["dcw_high_scaler"], 0.06)
        self.assertEqual(params["dcw_wavelet"], "haar")
        self.assertFalse(params["no_fsq"])

    def test_apply_param_defaults_uses_non_think_dcw_defaults_when_think_disabled(self):
        """Defaults helper should use pure-DiT DCW defaults when Think is off."""
        module, _state = load_batch_management_module(is_windows=False)
        params = {"think_checkbox": False}
        module._apply_param_defaults(params)
        self.assertEqual(params["dcw_mode"], "double")
        self.assertEqual(params["dcw_scaler"], 0.05)
        self.assertEqual(params["dcw_high_scaler"], 0.02)

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
