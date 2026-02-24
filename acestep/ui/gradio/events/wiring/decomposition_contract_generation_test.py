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
