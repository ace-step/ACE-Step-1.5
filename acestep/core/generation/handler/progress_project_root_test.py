"""Unit tests for ProgressMixin._get_project_root path resolution."""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_progress_mixin():
    """Load ProgressMixin directly without importing the full handler package."""
    spec = importlib.util.spec_from_file_location(
        "progress",
        os.path.join(os.path.dirname(__file__), "progress.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ProgressMixin


class TestProgressMixinGetProjectRoot(unittest.TestCase):
    """Tests for ProgressMixin._get_project_root()."""

    def _make_host(self):
        ProgressMixin = _load_progress_mixin()

        class Host(ProgressMixin):
            def __init__(self):
                self._last_diffusion_per_step_sec = None
                self._progress_estimates_lock = __import__("threading").Lock()
                self._progress_estimates = {"records": []}
                self._progress_estimates_path = os.path.join(
                    tempfile.gettempdir(), "test_progress_estimates.json"
                )

        return Host()

    def test_returns_cwd_by_default(self):
        """_get_project_root returns the current working directory when no env var is set."""
        host = self._make_host()
        env = {k: v for k, v in os.environ.items() if k != "ACESTEP_PROJECT_ROOT"}
        with patch.dict(os.environ, env, clear=True):
            result = host._get_project_root()
        self.assertEqual(result, os.getcwd())

    def test_returns_env_var_when_set(self):
        """_get_project_root returns the ACESTEP_PROJECT_ROOT env var path when set."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            host = self._make_host()
            with patch.dict(os.environ, {"ACESTEP_PROJECT_ROOT": tmp_dir}):
                result = host._get_project_root()
            self.assertEqual(result, os.path.abspath(tmp_dir))

    def test_env_var_takes_precedence_over_cwd(self):
        """ACESTEP_PROJECT_ROOT overrides the current working directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            host = self._make_host()
            with patch.dict(os.environ, {"ACESTEP_PROJECT_ROOT": tmp_dir}):
                result = host._get_project_root()
            self.assertNotEqual(result, os.getcwd())
            self.assertEqual(result, os.path.abspath(tmp_dir))

    def test_does_not_use_file_location(self):
        """_get_project_root must not return a path derived from __file__ (site-packages fix)."""
        host = self._make_host()
        env = {k: v for k, v in os.environ.items() if k != "ACESTEP_PROJECT_ROOT"}
        with patch.dict(os.environ, env, clear=True):
            result = host._get_project_root()
        # The result must equal os.getcwd(), not the directory of progress.py
        progress_file_dir = os.path.dirname(os.path.abspath(__file__))
        self.assertNotEqual(result, progress_file_dir)
        self.assertEqual(result, os.getcwd())


if __name__ == "__main__":
    unittest.main()
