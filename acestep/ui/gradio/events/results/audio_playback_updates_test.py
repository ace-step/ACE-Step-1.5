"""Unit tests for audio_playback_updates helpers."""

import importlib.util
from pathlib import Path
import unittest


def _load_module():
    """Load the target module directly by file path for isolated testing."""
    module_path = Path(__file__).with_name("audio_playback_updates.py")
    spec = importlib.util.spec_from_file_location("audio_playback_updates", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_MODULE = _load_module()
build_audio_slot_update = _MODULE.build_audio_slot_update


class _FakeGr:
    """Minimal Gradio-like stub exposing ``update``."""

    @staticmethod
    def update(**kwargs):
        """Return kwargs for direct assertion in tests."""
        return kwargs


class AudioPlaybackUpdatesTests(unittest.TestCase):
    """Behavior tests for audio playback update builders."""

    def test_build_audio_slot_update_sets_value_and_rewinds(self):
        """Success path: slot update should carry path and playback reset."""
        sample_path = "sample.flac"
        result = build_audio_slot_update(
            _FakeGr,
            sample_path,
            label="Sample 1 (Ready)",
            interactive=False,
        )
        self.assertEqual(result["value"], sample_path)
        self.assertEqual(result["playback_position"], 0)
        self.assertEqual(result["label"], "Sample 1 (Ready)")
        self.assertFalse(result["interactive"])

    def test_build_audio_slot_update_clear_path_rewinds(self):
        """Regression path: clearing a slot should still force playback to start."""
        result = build_audio_slot_update(_FakeGr, None)
        self.assertEqual(result["value"], None)
        self.assertEqual(result["playback_position"], 0)

    def test_build_audio_slot_update_without_optional_flags_preserves_defaults(self):
        """Non-target behavior: no label/interactivity overrides unless explicitly passed."""
        sample_path = "sample.flac"
        result = build_audio_slot_update(_FakeGr, sample_path)
        self.assertEqual(result["value"], sample_path)
        self.assertEqual(result["playback_position"], 0)
        self.assertNotIn("label", result)
        self.assertNotIn("interactive", result)


if __name__ == "__main__":
    unittest.main()
