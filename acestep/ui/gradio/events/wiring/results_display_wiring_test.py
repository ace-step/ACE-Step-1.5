"""Unit tests for results display wiring contracts."""

import ast
from pathlib import Path
import unittest

try:
    from .ast_test_utils import load_module_ast, subscript_key
except ImportError:  # pragma: no cover - supports direct file execution
    from ast_test_utils import load_module_ast, subscript_key


_WIRING_PATH = Path(__file__).with_name("results_display_wiring.py")

_EXPECTED_RESTORE_OUTPUT_KEYS = [
    "text2music_audio_code_string",
    "captions",
    "lyrics",
    "bpm",
    "key_scale",
    "time_signature",
    "vocal_language",
    "audio_duration",
    "batch_size_input",
    "inference_steps",
    "lm_temperature",
    "lm_cfg_scale",
    "lm_top_k",
    "lm_top_p",
    "think_checkbox",
    "use_cot_caption",
    "use_cot_language",
    "allow_lm_batch",
    "track_name",
    "complete_track_classes",
    "enable_normalization",
    "normalization_db",
    "latent_shift",
    "latent_rescale",
]

_EXPECTED_JS_MARKERS = [
    "[Debug] Current Audio Input:",
    "Warning: No audio selected or audio is empty.",
    "Warning: Batch file list is empty/not ready.",
    "Error: Could not extract a valid path string from input.",
    "Key extracted:",
    "Warning: No matching files found in batch list for key:",
    "Found ${targets.length} files to download.",
]

_FORBIDDEN_MOJIBAKE_MARKERS = ["Ã", "ðŸ", "âš", "â"]

class ResultsDisplayWiringTests(unittest.TestCase):
    """Verify save/download JS and restore/LRC wiring ordering contracts."""

    def test_download_js_contains_expected_ascii_messages(self):
        """Download JS should contain expected ASCII diagnostics and no mojibake markers."""

        module = load_module_ast(_WIRING_PATH)
        js_literal = None
        for node in module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "_DOWNLOAD_EXISTING_JS":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            js_literal = node.value.value
                            break
            if js_literal is not None:
                break
        self.assertIsNotNone(js_literal, "_DOWNLOAD_EXISTING_JS not found")
        for marker in _EXPECTED_JS_MARKERS:
            self.assertIn(marker, js_literal)
        for marker in _FORBIDDEN_MOJIBAKE_MARKERS:
            self.assertNotIn(marker, js_literal)

    def test_restore_outputs_keep_expected_order(self):
        """Restore params click outputs should keep existing generation field ordering."""

        module = load_module_ast(_WIRING_PATH)
        for node in module.body:
            if not isinstance(node, ast.FunctionDef) or node.name != "register_results_restore_and_lrc_handlers":
                continue
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                if not isinstance(call.func, ast.Attribute) or call.func.attr != "click":
                    continue
                for keyword in call.keywords:
                    if keyword.arg != "outputs" or not isinstance(keyword.value, ast.List):
                        continue
                    keys = []
                    for element in keyword.value.elts:
                        if isinstance(element, ast.Subscript):
                            key = subscript_key(element)
                            if key is not None:
                                keys.append(key)
                    if keys == _EXPECTED_RESTORE_OUTPUT_KEYS:
                        return
        self.fail("restore_params_btn outputs contract not found")

    def test_save_and_lrc_handlers_cover_all_8_result_slots(self):
        """Both save-btn and lrc-display loops should iterate over slots 1..8."""

        module = load_module_ast(_WIRING_PATH)
        range_calls = []
        for node in ast.walk(module):
            if isinstance(node, ast.For) and isinstance(node.iter, ast.Call):
                call = node.iter
                if isinstance(call.func, ast.Name) and call.func.id == "range":
                    args = []
                    for arg in call.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                            args.append(arg.value)
                    if args:
                        range_calls.append(tuple(args))

        self.assertIn((1, 9), range_calls)
        self.assertGreaterEqual(range_calls.count((1, 9)), 2)


if __name__ == "__main__":
    unittest.main()
