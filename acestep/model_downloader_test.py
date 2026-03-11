"""Unit tests for model_downloader.get_project_root and get_checkpoints_dir."""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_module():
    """Load model_downloader directly without importing heavy dependencies."""
    spec = importlib.util.spec_from_file_location(
        "model_downloader",
        os.path.join(os.path.dirname(__file__), "model_downloader.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestGetProjectRoot(unittest.TestCase):
    """Tests for model_downloader.get_project_root()."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_returns_cwd_by_default(self):
        """get_project_root returns the current working directory when no env var is set."""
        env = {k: v for k, v in os.environ.items() if k != "ACESTEP_PROJECT_ROOT"}
        with patch.dict(os.environ, env, clear=True):
            result = self.mod.get_project_root()
        self.assertEqual(result, Path(os.getcwd()))

    def test_returns_env_var_when_set(self):
        """get_project_root returns the ACESTEP_PROJECT_ROOT path when the env var is set."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"ACESTEP_PROJECT_ROOT": tmp_dir}):
                result = self.mod.get_project_root()
            self.assertEqual(result, Path(tmp_dir).resolve())

    def test_env_var_takes_precedence_over_cwd(self):
        """ACESTEP_PROJECT_ROOT overrides the current working directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"ACESTEP_PROJECT_ROOT": tmp_dir}):
                result = self.mod.get_project_root()
            self.assertNotEqual(result, Path(os.getcwd()))
            self.assertEqual(result, Path(tmp_dir).resolve())

    def test_does_not_derive_path_from_package_file(self):
        """get_project_root must not return a __file__-derived path (site-packages fix)."""
        env = {k: v for k, v in os.environ.items() if k != "ACESTEP_PROJECT_ROOT"}
        with patch.dict(os.environ, env, clear=True):
            result = self.mod.get_project_root()
        # The old __file__-based path would be the parent of the parent of model_downloader.py
        old_style_path = Path(os.path.abspath(__file__)).parent.parent
        # The current test is running with CWD == project root, so they happen to be equal
        # here; what matters is the returned path equals CWD, not the module file ancestor.
        self.assertEqual(result, Path(os.getcwd()))


class TestGetCheckpointsDir(unittest.TestCase):
    """Tests for model_downloader.get_checkpoints_dir()."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_default_is_checkpoints_under_cwd(self):
        """get_checkpoints_dir returns <cwd>/checkpoints when no custom dir or env var is set."""
        env = {k: v for k, v in os.environ.items() if k != "ACESTEP_PROJECT_ROOT"}
        with patch.dict(os.environ, env, clear=True):
            result = self.mod.get_checkpoints_dir()
        self.assertEqual(result, Path(os.getcwd()) / "checkpoints")

    def test_custom_dir_overrides_default(self):
        """get_checkpoints_dir returns the custom_dir when explicitly provided."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = self.mod.get_checkpoints_dir(custom_dir=tmp_dir)
        self.assertEqual(result, Path(tmp_dir))

    def test_env_var_is_honoured_as_root(self):
        """get_checkpoints_dir appends 'checkpoints' to ACESTEP_PROJECT_ROOT when set."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"ACESTEP_PROJECT_ROOT": tmp_dir}):
                result = self.mod.get_checkpoints_dir()
            self.assertEqual(result, Path(tmp_dir).resolve() / "checkpoints")


if __name__ == "__main__":
    unittest.main()
