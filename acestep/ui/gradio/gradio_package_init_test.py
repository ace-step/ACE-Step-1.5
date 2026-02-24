"""Tests for lazy-import behavior in the Gradio package facade."""

import importlib
import unittest


class GradioPackageInitTests(unittest.TestCase):
    """Verify `acestep.ui.gradio` imports without requiring Gradio at import time."""

    def test_package_import_exposes_interface_factory_without_gradio_dependency(self):
        """Importing package should succeed and expose the create facade callable."""
        module = importlib.import_module("acestep.ui.gradio")
        self.assertTrue(callable(module.create_gradio_interface))


if __name__ == "__main__":
    unittest.main()
