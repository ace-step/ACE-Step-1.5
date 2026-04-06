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

    def test_external_script_contains_mapping_logic(self):
        script_asset = _load_preferences_script()
        self.assertIn("dataset.maps", script_asset)
        self.assertIn("JSON.parse", script_asset)

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


_NUM_OUTPUTS = len(PREF_KEYS)


class RestoreTests(unittest.TestCase):
    """Tests for the Gradio-native restore mechanism."""

    def test_restore_js_returns_valid_javascript(self):
        js = _build_restore_js()
        self.assertIn("localStorage", js)
        self.assertIn("SCHEMA_VERSION", js)
        self.assertIn("acestep.ui.user_preferences", js)

    def test_restore_js_includes_all_pref_keys(self):
        js = _build_restore_js()
        for key in PREF_KEYS:
            self.assertIn(f'"{key}"', js, f"Missing key in restore JS: {key}")

    def test_restore_js_only_resets_on_downgrade(self):
        """Version check should only discard prefs from future (higher) versions."""
        js = _build_restore_js()
        self.assertIn("_version", js)
        self.assertIn("prefs._version > SCHEMA_VERSION", js)
        self.assertNotIn("prefs._version !== SCHEMA_VERSION", js)

    def test_restore_js_coerces_numeric_dropdown_values(self):
        """Dropdown values stored as strings in localStorage must be coerced
        back to numbers when the Gradio component expects integers."""
        js = _build_restore_js()
        self.assertIn("NUMERIC_COERCE_KEYS", js)
        self.assertIn("Number(v)", js)

    def test_restore_js_validates_value_types(self):
        """Restore JS must include per-key type validation."""
        js = _build_restore_js()
        self.assertIn("TYPE_MAP", js)
        self.assertIn("typeof v !== expected", js)

    def test_restore_js_returns_null_sentinel_when_no_stored_prefs(self):
        """When localStorage is empty the JS must return nulls so the Python
        side can skip updates and preserve init_params."""
        js = _build_restore_js()
        self.assertIn("SKIP", js)
        self.assertIn("[null]", js)
        # Should NOT contain DEFAULTS as a fallback for empty storage.
        self.assertNotIn("DEFAULTS", js)

    def test_restore_js_returns_json_string(self):
        """Restore JS should return a JSON string."""
        js = _build_restore_js()
        self.assertIn("JSON.stringify", js)

    def test_restore_preferences_with_values(self):
        """Values arrive as a JSON string from the dummy Textbox."""
        data = ["flac", "192k", 44100, 0.7, False, -2.0, 0.5, 0.5, 0.1, 1.1, 4]
        result = restore_preferences(json.dumps(data), _num_outputs=len(PREF_KEYS))
        self.assertEqual(result[0], "flac")
        self.assertEqual(result[3], 0.7)

    def test_restore_preferences_empty(self):
        result = restore_preferences(_num_outputs=len(PREF_KEYS))
        self.assertEqual(len(result), len(PREF_KEYS))
        for v in result:
            self.assertIsInstance(v, dict)
            self.assertEqual(v["__type__"], "update")
        # all should be gr.update()

    def test_restore_preferences_null_string(self):
        """Null input → noop."""
        result = restore_preferences(None, _num_outputs=len(PREF_KEYS))
        self.assertEqual(len(result), len(PREF_KEYS))

    def test_restore_preferences_partial_nulls(self):
        data = ["opus", None, None, 0.5, True, -1.0, 0.0, 0.0, 0.0, 1.0, 8]
        result = restore_preferences(json.dumps(data), _num_outputs=len(PREF_KEYS))
        self.assertEqual(result[0], "opus")
        self.assertIsInstance(result[1], dict)
        self.assertEqual(result[1]["__type__"], "update")
        self.assertIsInstance(result[2], dict)
        self.assertEqual(result[2]["__type__"], "update")
        self.assertEqual(result[3], 0.5)
        # indices 1, 2 should be gr.update()

    def test_restore_preferences_all_nulls(self):
        data = [None] * len(PREF_KEYS)
        result = restore_preferences(json.dumps(data), _num_outputs=len(PREF_KEYS))
        self.assertEqual(len(result), len(PREF_KEYS))
        for v in result:
            self.assertIsInstance(v, dict)
            self.assertEqual(v["__type__"], "update")

    def test_build_restore_js_has_dummy_param(self):
        js = _build_restore_js()
        self.assertTrue(js.strip().startswith("(_dummy)"))

    def test_build_restore_js_returns_json_string(self):
        js = _build_restore_js()
        self.assertIn("JSON.stringify", js)

    def test_build_restore_js_skip_sentinel(self):
        js = _build_restore_js()
        self.assertIn("[null]", js)
        self.assertNotIn("fill(null)", js)

    def test_restore_preferences_invalid_json(self):
        """Garbage string → noop."""
        result = restore_preferences("not-json{}", _num_outputs=len(PREF_KEYS))
        self.assertEqual(len(result), len(PREF_KEYS))

    def test_pref_keys_match_defaults(self):
        """Every PREF_KEY must have a corresponding default."""
        for key in PREF_KEYS:
            self.assertIn(key, _DEFAULTS, f"Key {key!r} missing from _DEFAULTS")

    def test_restore_js_generation_is_stable(self):
        js_1 = _build_restore_js()
        js_2 = _build_restore_js()
        self.assertEqual(js_1, js_2)


if __name__ == "__main__":
    unittest.main()
