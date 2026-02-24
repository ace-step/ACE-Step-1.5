"""Unit tests for training-preset switching behavior."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_training_preset_module():
    """Load training_preset module directly from file to avoid package side effects."""
    repo_root = Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    package_paths = {
        "acestep": repo_root / "acestep",
        "acestep.core": repo_root / "acestep" / "core",
        "acestep.core.generation": repo_root / "acestep" / "core" / "generation",
        "acestep.core.generation.handler": repo_root / "acestep" / "core" / "generation" / "handler",
    }
    for package_name, package_path in package_paths.items():
        if package_name in sys.modules:
            continue
        package_module = types.ModuleType(package_name)
        package_module.__path__ = [str(package_path)]
        sys.modules[package_name] = package_module
    module_path = Path(__file__).with_name("training_preset.py")
    spec = importlib.util.spec_from_file_location(
        "acestep.core.generation.handler.training_preset",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


TRAINING_PRESET_MODULE = _load_training_preset_module()
TrainingPresetMixin = TRAINING_PRESET_MODULE.TrainingPresetMixin


class _Host(TrainingPresetMixin):
    """Minimal host object exposing TrainingPresetMixin for focused unit testing."""

    def __init__(self):
        """Initialize host state needed for switch_to_training_preset tests."""
        self.quantization = None
        self.last_init_params = None
        self._initialize_calls = []
        self._initialize_result = ("ok", True)

    def initialize_service(self, **kwargs):
        """Capture initialize_service arguments and return a configured test result."""
        self._initialize_calls.append(kwargs)
        return self._initialize_result


class TrainingPresetMixinTests(unittest.TestCase):
    """Behavioral tests for training-preset switching helpers."""

    def test_switch_to_training_preset_returns_already_safe_when_unquantized(self):
        """It short-circuits when quantization is already disabled."""
        host = _Host()
        status, ok = host.switch_to_training_preset()
        self.assertTrue(ok)
        self.assertIn("Already in training-safe preset", status)
        self.assertEqual(host._initialize_calls, [])

    def test_switch_to_training_preset_fails_without_last_init_params(self):
        """It returns a descriptive failure when no previous init params are stored."""
        host = _Host()
        host.quantization = "int8_weight_only"
        status, ok = host.switch_to_training_preset()
        self.assertFalse(ok)
        self.assertIn("no previous init parameters", status)
        self.assertEqual(host._initialize_calls, [])

    def test_switch_to_training_preset_reinitializes_without_quantization(self):
        """It reinitializes using cached params and forces quantization to None."""
        host = _Host()
        host.quantization = "int8_weight_only"
        host.last_init_params = {
            "project_root": "K:/fake_root",
            "config_path": "acestep-v15-turbo",
            "device": "cpu",
            "use_flash_attention": False,
            "compile_model": True,
            "offload_to_cpu": False,
            "offload_dit_to_cpu": False,
            "quantization": "int8_weight_only",
            "prefer_source": "huggingface",
            "use_mlx_dit": False,
        }
        host._initialize_result = ("reinit ok", True)

        status, ok = host.switch_to_training_preset()

        self.assertTrue(ok)
        self.assertIn("Switched to training preset", status)
        self.assertIn("reinit ok", status)
        self.assertEqual(len(host._initialize_calls), 1)
        call = host._initialize_calls[0]
        self.assertIsNone(call["quantization"])
        self.assertEqual(call["prefer_source"], "huggingface")
        self.assertFalse(call["use_mlx_dit"])
        self.assertEqual(call["config_path"], "acestep-v15-turbo")

    def test_switch_to_training_preset_returns_failure_on_reinit_error(self):
        """It returns a failure message when initialize_service reports failure."""
        host = _Host()
        host.quantization = "fp8_weight_only"
        host.last_init_params = {
            "project_root": "K:/fake_root",
            "config_path": "acestep-v15-turbo",
            "device": "cpu",
            "use_flash_attention": False,
            "compile_model": False,
            "offload_to_cpu": True,
            "offload_dit_to_cpu": True,
            "quantization": "fp8_weight_only",
        }
        host._initialize_result = ("boom", False)

        status, ok = host.switch_to_training_preset()

        self.assertFalse(ok)
        self.assertIn("Failed to switch to training preset", status)
        self.assertIn("boom", status)
        self.assertEqual(len(host._initialize_calls), 1)
        self.assertIsNone(host._initialize_calls[0]["quantization"])

    def test_switch_to_training_preset_passes_none_when_prefer_source_absent(self):
        """It forwards ``prefer_source=None`` and default ``use_mlx_dit=True`` when missing."""
        host = _Host()
        host.quantization = "int8_weight_only"
        host.last_init_params = {
            "project_root": "K:/fake_root",
            "config_path": "acestep-v15-turbo",
            "device": "cpu",
            "use_flash_attention": False,
            "compile_model": True,
            "offload_to_cpu": False,
            "offload_dit_to_cpu": False,
            "quantization": "int8_weight_only",
        }
        host._initialize_result = ("ok", True)

        _, ok = host.switch_to_training_preset()

        self.assertTrue(ok)
        self.assertEqual(len(host._initialize_calls), 1)
        self.assertIsNone(host._initialize_calls[0]["prefer_source"])
        self.assertTrue(host._initialize_calls[0]["use_mlx_dit"])

    def test_switch_to_training_preset_does_not_mutate_last_init_params(self):
        """It preserves cached init parameters while forcing quantization only in call args."""
        host = _Host()
        host.quantization = "int8_weight_only"
        host.last_init_params = {
            "project_root": "K:/fake_root",
            "config_path": "acestep-v15-turbo",
            "device": "cpu",
            "use_flash_attention": False,
            "compile_model": True,
            "offload_to_cpu": False,
            "offload_dit_to_cpu": False,
            "quantization": "int8_weight_only",
            "prefer_source": "modelscope",
        }
        host._initialize_result = ("ok", True)

        _, ok = host.switch_to_training_preset()

        self.assertTrue(ok)
        self.assertEqual(host.last_init_params["quantization"], "int8_weight_only")
        self.assertIsNone(host._initialize_calls[0]["quantization"])


if __name__ == "__main__":
    unittest.main()
