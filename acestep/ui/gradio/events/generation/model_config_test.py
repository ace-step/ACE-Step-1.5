"""Unit tests for model configuration and UI control settings."""

import unittest

from acestep.ui.gradio.events.generation.model_config import (
    is_sft_model,
    is_pure_base_model,
    get_ui_control_config,
    update_model_type_settings,
)


class IsSftModelTests(unittest.TestCase):
    """Verify is_sft_model correctly identifies SFT model paths."""

    def test_sft_model_detected(self):
        """Paths containing 'sft' without 'turbo' should be identified as SFT."""
        self.assertTrue(is_sft_model("acestep-sft-1b-v1"))

    def test_turbo_model_not_sft(self):
        """Turbo models should not be classified as SFT even if path contains 'sft'."""
        self.assertFalse(is_sft_model("acestep-sft-turbo-1b"))

    def test_base_model_not_sft(self):
        """Plain base models should not be classified as SFT."""
        self.assertFalse(is_sft_model("acestep-base-1b"))

    def test_substring_match_is_not_word_bounded(self):
        """Known limitation: ``"sft" in path`` matches inside larger words.

        "sftp-server" contains "sft", so is_sft_model falsely returns True.
        Same pre-existing pattern as is_pure_base_model ("database" → "base").
        Fixing requires word-boundary matching — separate refactor.
        """
        self.assertTrue(is_sft_model("sftp-server"))

    def test_unrelated_path_not_sft(self):
        """Paths without any SFT-related substring should not match."""
        self.assertFalse(is_sft_model("acestep-v15-1b"))


class IsPureBaseModelTests(unittest.TestCase):
    """Verify is_pure_base_model correctly identifies pure base model paths."""

    def test_base_model_detected(self):
        """Paths containing 'base' without 'sft' or 'turbo' should match."""
        self.assertTrue(is_pure_base_model("acestep-base-1b"))

    def test_sft_model_not_base(self):
        """SFT models should not be classified as pure base."""
        self.assertFalse(is_pure_base_model("acestep-base-sft-1b"))

    def test_turbo_model_not_base(self):
        """Turbo models should not be classified as pure base."""
        self.assertFalse(is_pure_base_model("acestep-base-turbo-1b"))

    def test_substring_match_is_not_word_bounded(self):
        """Known limitation: ``"base" in path`` matches inside larger words.

        "database" contains "base", so is_pure_base_model falsely returns True.
        Same pre-existing pattern as is_sft_model ("sftp-server" → "sft").
        Fixing requires word-boundary matching — separate refactor.
        """
        self.assertTrue(is_pure_base_model("database-model"))

    def test_unrelated_path_not_base(self):
        """Paths without any base-related substring should not match."""
        self.assertFalse(is_pure_base_model("acestep-v15-1b"))


class GetUiControlConfigTests(unittest.TestCase):
    """Verify get_ui_control_config returns correct defaults per model type."""

    def test_sft_model_returns_50_steps(self):
        """SFT models should default to 50 inference steps."""
        cfg = get_ui_control_config(is_turbo=False, is_sft=True)
        self.assertEqual(cfg["inference_steps_value"], 50)

    def test_base_model_returns_32_steps(self):
        """Non-SFT, non-turbo models should default to 32 inference steps."""
        cfg = get_ui_control_config(is_turbo=False, is_sft=False)
        self.assertEqual(cfg["inference_steps_value"], 32)

    def test_turbo_model_returns_8_steps(self):
        """Turbo models should default to 8 inference steps."""
        cfg = get_ui_control_config(is_turbo=True)
        self.assertEqual(cfg["inference_steps_value"], 8)

    def test_turbo_takes_precedence_over_sft(self):
        """When both turbo and SFT flags are set, turbo should win."""
        cfg = get_ui_control_config(is_turbo=True, is_sft=True)
        self.assertEqual(cfg["inference_steps_value"], 8)


class UpdateModelTypeSettingsIntegrationTests(unittest.TestCase):
    """End-to-end tests: config path string in, correct step defaults out."""

    def test_sft_path_produces_50_steps(self):
        """Passing an SFT model path should yield 50 inference steps."""
        result = update_model_type_settings("acestep-v15-sft")
        # First element is the inference_steps gr.update()
        self.assertEqual(result[0]["value"], 50)

    def test_turbo_path_produces_8_steps(self):
        """Passing a turbo model path should yield 8 inference steps."""
        result = update_model_type_settings("acestep-v15-turbo")
        self.assertEqual(result[0]["value"], 8)

    def test_base_path_produces_32_steps(self):
        """Passing a base model path should yield 32 inference steps."""
        result = update_model_type_settings("acestep-v15-base")
        self.assertEqual(result[0]["value"], 32)

    def test_none_path_does_not_crash(self):
        """Passing None as config_path should not raise."""
        result = update_model_type_settings(None)
        self.assertEqual(result[0]["value"], 32)

    def test_substring_false_positive_flows_through(self):
        """Substring false positive propagates end-to-end.

        "sftp-server" triggers SFT detection (contains "sft"), producing
        50 steps instead of 32. Update expected value to 32 if word-boundary
        matching is added to detection functions.
        """
        result = update_model_type_settings("sftp-server")
        self.assertEqual(result[0]["value"], 50)


if __name__ == "__main__":
    unittest.main()
