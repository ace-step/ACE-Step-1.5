"""Unit tests for generation_info module."""

import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


def _load_module():
    """Load target module directly by file path for isolated testing."""
    # Stub i18n package path so importing generation_info.py does not require
    # importing the full Gradio UI package in headless test environments.
    acestep_pkg = sys.modules.setdefault("acestep", types.ModuleType("acestep"))
    ui_pkg = sys.modules.setdefault("acestep.ui", types.ModuleType("acestep.ui"))
    gradio_pkg = sys.modules.setdefault("acestep.ui.gradio", types.ModuleType("acestep.ui.gradio"))
    i18n_mod = types.ModuleType("acestep.ui.gradio.i18n")
    i18n_mod.t = lambda key, **kwargs: key
    sys.modules["acestep.ui.gradio.i18n"] = i18n_mod
    acestep_pkg.ui = ui_pkg
    ui_pkg.gradio = gradio_pkg
    gradio_pkg.i18n = i18n_mod

    module_path = Path(__file__).with_name("generation_info.py")
    spec = importlib.util.spec_from_file_location("generation_info", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_MODULE = _load_module()
DEFAULT_RESULTS_DIR = _MODULE.DEFAULT_RESULTS_DIR
PROJECT_ROOT = _MODULE.PROJECT_ROOT
clear_audio_outputs_for_new_generation = _MODULE.clear_audio_outputs_for_new_generation
_build_generation_info = _MODULE._build_generation_info


class ConstantsTests(unittest.TestCase):
    """Tests for module-level constants."""

    def test_project_root_exists(self):
        """PROJECT_ROOT should point to an existing directory."""
        self.assertTrue(os.path.isdir(PROJECT_ROOT))

    def test_default_results_dir_is_under_project_root(self):
        """DEFAULT_RESULTS_DIR should be a subdirectory of PROJECT_ROOT."""
        self.assertTrue(
            DEFAULT_RESULTS_DIR.replace("\\", "/").startswith(
                PROJECT_ROOT.replace("\\", "/")
            )
        )


class ClearAudioOutputsTests(unittest.TestCase):
    """Tests for clear_audio_outputs_for_new_generation."""

    def test_returns_nine_nones(self):
        """Should return a tuple of 9 None values."""
        result = clear_audio_outputs_for_new_generation()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 9)
        for item in result:
            self.assertIsNone(item)

    def test_gradio_runtime_skips_audio_clear_but_clears_batch_files(self):
        """With Gradio available, audio outputs should be skip updates."""
        fake_gradio = types.SimpleNamespace(skip=lambda: "SKIP")
        with patch.dict("sys.modules", {"gradio": fake_gradio}):
            result = clear_audio_outputs_for_new_generation()
        self.assertEqual(len(result), 9)
        self.assertEqual(result[:8], ("SKIP",) * 8)
        self.assertIsNone(result[8])


class BuildGenerationInfoTests(unittest.TestCase):
    """Tests for _build_generation_info."""

    def test_basic_generation_info(self):
        """Should build a readable info string from basic parameters."""
        time_costs = {
            "lm_total_time": 2.0,
            "dit_total_time_cost": 3.0,
            "audio_conversion_time": 0.5,
        }
        info = _build_generation_info(
            lm_metadata=None,
            time_costs=time_costs,
            seed_value="42",
            inference_steps=100,
            num_audios=2,
            audio_format="flac",
        )
        self.assertIsInstance(info, str)
        self.assertIn("generation time", info.lower())

    def test_empty_time_costs_returns_empty(self):
        """Empty time_costs should return an empty string."""
        info = _build_generation_info(
            lm_metadata=None,
            time_costs={},
            seed_value="0",
            inference_steps=50,
            num_audios=1,
        )
        self.assertEqual(info, "")

    def test_zero_audios_returns_empty(self):
        """Zero num_audios should return an empty string."""
        info = _build_generation_info(
            lm_metadata=None,
            time_costs={"dit_total_time_cost": 5.0},
            seed_value="0",
            inference_steps=50,
            num_audios=0,
        )
        self.assertEqual(info, "")

    def test_non_target_behavior_unchanged(self):
        """Calling with same params twice should produce identical output."""
        kwargs = dict(
            lm_metadata=None,
            time_costs={"dit_total_time_cost": 5.0, "lm_total_time": 1.0},
            seed_value="123",
            inference_steps=200,
            num_audios=4,
            audio_format="mp3",
        )
        info1 = _build_generation_info(**kwargs)
        info2 = _build_generation_info(**kwargs)
        self.assertEqual(info1, info2)


if __name__ == "__main__":
    unittest.main()
