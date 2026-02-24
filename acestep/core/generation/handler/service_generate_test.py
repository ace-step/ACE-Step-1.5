"""Unit tests for extracted service-generation orchestration.

This test module loads ``service_generate.py`` directly from file to avoid
package import side effects, then validates that orchestration wiring and
runtime-control forwarding remain stable after extraction.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_service_generate_module():
    """Load ``acestep.core.generation.handler.service_generate`` from disk.

    Inputs:
        Resolves the repository root from this file path, injects it into
        ``sys.path``, and stubs package modules in ``sys.modules``.

    Returns:
        The loaded module object for
        ``acestep.core.generation.handler.service_generate``.

    Raises:
        AssertionError: If import spec loader cannot be created.
        ImportError: If module loading fails.
        OSError: If the module file cannot be read.
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
    module_path = Path(__file__).with_name("service_generate.py")
    spec = importlib.util.spec_from_file_location("acestep.core.generation.handler.service_generate", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# Import context: load extracted mixin directly to isolate tests from package side effects.
SERVICE_GENERATE_MODULE = _load_service_generate_module()
ServiceGenerateMixin = SERVICE_GENERATE_MODULE.ServiceGenerateMixin


class _Host(ServiceGenerateMixin):
    """Minimal orchestration host used to record helper invocations.

    Exposes deterministic fixture state and a ``calls`` dictionary for asserted
    input/output forwarding across normalize, diffusion, and attachment helpers.
    """

    def __init__(self):
        """Initialize deterministic fixtures and return values for helper stubs."""
        self.calls = {}
        self.normalized = {
            "captions": ["cap"], "lyrics": ["lyr"], "keys": ["k1"], "metas": [{"bpm": 120}],
            "vocal_languages": ["en"], "repainting_start": [0.0], "repainting_end": [12.0],
            "instructions": ["ins"], "audio_code_hints": ["hint"], "infer_steps": 77, "seed_list": [101],
        }
        self.batch = {"batch": "prepared"}
        self.processed = {"processed": "batch"}
        self.payload = {"payload": "ready"}
        self.seed_param = 314
        self.generate_kwargs = {"gw": "args"}
        self.diffusion_outputs = ("outputs", "ehs", "eam", "ctx")
        self.final_payload = {"result": "ok"}
        self._returns = {
            "_prepare_batch": lambda _a, _k: self.batch,
            "preprocess_batch": lambda _a, _k: self.processed,
            "_unpack_service_processed_data": lambda _a, _k: self.payload,
            "_resolve_service_seed_param": lambda _a, _k: self.seed_param,
            "_ensure_silence_latent_on_device": lambda _a, _k: None,
            "_build_service_generate_kwargs": lambda _a, _k: self.generate_kwargs,
            "_execute_service_generate_diffusion": lambda _a, _k: self.diffusion_outputs,
            "_attach_service_generate_outputs": lambda _a, _k: self.final_payload,
        }

    def _normalize_service_generate_inputs(self, **kwargs):
        """Capture normalize args and return deterministic normalized payload."""
        self.calls["_normalize_service_generate_inputs"] = kwargs
        out = dict(self.normalized)
        out["return_intermediate"] = kwargs["return_intermediate"]
        return out

    def __getattr__(self, name):
        """Create and return a recording helper stub for known mixin dependencies."""
        if name not in self._returns:
            raise AttributeError(name)

        def _stub(*args, **kwargs):
            """Record call arguments and return deterministic fixture data."""
            self.calls[name] = kwargs if kwargs else (args[0] if len(args) == 1 else args if args else True)
            return self._returns[name](args, kwargs)

        return _stub


class ServiceGenerateMixinTests(unittest.TestCase):
    """Verify service-generate entrypoint orchestration after extraction."""

    def test_service_generate_orchestrates_helpers_and_returns_attached_outputs(self):
        """It executes helper stages in order and returns attached final outputs."""
        host = _Host()
        out = host.service_generate(captions="cap", lyrics="lyr", infer_steps=10, seed=7, return_intermediate=True)
        self.assertEqual(out, host.final_payload)
        self.assertEqual(host.calls["_normalize_service_generate_inputs"]["infer_steps"], 10)
        self.assertEqual(host.calls["_normalize_service_generate_inputs"]["seed"], 7)
        self.assertTrue(host.calls["_normalize_service_generate_inputs"]["return_intermediate"])
        self.assertEqual(host.calls["_prepare_batch"]["captions"], host.normalized["captions"])
        self.assertEqual(host.calls["_resolve_service_seed_param"], host.normalized["seed_list"])
        self.assertTrue(host.calls["_attach_service_generate_outputs"]["return_intermediate"])

    def test_service_generate_forwards_runtime_controls_to_build_and_execute(self):
        """It forwards runtime tuning controls to downstream helper invocations."""
        host = _Host()
        custom_timesteps = [1.0, 0.5, 0.0]
        host.service_generate(
            captions="cap", lyrics="lyr", guidance_scale=9.5, audio_cover_strength=0.7,
            cover_noise_strength=0.2, use_adg=True, cfg_interval_start=0.1, cfg_interval_end=0.9,
            shift=1.3, infer_method="sde", timesteps=custom_timesteps, return_intermediate=False,
        )
        build_kwargs = host.calls["_build_service_generate_kwargs"]
        self.assertEqual(build_kwargs["guidance_scale"], 9.5)
        self.assertEqual(build_kwargs["audio_cover_strength"], 0.7)
        self.assertEqual(build_kwargs["cover_noise_strength"], 0.2)
        self.assertTrue(build_kwargs["use_adg"])
        self.assertEqual(build_kwargs["timesteps"], custom_timesteps)
        self.assertFalse(host.calls["_attach_service_generate_outputs"]["return_intermediate"])
        execute_kwargs = host.calls["_execute_service_generate_diffusion"]
        self.assertEqual(execute_kwargs["infer_method"], "sde")
        self.assertEqual(execute_kwargs["shift"], 1.3)
        self.assertEqual(execute_kwargs["audio_cover_strength"], 0.7)


if __name__ == "__main__":
    unittest.main()
