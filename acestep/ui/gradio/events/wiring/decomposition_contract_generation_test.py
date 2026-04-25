"""Generation-focused decomposition contract tests."""

import ast
import unittest

try:
    from .decomposition_contract_helpers import (
        call_name,
        load_generation_batch_navigation_wiring_node,
        load_generation_metadata_file_wiring_module,
        load_generation_mode_wiring_node,
        load_generation_run_wiring_node,
        load_results_display_wiring_module,
        load_setup_event_handlers_node,
    )
except ImportError:  # pragma: no cover - supports direct file execution
    from decomposition_contract_helpers import (
        call_name,
        load_generation_batch_navigation_wiring_node,
        load_generation_metadata_file_wiring_module,
        load_generation_mode_wiring_node,
        load_generation_run_wiring_node,
        load_results_display_wiring_module,
        load_setup_event_handlers_node,
    )


def _is_generation_mode_change_call(node: ast.AST) -> bool:
    """Return whether ``node`` is the generation-mode component change call."""

    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "change":
        return False
    subscript = node.func.value
    return (
        isinstance(subscript, ast.Subscript)
        and isinstance(subscript.value, ast.Name)
        and subscript.value.id == "generation_section"
        and isinstance(subscript.slice, ast.Constant)
        and subscript.slice.value == "generation_mode"
    )


def _call_uses_keyword_function(node: ast.Call, function_name: str) -> bool:
    """Return whether a call passes ``function_name`` as its ``fn=`` keyword."""

    return any(k.arg == "fn" and call_name(k.value) == function_name for k in node.keywords)


def _event_chain_root(node: ast.AST) -> ast.AST:
    """Return the originating event for chained ``.then()`` calls."""

    while isinstance(node, ast.Call) and call_name(node.func) == "then":
        node = node.func.value
    return node


class DecompositionContractGenerationTests(unittest.TestCase):
    """Verify generation-side delegation contracts for event wiring extraction."""

    def test_setup_event_handlers_uses_generation_wiring_helpers(self):
        """setup_event_handlers should delegate generation wiring registration."""

        setup_node = load_setup_event_handlers_node()
        call_names = []
        for node in ast.walk(setup_node):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)

        self.assertIn("register_generation_service_handlers", call_names)
        self.assertIn("register_generation_batch_navigation_handlers", call_names)
        self.assertIn("register_generation_metadata_file_handlers", call_names)
        self.assertIn("register_generation_metadata_handlers", call_names)
        self.assertIn("register_generation_mode_handlers", call_names)
        self.assertIn("register_generation_run_handlers", call_names)
        self.assertIn("register_results_aux_handlers", call_names)
        self.assertIn("register_results_save_button_handlers", call_names)
        self.assertIn("register_results_restore_and_lrc_handlers", call_names)
        self.assertIn("build_mode_ui_outputs", call_names)

    def test_generation_metadata_file_wiring_calls_expected_handlers(self):
        """Metadata file wiring should call load-metadata and auto-uncheck handlers."""

        wiring_node = load_generation_metadata_file_wiring_module()
        attribute_names = []
        for node in ast.walk(wiring_node):
            if isinstance(node, ast.Attribute):
                attribute_names.append(node.attr)

        self.assertIn("load_metadata", attribute_names)
        self.assertIn("uncheck_auto_for_populated_fields", attribute_names)

    def test_generation_mode_wiring_uses_mode_ui_outputs_variable(self):
        """Mode wiring helper should bind generation_mode outputs to mode_ui_outputs."""

        wiring_node = load_generation_mode_wiring_node()
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

    def test_generation_mode_change_does_not_reset_dcw_defaults(self):
        """Mode switches should not overwrite manually tuned DCW controls."""

        wiring_node = load_generation_mode_wiring_node()
        mode_change_event_names = set()

        for node in ast.walk(wiring_node):
            if not isinstance(node, ast.Assign):
                continue
            event_root = _event_chain_root(node.value)
            if _is_generation_mode_change_call(event_root) or (
                isinstance(event_root, ast.Name) and event_root.id in mode_change_event_names
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        mode_change_event_names.add(target.id)

        for node in ast.walk(wiring_node):
            if not isinstance(node, ast.Call):
                continue
            if call_name(node.func) != "then":
                continue
            if not _call_uses_keyword_function(node, "update_dcw_defaults_for_think"):
                continue
            event_source = _event_chain_root(node.func.value)
            if _is_generation_mode_change_call(event_source):
                self.fail("generation_mode.change must not chain DCW default updates")
            if isinstance(event_source, ast.Name) and event_source.id in mode_change_event_names:
                self.fail("generation_mode.change must not chain DCW default updates")

    def test_generation_run_wiring_calls_expected_results_handlers(self):
        """Run wiring should call clear, generate stream, and background pre-generation helpers."""

        wiring_node = load_generation_run_wiring_node()
        call_names = []
        attribute_names = []
        for node in ast.walk(wiring_node):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)
            if isinstance(node, ast.Attribute):
                attribute_names.append(node.attr)

        self.assertIn("clear_audio_outputs_for_new_generation", attribute_names)
        self.assertIn("generate_with_batch_management", call_names)
        self.assertIn("generate_next_batch_background", call_names)

    def test_batch_navigation_wiring_calls_expected_results_handlers(self):
        """Batch navigation wiring should call previous/next/background results helpers."""

        wiring_node = load_generation_batch_navigation_wiring_node()
        call_names = []
        attribute_names = []
        for node in ast.walk(wiring_node):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)
            if isinstance(node, ast.Attribute):
                attribute_names.append(node.attr)

        self.assertIn("navigate_to_previous_batch", attribute_names)
        self.assertIn("capture_current_params", attribute_names)
        self.assertIn("navigate_to_next_batch", attribute_names)
        self.assertIn("generate_next_batch_background", call_names)

    def test_results_display_wiring_calls_expected_results_handlers(self):
        """Results display wiring should call restore and LRC subtitle handlers."""

        wiring_node = load_results_display_wiring_module()
        attribute_names = []
        for node in ast.walk(wiring_node):
            if isinstance(node, ast.Attribute):
                attribute_names.append(node.attr)

        self.assertIn("restore_batch_parameters", attribute_names)
        self.assertIn("update_audio_subtitles_from_lrc", attribute_names)


if __name__ == "__main__":
    unittest.main()
