"""Training-focused decomposition contract tests."""

import ast
import unittest

try:
    from .decomposition_contract_helpers import (
        call_name,
        load_setup_training_event_handlers_node,
        load_training_dataset_builder_wiring_module,
        load_training_dataset_preprocess_wiring_module,
        load_training_lokr_wiring_module,
        load_training_run_wiring_module,
    )
except ImportError:  # pragma: no cover - supports direct file execution
    from decomposition_contract_helpers import (
        call_name,
        load_setup_training_event_handlers_node,
        load_training_dataset_builder_wiring_module,
        load_training_dataset_preprocess_wiring_module,
        load_training_lokr_wiring_module,
        load_training_run_wiring_module,
    )


class DecompositionContractTrainingTests(unittest.TestCase):
    """Verify training-side delegation contracts for event wiring extraction."""

    def test_setup_training_event_handlers_uses_training_run_wiring_helper(self):
        """setup_training_event_handlers should delegate run-tab wiring registration."""

        setup_node = load_setup_training_event_handlers_node()
        call_names = []
        for node in ast.walk(setup_node):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)

        self.assertIn("register_training_run_handlers", call_names)
        self.assertIn("register_training_dataset_builder_handlers", call_names)
        self.assertIn("register_training_dataset_load_handler", call_names)
        self.assertIn("register_training_preprocess_handler", call_names)

    def test_training_run_wiring_calls_expected_training_handlers(self):
        """Training run wiring should invoke both LoRA and LoKr training entry points."""

        training_run_node = load_training_run_wiring_module()
        lokr_node = load_training_lokr_wiring_module()

        training_run_call_names = []
        for node in ast.walk(training_run_node):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    training_run_call_names.append(name)

        lokr_call_names = []
        lokr_attribute_names = []
        for node in ast.walk(lokr_node):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    lokr_call_names.append(name)
            if isinstance(node, ast.Attribute):
                lokr_attribute_names.append(node.attr)

        self.assertIn("start_training", training_run_call_names)
        self.assertIn("register_lokr_training_handlers", training_run_call_names)
        self.assertIn("start_lokr_training", lokr_call_names)
        self.assertIn("stop_training", lokr_attribute_names)

    def test_training_dataset_builder_wiring_calls_expected_handlers(self):
        """Dataset-builder wiring should call scan/label/edit/settings/save handlers."""

        wiring_node = load_training_dataset_builder_wiring_module()
        call_names = []
        attribute_names = []
        for node in ast.walk(wiring_node):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)
            if isinstance(node, ast.Attribute):
                attribute_names.append(node.attr)

        self.assertIn("scan_directory", call_names)
        self.assertIn("auto_label_all", call_names)
        self.assertIn("save_sample_edit", attribute_names)
        self.assertIn("update_settings", attribute_names)
        self.assertIn("save_dataset", attribute_names)

    def test_training_dataset_preprocess_wiring_calls_expected_handlers(self):
        """Dataset/preprocess wiring should call existing training handler entry points."""

        wiring_node = load_training_dataset_preprocess_wiring_module()
        call_names = []
        attribute_names = []
        for node in ast.walk(wiring_node):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)
            if isinstance(node, ast.Attribute):
                attribute_names.append(node.attr)

        self.assertIn("load_existing_dataset_for_preprocess", attribute_names)
        self.assertIn("preprocess_dataset", call_names)


if __name__ == "__main__":
    unittest.main()
