"""Tests for extracted ``generate_music`` orchestration behavior.

The module loads ``acestep.core.generation.handler.generate_music`` directly
from file to avoid package import side effects and validates orchestration
ordering, readiness short-circuiting, and failure payload handling.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any, Dict

import torch


def _load_generate_music_module():
    """Load ``generate_music.py`` from disk for isolated mixin tests.

    Returns:
        types.ModuleType: Loaded module object for
        ``acestep.core.generation.handler.generate_music``.

    Raises:
        FileNotFoundError: If the target module file is missing.
        ImportError: If module loading fails.
    """
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
    module_path = Path(__file__).with_name("generate_music.py")
    spec = importlib.util.spec_from_file_location(
        "acestep.core.generation.handler.generate_music",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GENERATE_MUSIC_MODULE = _load_generate_music_module()
GenerateMusicMixin = GENERATE_MUSIC_MODULE.GenerateMusicMixin


class _Host(GenerateMusicMixin):
    """Minimal host implementing ``generate_music`` helper dependencies.

    The host captures helper calls in ``self.calls`` and returns deterministic
    payloads so tests can assert orchestration sequencing and return behavior.
    """

    def __init__(self):
        """Initialize deterministic state and stub payloads for orchestration tests."""
        self.model = object()
        self.vae = object()
        self.text_tokenizer = object()
        self.text_encoder = object()
        self.calls: Dict[str, Any] = {}
        self._final_payload = {"audios": [{"tensor": torch.zeros(1, 4), "sample_rate": 48000}], "success": True}
        self._readiness_error = {
            "audios": [],
            "status_message": "not ready",
            "extra_outputs": {},
            "success": False,
            "error": "Model not fully initialized",
        }

    def _resolve_generate_music_progress(self, progress):
        """Return provided callback or deterministic no-op callback."""
        self.calls["_resolve_generate_music_progress"] = bool(progress)
        if progress is not None:
            return progress

        def _noop(*_args, **_kwargs):
            """Ignore progress updates in tests."""
            return None

        return _noop

    def _validate_generate_music_readiness(self):
        """Return deterministic readiness error payload."""
        self.calls["_validate_generate_music_readiness"] = True
        return self._readiness_error

    def _resolve_generate_music_task(self, **kwargs):
        """Capture task resolution args and return deterministic task/instruction."""
        self.calls["_resolve_generate_music_task"] = kwargs
        return kwargs["task_type"], kwargs["instruction"]

    def _prepare_generate_music_runtime(self, **kwargs):
        """Capture runtime args and return deterministic runtime state."""
        self.calls["_prepare_generate_music_runtime"] = kwargs
        return {
            "actual_batch_size": 1,
            "actual_seed_list": [77],
            "seed_value_for_ui": 77,
            "audio_duration": kwargs["audio_duration"],
            "repainting_end": kwargs["repainting_end"],
        }

    def _prepare_reference_and_source_audio(self, **kwargs):
        """Capture audio-prepare args and return deterministic prepared state."""
        self.calls["_prepare_reference_and_source_audio"] = kwargs
        return [[torch.zeros(2, 10)]], None, None

    def _prepare_generate_music_service_inputs(self, **kwargs):
        """Capture service-input args and return deterministic payload."""
        self.calls["_prepare_generate_music_service_inputs"] = kwargs
        return {"should_return_intermediate": True}

    def _run_generate_music_service_with_progress(self, **kwargs):
        """Capture service execution args and return deterministic model outputs."""
        self.calls["_run_generate_music_service_with_progress"] = kwargs
        return {
            "outputs": {
                "target_latents": torch.ones(1, 4, 3),
                "time_costs": {"total_time_cost": 1.0, "diffusion_per_step_time_cost": 0.1},
            },
            "infer_steps_for_progress": 8,
        }

    def _prepare_generate_music_decode_state(self, **kwargs):
        """Capture decode-state args and return deterministic latents/costs."""
        self.calls["_prepare_generate_music_decode_state"] = kwargs
        return torch.ones(1, 4, 3), {"total_time_cost": 1.0}

    def _decode_generate_music_pred_latents(self, **kwargs):
        """Capture decode args and return deterministic decode outputs."""
        self.calls["_decode_generate_music_pred_latents"] = kwargs
        return torch.ones(1, 2, 8), torch.ones(1, 4, 3), {"total_time_cost": 2.0}

    def _build_generate_music_success_payload(self, **kwargs):
        """Capture payload-builder args and return deterministic success payload."""
        self.calls["_build_generate_music_success_payload"] = kwargs
        return self._final_payload


class GenerateMusicMixinTests(unittest.TestCase):
    """Verify top-level ``generate_music`` orchestration behavior."""

    def test_generate_music_returns_success_payload_from_builder(self):
        """It executes helper stages and returns the payload builder result."""
        host = _Host()
        out = host.generate_music(
            captions="cap",
            lyrics="lyr",
            inference_steps=8,
            guidance_scale=6.5,
            use_random_seed=False,
            seed=77,
            task_type="text2music",
        )
        self.assertEqual(out, host._final_payload)
        self.assertEqual(host.calls["_prepare_generate_music_runtime"]["seed"], 77)
        self.assertEqual(host.calls["_run_generate_music_service_with_progress"]["guidance_scale"], 6.5)
        self.assertEqual(host.calls["_prepare_generate_music_decode_state"]["infer_steps_for_progress"], 8)

    def test_generate_music_returns_readiness_error_when_components_missing(self):
        """It short-circuits with readiness payload when required models are missing."""
        host = _Host()
        host.model = None
        out = host.generate_music(captions="cap", lyrics="lyr")
        self.assertEqual(out, host._readiness_error)
        self.assertTrue(host.calls["_validate_generate_music_readiness"])
        self.assertNotIn("_prepare_generate_music_runtime", host.calls)

    def test_generate_music_returns_error_payload_on_exception(self):
        """It catches orchestration errors and returns standardized failure payload."""
        host = _Host()

        def _raise_error(**_kwargs):
            """Raise deterministic runtime failure for exception-path validation."""
            raise RuntimeError("boom")

        host._prepare_reference_and_source_audio = _raise_error
        out = host.generate_music(captions="cap", lyrics="lyr")
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "boom")
        self.assertIn("Error: boom", out["status_message"])


if __name__ == "__main__":
    unittest.main()
