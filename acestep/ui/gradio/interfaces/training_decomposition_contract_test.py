"""AST contract tests for training interface decomposition."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

try:
    from .training_contract_ast_utils import (
        call_name,
        collect_return_dict_keys,
        collect_training_section_keys_used_by_wiring,
        load_module,
    )
except ImportError:
    from training_contract_ast_utils import (  # type: ignore[no-redef]
        call_name,
        collect_return_dict_keys,
        collect_training_section_keys_used_by_wiring,
        load_module,
    )


class TrainingDecompositionContractTests(unittest.TestCase):
    """Verify the training interface facade composes focused helper modules."""

    def test_training_facade_imports_tab_helpers(self) -> None:
        """``training.py`` should import dataset, LoRA, and LoKr helper modules."""

        module = load_module("training.py")
        imported_modules = []
        for node in ast.walk(module):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)

        self.assertIn(
            "acestep.ui.gradio.interfaces.training_dataset_builder_tab",
            imported_modules,
        )
        self.assertIn("acestep.ui.gradio.interfaces.training_lora_tab", imported_modules)
        self.assertIn("acestep.ui.gradio.interfaces.training_lokr_tab", imported_modules)

    def test_training_facade_merges_helper_sections(self) -> None:
        """``training.py`` should compose helper returns into one training-section map."""

        module = load_module("training.py")
        call_names: list[str] = []
        update_calls = 0
        for node in ast.walk(module):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node.func)
            if name:
                call_names.append(name)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "update":
                update_calls += 1

        self.assertIn("create_dataset_builder_tab", call_names)
        self.assertIn("create_training_lora_tab", call_names)
        self.assertIn("create_training_lokr_tab", call_names)
        self.assertGreaterEqual(update_calls, 4)

    def test_dataset_builder_tab_delegates_to_section_builders(self) -> None:
        """Dataset-builder facade should delegate to scan/label/preprocess builders."""

        module = load_module("training_dataset_builder_tab.py")
        call_names: list[str] = []
        for node in ast.walk(module):
            if isinstance(node, ast.Call):
                name = call_name(node.func)
                if name:
                    call_names.append(name)

        self.assertIn("build_dataset_scan_and_settings_controls", call_names)
        self.assertIn("build_dataset_label_and_preview_controls", call_names)
        self.assertIn("build_dataset_save_and_preprocess_controls", call_names)

    def test_training_keys_cover_wiring_requirements(self) -> None:
        """Returned training keys should cover all keys consumed by wiring modules."""

        produced_keys: set[str] = set()
        key_sources = [
            ("training.py", "create_training_section"),
            ("training_dataset_tab_scan_settings.py", "build_dataset_scan_and_settings_controls"),
            (
                "training_dataset_tab_label_preview.py",
                "build_dataset_label_and_preview_controls",
            ),
            (
                "training_dataset_tab_save_preprocess.py",
                "build_dataset_save_and_preprocess_controls",
            ),
            ("training_lora_tab_dataset.py", "build_lora_dataset_and_adapter_controls"),
            ("training_lora_tab_run_export.py", "build_lora_run_and_export_controls"),
            ("training_lokr_tab_dataset.py", "build_lokr_dataset_and_adapter_controls"),
            ("training_lokr_tab_run_export.py", "build_lokr_run_and_export_controls"),
        ]
        for module_name, function_name in key_sources:
            produced_keys |= collect_return_dict_keys(module_name, function_name)

        required_keys = collect_training_section_keys_used_by_wiring()
        self.assertTrue(
            required_keys.issubset(produced_keys),
            f"Missing training_section keys: {sorted(required_keys - produced_keys)}",
        )

    def test_training_ui_markers_preserved(self) -> None:
        """Key emoji UI markers should remain present after decomposition."""

        interfaces_dir = Path(__file__).resolve().parent
        expected_markers = {
            "training.py": ["🎵 LoRA Training for ACE-Step"],
            "training_dataset_tab_scan_settings.py": ["📂 Load Existing Dataset", "🔍 Scan New Directory"],
            "training_dataset_tab_label_preview.py": ["🤖", "👀"],
            "training_dataset_tab_save_preprocess.py": ["💾", "⚡"],
            "training_lora_tab_dataset.py": ["📊", "⚙️"],
            "training_lora_tab_run_export.py": ["🎛️", "📦"],
            "training_lokr_tab_run_export.py": ["🎛️", "📦"],
        }
        for module_name, markers in expected_markers.items():
            source = (interfaces_dir / module_name).read_text(encoding="utf-8")
            for marker in markers:
                self.assertIn(marker, source, f"Missing marker {marker!r} in {module_name}")

    def test_lokr_helpers_use_i18n_translation_calls(self) -> None:
        """LoKr modules should import and call ``t(...)`` for user-facing labels."""

        for module_name in (
            "training_lokr_tab.py",
            "training_lokr_tab_dataset.py",
            "training_lokr_tab_run_export.py",
        ):
            module = load_module(module_name)
            imported_i18n = False
            call_names: list[str] = []
            for node in ast.walk(module):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "acestep.ui.gradio.i18n"
                    and any(alias.name == "t" for alias in node.names)
                ):
                    imported_i18n = True
                if isinstance(node, ast.Call):
                    name = call_name(node.func)
                    if name:
                        call_names.append(name)

            self.assertTrue(imported_i18n, f"{module_name} does not import t from i18n")
            self.assertIn("t", call_names, f"{module_name} does not call t(...)")


if __name__ == "__main__":
    unittest.main()
