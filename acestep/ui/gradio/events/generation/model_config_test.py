"""Unit tests for model configuration and UI control settings."""

import unittest

from acestep.ui.gradio.events.generation.model_config import (
    _has_token,
    is_sft_model,
    is_pure_base_model,
    get_ui_control_config,
    update_model_type_settings,
)


class HasTokenTests(unittest.TestCase):
    """Verify _has_token matches tokens at various delimiter boundaries."""

    def test_token_with_hyphens(self):
        """Standard hyphen-delimited path."""
        self.assertTrue(_has_token("sft", "acestep-sft-1b"))

    def test_token_at_start(self):
        """Token at the beginning of the string."""
        self.assertTrue(_has_token("sft", "sft-model"))

    def test_token_at_end(self):
        """Token at the end of the string."""
        self.assertTrue(_has_token("sft", "model-sft"))

    def test_token_alone(self):
        """Token is the entire string."""
        self.assertTrue(_has_token("sft", "sft"))

    def test_token_with_dots(self):
        """Dot-delimited path."""
        self.assertTrue(_has_token("sft", "model.sft.v1"))

    def test_token_with_underscores(self):
        """Underscore-delimited path."""
        self.assertTrue(_has_token("sft", "model_sft_v1"))

    def test_token_embedded_rejected(self):
        """Token inside a larger word is not matched."""
        self.assertFalse(_has_token("sft", "sftp-server"))
        self.assertFalse(_has_token("base", "database"))


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

    def test_substring_inside_larger_word_rejected(self):
        """Word-boundary matching rejects 'sft' embedded in larger tokens.

        "sftp-server" contains "sft" but not as a delimited token.
        """
        self.assertFalse(is_sft_model("sftp-server"))

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

    def test_substring_inside_larger_word_rejected(self):
        """Word-boundary matching rejects 'base' embedded in larger tokens.

        "database" contains "base" but not as a delimited token.
        """
        self.assertFalse(is_pure_base_model("database-model"))

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

    def test_substring_no_false_positive_end_to_end(self):
        """Word-boundary matching prevents false positives end-to-end.

        "sftp-server" contains "sft" but not as a delimited token,
        so it correctly falls through to the 32-step default.
        """
        result = update_model_type_settings("sftp-server")
        self.assertEqual(result[0]["value"], 32)


if __name__ == "__main__":
    unittest.main()
