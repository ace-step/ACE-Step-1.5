"""Guard that every literal i18n key used by the UI exists in ``en.json``.

``t()`` silently returns the key itself when it cannot resolve a
translation, so a key that is used in code but missing from the English
catalog surfaces to the user as a raw identifier such as
``messages.no_source_audio``.  English is also the fallback for every
other language, so a gap there is visible in every locale.

This test parses the UI modules instead of importing them: it stays fast
and does not need Gradio or a display.
"""

import ast
import json
import unittest
from pathlib import Path

_UI_ROOT = Path(__file__).resolve().parents[2]
_EN_CATALOG = Path(__file__).with_name("en.json")

# Directories scanned for ``t("...")`` call sites.
_SCAN_ROOTS = (_UI_ROOT / "gradio",)
# Modules that must not be scanned: test code, and this package's own loader.
_SKIP_DIR_NAMES = {"i18n", "__pycache__"}


def _flatten_keys(node, prefix=""):
    """Yield every leaf key of a nested catalog as a dot-separated path."""
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten_keys(value, path)
        else:
            yield path


def _iter_python_files(root: Path):
    """Yield Python modules under *root*, skipping tests and the i18n package."""
    for path in sorted(root.rglob("*.py")):
        if _SKIP_DIR_NAMES & set(path.relative_to(root).parts):
            continue
        name = path.name
        if name.startswith("test_") or name.endswith("_test.py"):
            continue
        yield path


def _literal_i18n_keys(path: Path):
    """Yield ``(lineno, key)`` for literal ``t("...")`` calls in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "t":
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            yield node.lineno, first.value


class I18nKeyCoverageTests(unittest.TestCase):
    """Ensure the English catalog defines every key the UI asks for."""

    @classmethod
    def setUpClass(cls):
        """Load the English catalog once for all assertions."""
        cls.catalog = set(_flatten_keys(json.loads(_EN_CATALOG.read_text(encoding="utf-8"))))

    def test_catalog_is_non_empty(self):
        """Sanity check that the catalog parsed into a usable key set."""
        self.assertGreater(len(self.catalog), 100)

    def test_every_literal_ui_key_resolves(self):
        """Every literal ``t("...")`` key must exist in ``en.json``.

        A missing key makes ``t()`` return the key text, so the user sees
        e.g. ``messages.no_source_audio`` in a toast instead of a message.
        """
        missing = []
        for root in _SCAN_ROOTS:
            for path in _iter_python_files(root):
                for lineno, key in _literal_i18n_keys(path):
                    if key not in self.catalog:
                        missing.append(f"{path.relative_to(_UI_ROOT.parent)}:{lineno} -> {key}")

        self.assertEqual(
            missing,
            [],
            "UI code references i18n keys that are absent from en.json "
            "(t() would return the raw key to the user):\n  " + "\n  ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
