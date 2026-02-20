"""Regression tests for event wiring decomposition contracts.

These tests validate source-level delegation in
``acestep.ui.gradio.events.__init__`` without importing Gradio dependencies.
"""

import ast
from pathlib import Path
import unittest


_EVENTS_INIT_PATH = Path(__file__).resolve().parents[1] / "__init__.py"
_MODE_WIRING_PATH = Path(__file__).resolve().with_name("generation_mode_wiring.py")


def _load_setup_event_handlers_node() -> ast.FunctionDef:
    """Return the AST node for ``setup_event_handlers``."""

    source = _EVENTS_INIT_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "setup_event_handlers":
            return node
    raise AssertionError("setup_event_handlers not found")


def _load_generation_mode_wiring_node() -> ast.FunctionDef:
    """Return the AST node for ``register_generation_mode_handlers``."""

    source = _MODE_WIRING_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "register_generation_mode_handlers":
            return node
    raise AssertionError("register_generation_mode_handlers not found")


def _call_name(node: ast.AST) -> str | None:
    """Extract a simple function name from a call node target."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class DecompositionContractTests(unittest.TestCase):
    """Verify delegation contracts introduced in PR2/PR3/PR4 extraction."""

    def test_setup_event_handlers_uses_generation_wiring_helpers(self):
        """setup_event_handlers should delegate service/metadata/mode/results registration."""

        setup_node = _load_setup_event_handlers_node()
        call_names = []
        for node in ast.walk(setup_node):
            if isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name:
                    call_names.append(name)

        self.assertIn("register_generation_service_handlers", call_names)
        self.assertIn("register_generation_metadata_handlers", call_names)
        self.assertIn("register_generation_mode_handlers", call_names)
        self.assertIn("register_results_aux_handlers", call_names)
        self.assertIn("build_mode_ui_outputs", call_names)

    def test_generation_mode_wiring_uses_mode_ui_outputs_variable(self):
        """Mode wiring helper should bind generation_mode outputs to mode_ui_outputs."""

        wiring_node = _load_generation_mode_wiring_node()
        found_mode_change_output_binding = False

        for node in ast.walk(wiring_node):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "change":
                continue
            for keyword in node.keywords:
                if keyword.arg != "outputs":
                    continue
                if isinstance(keyword.value, ast.Name) and keyword.value.id == "mode_ui_outputs":
                    found_mode_change_output_binding = True
                    break
            if found_mode_change_output_binding:
                break

        self.assertTrue(found_mode_change_output_binding)


if __name__ == "__main__":
    unittest.main()
