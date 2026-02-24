"""Contract tests for generation service-config row builders."""

import ast
from pathlib import Path
import unittest


_ROWS_PATH = Path(__file__).resolve().parent / "generation_service_config_rows.py"


class GenerationServiceConfigRowsTests(unittest.TestCase):
    """Verify service row builder contracts needed by the UI wiring."""

    def test_language_dropdown_is_explicitly_interactive(self):
        """Language selector should remain interactive for runtime language selection."""

        module = ast.parse(_ROWS_PATH.read_text(encoding="utf-8"))
        func = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "build_language_selector"
        )

        dropdown_calls = [
            node
            for node in ast.walk(func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "Dropdown"
        ]
        self.assertTrue(dropdown_calls, "Expected a gr.Dropdown call in build_language_selector")

        interactive_kw = next(
            (
                kw
                for kw in dropdown_calls[0].keywords
                if kw.arg == "interactive"
            ),
            None,
        )
        self.assertIsNotNone(interactive_kw, "language_dropdown should set interactive explicitly")
        self.assertIsInstance(interactive_kw.value, ast.Constant)
        self.assertTrue(interactive_kw.value.value)


if __name__ == "__main__":
    unittest.main()
