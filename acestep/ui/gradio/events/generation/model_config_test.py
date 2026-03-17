"""Unit tests for model configuration and UI control settings."""

import unittest

try:
    from acestep.ui.gradio.events.generation.model_config import (
        is_sft_model,
        get_ui_control_config,
    )
    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - dependency guard
    is_sft_model = None
    get_ui_control_config = None
    _IMPORT_ERROR = exc


@unittest.skipIf(is_sft_model is None, f"model_config import unavailable: {_IMPORT_ERROR}")
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


@unittest.skipIf(get_ui_control_config is None, f"model_config import unavailable: {_IMPORT_ERROR}")
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


if __name__ == "__main__":
    unittest.main()
