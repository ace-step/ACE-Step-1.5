"""AST contract tests for generation interface decomposition."""

import ast
import unittest

try:
    from .generation_contract_ast_utils import (
        call_name,
        collect_generation_section_keys_used_by_wiring,
        collect_return_dict_keys,
        load_module,
    )
except ImportError:
    from generation_contract_ast_utils import (  # type: ignore[no-redef]
        call_name,
        collect_generation_section_keys_used_by_wiring,
        collect_return_dict_keys,
        load_module,
    )


class GenerationDecompositionContractTests(unittest.TestCase):
    """Verify that generation interface facade delegates to focused helpers."""

    def test_generation_facade_imports(self):
        """`generation.py` should import advanced-settings, service, and tab helpers."""

        module = load_module("generation.py")
        imported_modules = []
        for node in ast.walk(module):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)

        self.assertIn("generation_advanced_settings", imported_modules)
        self.assertIn("generation_service_config", imported_modules)
        self.assertIn("generation_tab_section", imported_modules)

    def test_generation_facade_merges_sections(self):
        """`generation.py` should compose settings/tab sections into a merged map."""

        module = load_module("generation.py")
        call_names = []
        update_calls = 0
        for node in ast.walk(module):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node.func)
            if name:
                call_names.append(name)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "update":
                update_calls += 1

        self.assertIn("create_advanced_settings_section", call_names)
        self.assertIn("create_generation_tab_section", call_names)
        self.assertGreaterEqual(update_calls, 2)

    def test_generation_facade_exposes_required_public_symbols(self):
        """Facade should expose key constructors imported by interfaces package."""

        module = load_module("generation.py")
        names = set()
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                names.add(node.name)
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(alias.asname or alias.name)

        self.assertIn("create_advanced_settings_section", names)
        self.assertIn("create_generation_tab_section", names)
        self.assertIn("create_service_config_section", names)

    def test_advanced_settings_section_delegates_to_control_builders(self):
        """Advanced settings should compose service/lora/dit/lm/output helpers."""

        module = load_module("generation_advanced_settings.py")
        call_names = []
        for node in ast.walk(module):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)

        self.assertIn("create_service_config_content", call_names)
        self.assertIn("build_lora_controls", call_names)
        self.assertIn("build_dit_controls", call_names)
        self.assertIn("build_lm_controls", call_names)
        self.assertIn("build_output_controls", call_names)
        self.assertIn("build_automation_controls", call_names)

    def test_generation_tab_section_delegates_to_component_builders(self):
        """Generation tab should compose focused primary/secondary/runtime helpers."""

        module = load_module("generation_tab_section.py")
        call_names = []
        for node in ast.walk(module):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)

        self.assertIn("build_mode_selector_controls", call_names)
        self.assertIn("build_hidden_generation_state", call_names)
        self.assertIn("build_simple_mode_controls", call_names)
        self.assertIn("build_source_track_and_code_controls", call_names)
        self.assertIn("build_cover_strength_controls", call_names)
        self.assertIn("build_custom_mode_controls", call_names)
        self.assertIn("build_repainting_controls", call_names)
        self.assertIn("build_optional_parameter_controls", call_names)
        self.assertIn("build_generate_row_controls", call_names)

    def test_service_config_section_delegates_to_row_and_toggle_helpers(self):
        """Service config section should compose row/toggle helper builders."""

        module = load_module("generation_service_config.py")
        call_names = []
        for node in ast.walk(module):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)

        self.assertIn("build_language_selector", call_names)
        self.assertIn("build_gpu_info_and_tier", call_names)
        self.assertIn("build_checkpoint_controls", call_names)
        self.assertIn("build_model_device_controls", call_names)
        self.assertIn("build_lm_backend_controls", call_names)
        self.assertIn("build_service_toggles", call_names)
        self.assertIn("build_service_init_controls", call_names)

    def test_generation_keys_cover_all_wiring_generation_section_requirements(self):
        """Returned generation keys should cover all keys consumed by wiring modules."""

        produced_keys: set[str] = set()
        key_sources = [
            ("generation_tab_section.py", "create_generation_tab_section"),
            ("generation_advanced_settings.py", "create_advanced_settings_section"),
            ("generation_service_config.py", "create_service_config_content"),
            ("generation_tab_primary_controls.py", "build_mode_selector_controls"),
            ("generation_tab_primary_controls.py", "build_hidden_generation_state"),
            ("generation_tab_simple_controls.py", "build_simple_mode_controls"),
            ("generation_tab_source_controls.py", "build_source_track_and_code_controls"),
            ("generation_tab_secondary_controls.py", "build_cover_strength_controls"),
            ("generation_tab_secondary_controls.py", "build_custom_mode_controls"),
            ("generation_tab_secondary_controls.py", "build_repainting_controls"),
            ("generation_tab_optional_controls.py", "build_optional_parameter_controls"),
            ("generation_tab_generate_controls.py", "build_generate_row_controls"),
            ("generation_advanced_dit_controls.py", "build_dit_controls"),
            ("generation_advanced_primary_controls.py", "build_lm_controls"),
            ("generation_advanced_primary_controls.py", "build_lora_controls"),
            ("generation_advanced_output_controls.py", "build_output_controls"),
            ("generation_advanced_output_controls.py", "build_automation_controls"),
            ("generation_service_config_rows.py", "build_language_selector"),
            ("generation_service_config_rows.py", "build_gpu_info_and_tier"),
            ("generation_service_config_rows.py", "build_checkpoint_controls"),
            ("generation_service_config_rows.py", "build_model_device_controls"),
            ("generation_service_config_rows.py", "build_lm_backend_controls"),
            ("generation_service_config_toggles.py", "build_service_toggles"),
            ("generation_service_config_toggles.py", "build_service_init_controls"),
        ]
        for module_name, function_name in key_sources:
            produced_keys |= collect_return_dict_keys(module_name, function_name)
        produced_keys.discard("device_value")

        required_keys = collect_generation_section_keys_used_by_wiring()
        self.assertTrue(
            required_keys.issubset(produced_keys),
            f"Missing generation_section keys: {sorted(required_keys - produced_keys)}",
        )


if __name__ == "__main__":
    unittest.main()
