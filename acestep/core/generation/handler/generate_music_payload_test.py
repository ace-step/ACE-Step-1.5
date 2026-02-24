"""Tests for extracted ``generate_music`` success-payload builder behavior.

The module loads ``acestep.core.generation.handler.generate_music_payload``
directly from file and validates final payload assembly with deterministic test
fixtures.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path

import torch


def _load_generate_music_payload_module():
    """Load ``generate_music_payload.py`` from disk for isolated tests.

    Returns:
        types.ModuleType: Loaded module object for
        ``acestep.core.generation.handler.generate_music_payload``.

    Raises:
        FileNotFoundError: If the target file does not exist.
        ImportError: If module execution fails.
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
    module_path = Path(__file__).with_name("generate_music_payload.py")
    spec = importlib.util.spec_from_file_location(
        "acestep.core.generation.handler.generate_music_payload",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GENERATE_MUSIC_PAYLOAD_MODULE = _load_generate_music_payload_module()
GenerateMusicPayloadMixin = GENERATE_MUSIC_PAYLOAD_MODULE.GenerateMusicPayloadMixin


class _Host(GenerateMusicPayloadMixin):
    """Minimal host providing state required by payload assembly tests."""

    def __init__(self):
        """Initialize deterministic sample rate state."""
        self.sample_rate = 48000


class GenerateMusicPayloadMixinTests(unittest.TestCase):
    """Verify payload builder output structure and tensor routing."""

    def test_build_success_payload_contains_audio_and_extra_outputs(self):
        """It assembles audios and extra_outputs with CPU tensors and metadata."""
        host = _Host()
        outputs = {
            "target_latents_input": torch.ones(1, 4, 3),
            "src_latents": torch.ones(1, 4, 3),
            "chunk_masks": torch.ones(1, 4),
            "latent_masks": torch.ones(1, 4),
            "spans": [(0, 4)],
            "encoder_hidden_states": torch.ones(1, 2, 3),
            "encoder_attention_mask": torch.ones(1, 2),
            "context_latents": torch.ones(1, 4, 3),
            "lyric_token_idss": torch.ones(1, 2, dtype=torch.long),
        }
        pred_wavs = torch.ones(1, 2, 8)
        pred_latents_cpu = torch.ones(1, 4, 3)
        time_costs = {"total_time_cost": 2.0}
        progress_calls = []

        def _progress(value, desc=None):
            """Capture progress updates for assertions."""
            progress_calls.append((value, desc))

        payload = host._build_generate_music_success_payload(
            outputs=outputs,
            pred_wavs=pred_wavs,
            pred_latents_cpu=pred_latents_cpu,
            time_costs=time_costs,
            seed_value_for_ui=7,
            actual_batch_size=1,
            progress=_progress,
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["error"], None)
        self.assertEqual(len(payload["audios"]), 1)
        self.assertEqual(payload["audios"][0]["sample_rate"], 48000)
        self.assertEqual(payload["extra_outputs"]["seed_value"], 7)
        self.assertEqual(payload["extra_outputs"]["pred_latents"].device.type, "cpu")
        self.assertEqual(progress_calls[0][0], 0.99)

    def test_build_success_payload_handles_missing_optional_outputs_without_progress(self):
        """It handles absent optional output keys and no progress callback."""
        host = _Host()
        outputs = {}
        pred_wavs = torch.ones(1, 2, 8)
        pred_latents_cpu = torch.ones(1, 4, 3)
        time_costs = {"total_time_cost": 2.0}

        payload = host._build_generate_music_success_payload(
            outputs=outputs,
            pred_wavs=pred_wavs,
            pred_latents_cpu=pred_latents_cpu,
            time_costs=time_costs,
            seed_value_for_ui=11,
            actual_batch_size=1,
            progress=None,
        )

        self.assertTrue(payload["success"])
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["status_message"], "Generation completed successfully!")
        self.assertEqual(payload["extra_outputs"]["spans"], [])
        self.assertIsNone(payload["extra_outputs"]["encoder_hidden_states"])
        self.assertIsNone(payload["extra_outputs"]["encoder_attention_mask"])
        self.assertIsNone(payload["extra_outputs"]["context_latents"])
        self.assertEqual(payload["extra_outputs"]["pred_latents"].device.type, "cpu")


if __name__ == "__main__":
    unittest.main()
