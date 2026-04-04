"""Contract tests for generation service wiring."""

import ast
from pathlib import Path
import unittest


_WIRING_PATH = Path(__file__).resolve().parent / "generation_service_wiring.py"


class GenerationServiceWiringTests(unittest.TestCase):
    """Verify key event hooks are present in generation service wiring."""

    def test_registers_language_dropdown_change_handler(self):
        """Service wiring should attach a change handler for language dropdown."""

        module = ast.parse(_WIRING_PATH.read_text(encoding="utf-8"))
        register_fn = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "register_generation_service_handlers"
        )

        found_language_change = False
        for node in ast.walk(register_fn):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "change":
                continue
            if not isinstance(node.func.value, ast.Subscript):
                continue
            target = node.func.value
            if (
                isinstance(target.value, ast.Name)
                and target.value.id == "generation_section"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "language_dropdown"
            ):
                found_language_change = True
                break

        self.assertTrue(found_language_change, "language_dropdown.change handler was not found")

    def test_language_runtime_helper_exists(self):
        """Runtime language helper should exist for dropdown change wiring."""

        module = ast.parse(_WIRING_PATH.read_text(encoding="utf-8"))
        function_names = {
            node.name for node in module.body if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("_apply_runtime_language", function_names)

    def test_registers_backend_dropdown_change_handler(self):
        """Service wiring should react to backend changes for external LM controls."""

        module = ast.parse(_WIRING_PATH.read_text(encoding="utf-8"))
        register_fn = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "register_generation_service_handlers"
        )

        found_backend_change = False
        for node in ast.walk(register_fn):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "change":
                continue
            if not isinstance(node.func.value, ast.Subscript):
                continue
            target = node.func.value
            if (
                isinstance(target.value, ast.Name)
                and target.value.id == "generation_section"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "backend_dropdown"
            ):
                found_backend_change = True
                break

        self.assertTrue(found_backend_change, "backend_dropdown.change handler was not found")

    def test_registers_external_lm_setup_actions(self):
        """Service wiring should include fetch/save/test/doctor handlers for external LM setup."""

        module = ast.parse(_WIRING_PATH.read_text(encoding="utf-8"))
        register_fn = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "register_generation_service_handlers"
        )

        click_targets = set()
        for node in ast.walk(register_fn):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "click":
                continue
            if not isinstance(node.func.value, ast.Subscript):
                continue
            target = node.func.value
            if (
                isinstance(target.value, ast.Name)
                and target.value.id == "generation_section"
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                click_targets.add(target.slice.value)

        self.assertTrue(
            {
                "external_llm_fetch_models_btn",
                "external_llm_save_btn",
                "external_llm_test_btn",
                "external_llm_doctor_btn",
            }.issubset(click_targets)
        )


if __name__ == "__main__":
    unittest.main()
