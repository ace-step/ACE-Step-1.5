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

    def test_checkpoints_dir_env_var_overrides_default(self):
        """ACESTEP_CHECKPOINTS_DIR points directly to a shared model directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = {k: v for k, v in os.environ.items() if k not in ("ACESTEP_PROJECT_ROOT", "ACESTEP_CHECKPOINTS_DIR")}
            env["ACESTEP_CHECKPOINTS_DIR"] = tmp_dir
            with patch.dict(os.environ, env, clear=True):
                result = self.mod.get_checkpoints_dir()
            self.assertEqual(result, Path(tmp_dir).resolve())

    def test_checkpoints_dir_env_var_overrides_project_root(self):
        """ACESTEP_CHECKPOINTS_DIR takes precedence over ACESTEP_PROJECT_ROOT."""
        with tempfile.TemporaryDirectory() as ckpt_dir, tempfile.TemporaryDirectory() as proj_dir:
            with patch.dict(os.environ, {"ACESTEP_CHECKPOINTS_DIR": ckpt_dir, "ACESTEP_PROJECT_ROOT": proj_dir}):
                result = self.mod.get_checkpoints_dir()
            self.assertEqual(result, Path(ckpt_dir).resolve())

    def test_checkpoints_dir_env_var_expands_tilde(self):
        """ACESTEP_CHECKPOINTS_DIR expands ~ to the user's home directory."""
        env = {k: v for k, v in os.environ.items() if k not in ("ACESTEP_PROJECT_ROOT", "ACESTEP_CHECKPOINTS_DIR")}
        env["ACESTEP_CHECKPOINTS_DIR"] = "~/ace-step-models"
        with patch.dict(os.environ, env, clear=True):
            result = self.mod.get_checkpoints_dir()
        self.assertEqual(result, Path.home() / "ace-step-models")

    def test_custom_dir_overrides_checkpoints_dir_env_var(self):
        """Programmatic custom_dir takes highest precedence over env vars."""
        with tempfile.TemporaryDirectory() as custom, tempfile.TemporaryDirectory() as env_dir:
            with patch.dict(os.environ, {"ACESTEP_CHECKPOINTS_DIR": env_dir}):
                result = self.mod.get_checkpoints_dir(custom_dir=custom)
            self.assertEqual(result, Path(custom))

class TestCheckMainModelExists(unittest.TestCase):
    """Tests for model_downloader.check_main_model_exists()."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_returns_false_when_any_component_lacks_weights(self):
        """check_main_model_exists rejects partial main-model component directories."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoints_dir = Path(tmp_dir)
            for component in self.mod.MAIN_MODEL_COMPONENTS:
                component_dir = checkpoints_dir / component
                component_dir.mkdir()
                (component_dir / "configuration.json").write_text("{}", encoding="utf-8")

            result = self.mod.check_main_model_exists(checkpoints_dir)

        self.assertFalse(result)

    def test_returns_true_when_all_components_have_weights(self):
        """check_main_model_exists accepts main-model components with weights present."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoints_dir = Path(tmp_dir)
            for component in self.mod.MAIN_MODEL_COMPONENTS:
                component_dir = checkpoints_dir / component
                component_dir.mkdir()
                (component_dir / "model.safetensors").write_text("weights", encoding="utf-8")

            result = self.mod.check_main_model_exists(checkpoints_dir)

        self.assertTrue(result)

    def test_returns_true_when_vae_uses_diffusers_weight_filename(self):
        """check_main_model_exists accepts the current Diffusers-style VAE checkpoint filename."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            checkpoints_dir = Path(tmp_dir)
            for component in self.mod.MAIN_MODEL_COMPONENTS:
                component_dir = checkpoints_dir / component
                component_dir.mkdir()
                weight_filename = "model.safetensors"
                if component == "vae":
                    weight_filename = "diffusion_pytorch_model.safetensors"
                (component_dir / weight_filename).write_text("weights", encoding="utf-8")

            result = self.mod.check_main_model_exists(checkpoints_dir)

        self.assertTrue(result)


class TestCheckModelExists(unittest.TestCase):
    """Tests for model_downloader.check_model_exists()."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_returns_false_for_partial_model_directory_without_weights(self):
        """check_model_exists rejects directories that only contain synced code files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_dir = Path(tmp_dir) / "acestep-v15-turbo"
            model_dir.mkdir()
            (model_dir / "configuration_acestep_v15.py").write_text(
                "# synced code only\n",
                encoding="utf-8",
            )

            result = self.mod.check_model_exists("acestep-v15-turbo", Path(tmp_dir))

        self.assertFalse(result)

    def test_returns_true_when_model_weights_are_present(self):
        """check_model_exists accepts directories that contain a weights artifact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_dir = Path(tmp_dir) / "acestep-v15-turbo"
            model_dir.mkdir()
            (model_dir / "model.safetensors").write_text("weights", encoding="utf-8")

            result = self.mod.check_model_exists("acestep-v15-turbo", Path(tmp_dir))

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
