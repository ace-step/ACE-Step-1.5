"""Docstring coverage tests for decomposed event-wiring modules."""

import ast
from pathlib import Path
import unittest


_MODULE_PATHS = [
    Path(__file__).resolve().parents[1] / "__init__.py",
    Path(__file__).resolve().with_name("generation_metadata_file_wiring.py"),
    Path(__file__).resolve().with_name("results_display_wiring.py"),
    Path(__file__).resolve().with_name("training_dataset_builder_wiring.py"),
    Path(__file__).resolve().with_name("training_dataset_preprocess_wiring.py"),
    Path(__file__).resolve().with_name("training_run_wiring.py"),
    Path(__file__).resolve().with_name("training_lokr_wiring.py"),
]


def _collect_nodes_missing_docstrings(module: ast.Module) -> list[str]:
    """Return qualified names for functions/classes missing docstrings."""

    missing: list[str] = []

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                if ast.get_docstring(child) is None:
                    missing.append(name)
                visit(child, f"{name}.")
            else:
                visit(child, prefix)

    visit(module)
    return missing


class DocstringCoverageTests(unittest.TestCase):
    """Ensure decomposed event-wiring modules keep full docstring coverage."""

    def test_module_and_symbol_docstrings_are_present(self):
        """Each target module and all nested defs/classes should have docstrings."""

        failures: list[str] = []
        for module_path in _MODULE_PATHS:
            source = module_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            try:
                module_name = str(module_path.relative_to(Path.cwd()))
            except ValueError:
                module_name = module_path.name
            if ast.get_docstring(tree) is None:
                failures.append(f"{module_name}: <module>")
            for symbol in _collect_nodes_missing_docstrings(tree):
                failures.append(f"{module_name}: {symbol}")

        self.assertEqual(failures, [], f"Missing docstrings: {failures}")


if __name__ == "__main__":
    unittest.main()
