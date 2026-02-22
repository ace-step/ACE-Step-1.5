"""Unit tests for audio player preference head-script generation."""

import importlib.util
from pathlib import Path
import unittest


def _load_module():
    """Load the target module directly by file path for isolated testing."""
    module_path = Path(__file__).with_name("audio_player_preferences.py")
    spec = importlib.util.spec_from_file_location("audio_player_preferences", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_MODULE = _load_module()
get_audio_player_preferences_head = _MODULE.get_audio_player_preferences_head


class AudioPlayerPreferencesHeadTests(unittest.TestCase):
    """Tests for browser script generation used by Gradio ``Blocks(head=...)``."""

    def test_script_contains_volume_persistence_and_sync_hooks(self):
        """Success path: script should include storage and volume-change handling."""
        script = get_audio_player_preferences_head()
        self.assertIn("<script>", script)
        self.assertIn("localStorage", script)
        self.assertIn("volumechange", script)
        self.assertIn("MutationObserver", script)
        self.assertIn("shadowRoot", script)
        self.assertIn("syncAllVolumeControlsToPreferred", script)
        self.assertIn("volume-slider", script)
        self.assertIn("readyForPersistence", script)
        self.assertIn("wasReadyBeforeLoad", script)
        self.assertIn("markReadyForPersistence", script)
        self.assertIn("isTrustedUserEvent", script)
        self.assertIn("STARTUP_RESYNC_WINDOW_MS", script)
        self.assertIn("setInterval", script)

    def test_script_resets_audio_position_on_updates(self):
        """Regression path: script should force playback to track start on reloads."""
        script = get_audio_player_preferences_head()
        self.assertIn("currentTime = 0", script)
        self.assertIn("loadstart", script)
        self.assertIn("loadedmetadata", script)

    def test_script_generation_is_stable(self):
        """Non-target behavior: function should be deterministic for repeated calls."""
        script_1 = get_audio_player_preferences_head()
        script_2 = get_audio_player_preferences_head()
        self.assertEqual(script_1, script_2)


if __name__ == "__main__":
    unittest.main()
