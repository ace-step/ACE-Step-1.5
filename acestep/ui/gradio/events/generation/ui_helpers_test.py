"""Unit tests for small generation UI helper functions."""

import unittest

from acestep.ui.gradio.events.generation.ui_helpers import (
    get_dcw_defaults_for_think,
    update_dcw_defaults_for_think,
)


class DcwDefaultTests(unittest.TestCase):
    """Validate Think-aware DCW default selection."""

    def test_think_mode_uses_think_dcw_defaults(self):
        """Think mode should use the LM-tuned DCW defaults."""
        defaults = get_dcw_defaults_for_think(True)
        self.assertEqual(defaults["mode"], "double")
        self.assertEqual(defaults["scaler"], 0.02)
        self.assertEqual(defaults["high_scaler"], 0.06)

    def test_non_think_mode_uses_original_dcw_defaults(self):
        """Non-Think mode should keep the existing pure-DiT DCW defaults."""
        defaults = get_dcw_defaults_for_think(False)
        self.assertEqual(defaults["mode"], "double")
        self.assertEqual(defaults["scaler"], 0.05)
        self.assertEqual(defaults["high_scaler"], 0.02)

    def test_update_dcw_defaults_returns_gradio_updates(self):
        """The event handler should return updates in component order."""
        mode_update, scaler_update, high_scaler_update = update_dcw_defaults_for_think(True)
        self.assertEqual(mode_update.get("value"), "double")
        self.assertEqual(scaler_update.get("value"), 0.02)
        self.assertEqual(high_scaler_update.get("value"), 0.06)


if __name__ == "__main__":
    unittest.main()
