"""Unit tests for user preference persistence."""

import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest


def _ensure_gradio_stub():
    """Install a minimal ``gradio`` stub if the real package is absent.

    The stub only provides ``gr.update()`` which returns a dict sentinel,
    enough for ``restore_preferences`` to work in tests.
    """
    if "gradio" not in sys.modules:
        gr = types.ModuleType("gradio")
        gr.update = lambda **kwargs: {"__type__": "update", **kwargs}  # type: ignore[attr-defined]
        sys.modules["gradio"] = gr


_ensure_gradio_stub()


def _load_module():
    """Load the target module directly by file path for isolated testing."""
    module_path = Path(__file__).with_name("user_preferences.py")
    spec = importlib.util.spec_from_file_location("user_preferences", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_MODULE = _load_module()
get_user_preferences_head = _MODULE.get_user_preferences_head
_load_preferences_script = _MODULE._load_preferences_script
_build_restore_js = _MODULE._build_restore_js
restore_preferences = _MODULE.restore_preferences
PREF_KEYS = _MODULE.PREF_KEYS
_DEFAULTS = _MODULE._DEFAULTS
_SCRIPT_PATH = Path(__file__).with_name("user_preferences.js")


class SaveScriptTests(unittest.TestCase):
    """Tests for the save-side JavaScript injected via Gradio head."""

    def test_external_script_asset_exists(self):
        self.assertTrue(_SCRIPT_PATH.is_file())
        script_asset = _load_preferences_script()
        self.assertTrue(script_asset)

    def test_script_contains_localstorage_persistence(self):
        script = get_user_preferences_head()
        self.assertIn("<script>", script)
        self.assertIn("localStorage", script)
        self.assertIn("acestep.ui.user_preferences", script)

    def test_script_contains_all_preference_elem_ids(self):
        script = get_user_preferences_head()
        expected_ids = [
            "acestep-audio-format",
            "acestep-mp3-bitrate",
            "acestep-mp3-sample-rate",
            "acestep-score-scale",
            "acestep-enable-normalization",
            "acestep-normalization-db",
            "acestep-fade-in-duration",
            "acestep-fade-out-duration",
            "acestep-latent-shift",
            "acestep-latent-rescale",
            "acestep-lm-batch-chunk-size",
        ]
        for elem_id in expected_ids:
            self.assertIn(elem_id, script, f"Missing elem_id: {elem_id}")

    def test_script_is_save_only_no_restore_logic(self):
        """The JS should only save; restore is handled by Gradio .load()."""
        script = get_user_preferences_head()
        self.assertNotIn("restoreAll", script)
        self.assertNotIn("applyValue", script)
        self.assertNotIn("nativeInputValueSetter", script)

    def test_script_includes_schema_version(self):
        script = get_user_preferences_head()
        self.assertIn("SCHEMA_VERSION", script)
        self.assertIn("_version", script)

    def test_script_debounces_saves(self):
        script = get_user_preferences_head()
        self.assertIn("DEBOUNCE_MS", script)
        self.assertIn("clearTimeout", script)

    def test_script_uses_mutation_observer(self):
        """MutationObserver ensures listeners survive Gradio re-renders."""
        script = get_user_preferences_head()
        self.assertIn("MutationObserver", script)
        self.assertIn("wiredElements", script)

    def test_script_gracefully_handles_storage_failure(self):
        script = get_user_preferences_head()
        self.assertIn("catch", script)

    def test_script_generation_is_stable(self):
        script_1 = get_user_preferences_head()
        script_2 = get_user_preferences_head()
        self.assertEqual(script_1, script_2)


_NUM_OUTPUTS = len(PREF_KEYS) + 3  # +3 for mp3_controls_row, mp3_bitrate, mp3_sample_rate


class RestoreTests(unittest.TestCase):
    """Tests for the Gradio-native restore mechanism."""

    def test_restore_js_returns_valid_javascript(self):
        js = _build_restore_js(_NUM_OUTPUTS)
        self.assertIn("localStorage", js)
        self.assertIn("SCHEMA_VERSION", js)
        self.assertIn("acestep.ui.user_preferences", js)

    def test_restore_js_includes_all_pref_keys(self):
        js = _build_restore_js(_NUM_OUTPUTS)
        for key in PREF_KEYS:
            self.assertIn(f'"{key}"', js, f"Missing key in restore JS: {key}")

    def test_restore_js_only_resets_on_downgrade(self):
        """Version check should only discard prefs from future (higher) versions."""
        js = _build_restore_js(_NUM_OUTPUTS)
        self.assertIn("_version", js)
        self.assertIn("prefs._version > SCHEMA_VERSION", js)
        self.assertNotIn("prefs._version !== SCHEMA_VERSION", js)

    def test_restore_js_coerces_numeric_dropdown_values(self):
        """Dropdown values stored as strings in localStorage must be coerced
        back to numbers when the Gradio component expects integers."""
        js = _build_restore_js(_NUM_OUTPUTS)
        self.assertIn("NUMERIC_COERCE_KEYS", js)
        self.assertIn("Number(v)", js)

    def test_restore_js_validates_value_types(self):
        """Restore JS must include per-key type validation."""
        js = _build_restore_js(_NUM_OUTPUTS)
        self.assertIn("TYPE_MAP", js)
        self.assertIn("typeof v !== expected", js)

    def test_restore_js_returns_null_sentinel_when_no_stored_prefs(self):
        """When localStorage is empty the JS must return nulls so the Python
        side can skip updates and preserve init_params."""
        js = _build_restore_js(_NUM_OUTPUTS)
        self.assertIn("SKIP", js)
        self.assertIn("fill(null)", js)
        # Should NOT contain DEFAULTS as a fallback for empty storage.
        self.assertNotIn("DEFAULTS", js)

    def test_restore_js_includes_mp3_visibility_computation(self):
        """Restore JS should compute mp3_controls_row visibility from
        the restored audio_format and append it."""
        js = _build_restore_js(_NUM_OUTPUTS)
        self.assertIn("audioFormat", js)
        self.assertIn('result.push(', js)
        self.assertIn('"mp3"', js)

    def test_restore_preferences_passes_through_values(self):
        """Non-None values are passed through unchanged."""
        values = ("flac", "320k", 44100, 0.8, False, -3.0, 0.5, 1.0, 0.05, 0.95, 4, True)
        result = restore_preferences(*values)
        # First 11 values are direct pass-through, last is visibility.
        for i in range(len(PREF_KEYS)):
            self.assertEqual(result[i], values[i])

    def test_restore_preferences_converts_none_to_gr_update(self):
        """None values from JS should become gr.update() (no-op)."""
        values = (None, None, None, None, None, None, None, None, None, None, None, None)
        result = restore_preferences(*values)
        for v in result:
            self.assertIsInstance(v, dict, "None should be converted to gr.update()")
            self.assertEqual(v["__type__"], "update")

    def test_restore_preferences_converts_visibility_bools(self):
        """The trailing booleans for mp3 controls should become
        gr.update(visible=...) not raw bools."""
        # 11 pref values + 3 mp3 visibility bools
        values = ("mp3", "128k", 48000, 0.5, True, -1.0, 0.0, 0.0, 0.0, 1.0, 8, True, True, True)
        result = restore_preferences(*values)
        # mp3_controls_row (index 11): visible only
        row_update = result[11]
        self.assertIsInstance(row_update, dict)
        self.assertTrue(row_update["visible"])
        self.assertNotIn("interactive", row_update)
        # mp3_bitrate (index 12): visible + interactive
        bitrate_update = result[12]
        self.assertIsInstance(bitrate_update, dict)
        self.assertTrue(bitrate_update["visible"])
        self.assertTrue(bitrate_update["interactive"])
        # mp3_sample_rate (index 13): visible + interactive
        sr_update = result[13]
        self.assertIsInstance(sr_update, dict)
        self.assertTrue(sr_update["visible"])
        self.assertTrue(sr_update["interactive"])

    def test_restore_preferences_empty_values_returns_noop_updates(self):
        """When called with no values (JS did not forward args), the function
        should return ``_num_outputs`` gr.update() no-ops instead of crashing."""
        result = restore_preferences(_num_outputs=_NUM_OUTPUTS)
        self.assertEqual(len(result), _NUM_OUTPUTS)
        for v in result:
            self.assertIsInstance(v, dict)
            self.assertEqual(v["__type__"], "update")

    def test_restore_preferences_empty_values_no_num_outputs(self):
        """With no values and no _num_outputs hint, return empty tuple."""
        result = restore_preferences()
        self.assertEqual(len(result), 0)

    def test_pref_keys_match_defaults(self):
        """Every PREF_KEY must have a corresponding default."""
        for key in PREF_KEYS:
            self.assertIn(key, _DEFAULTS, f"Key {key!r} missing from _DEFAULTS")

    def test_restore_js_generation_is_stable(self):
        js_1 = _build_restore_js(_NUM_OUTPUTS)
        js_2 = _build_restore_js(_NUM_OUTPUTS)
        self.assertEqual(js_1, js_2)


if __name__ == "__main__":
    unittest.main()
