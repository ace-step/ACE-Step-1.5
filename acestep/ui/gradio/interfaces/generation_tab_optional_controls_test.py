"""Contract tests for generation optional-parameter controls."""

import ast
from pathlib import Path
import unittest


_OPTIONAL_PATH = Path(__file__).resolve().parent / "generation_tab_optional_controls.py"
_EXPECTED_NAMES = {
    "bpm",
    "key_scale",
    "time_signature",
    "vocal_language",
    "audio_duration",
}


class GenerationTabOptionalControlsTests(unittest.TestCase):
    """Verify optional controls start locked when Auto toggles are enabled."""

    def test_optional_fields_default_to_non_interactive(self):
        """Optional controls should initialize with ``interactive=False``."""

        module = ast.parse(_OPTIONAL_PATH.read_text(encoding="utf-8"))
        func = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "build_optional_parameter_controls"
        )

        found: dict[str, ast.AST] = {}
        for node in ast.walk(func):
            if not isinstance(node, ast.Assign):
                continue
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            target_name = node.targets[0].id
            if target_name not in _EXPECTED_NAMES:
                continue
            if not isinstance(node.value, ast.Call):
                continue
            interactive_kw = next((kw for kw in node.value.keywords if kw.arg == "interactive"), None)
            if interactive_kw is not None:
                found[target_name] = interactive_kw.value

        self.assertEqual(_EXPECTED_NAMES, set(found.keys()))
        for field_name, expr in found.items():
            self.assertIsInstance(expr, ast.Constant, f"{field_name} should use constant False")
            self.assertFalse(expr.value, f"{field_name} should default to non-interactive")


if __name__ == "__main__":
    unittest.main()
