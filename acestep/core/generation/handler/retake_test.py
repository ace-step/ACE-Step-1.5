"""Tests for retake noise mixing (issue #1155).

The retake mechanism re-uses the existing ``prepare_noise()`` helper twice
(once for the main seed, once for the retake seed) and blends the results
via a variance-preserving sin/cos mix:

    mixed = cos(v · π/2) · base + sin(v · π/2) · retake

These tests pin down the four invariants the model layer relies on:

1. ``v=0`` is a no-op (mixed == base)
2. ``v=1`` collapses to ``retake`` (cos(π/2)=0, sin(π/2)=1)
3. The mix preserves unit-normal statistics (cos²+sin² = 1)
4. The blend is deterministic given the same seeds

A separate group covers the runtime-helper gate that resolves retake seeds
only when ``retake_variance > 0`` (so we do not consume randomness for
the no-op path) and persists the resolved seeds for the metadata payload.
"""

import math
import unittest
from unittest.mock import MagicMock

import torch

from acestep.core.generation.handler.generate_music_request import (
    GenerateMusicRequestMixin,
)
from acestep.core.generation.handler.task_utils import TaskUtilsMixin


def _retake_mix(base: torch.Tensor, retake: torch.Tensor, variance: float) -> torch.Tensor:
    """Reference implementation mirroring the inline mix inside generate_audio."""
    v_rad = variance * (math.pi / 2.0)
    return math.cos(v_rad) * base + math.sin(v_rad) * retake


def _draw(shape, seed: int) -> torch.Tensor:
    g = torch.Generator(device="cpu").manual_seed(seed)
    return torch.randn(shape, generator=g)


class RetakeMixMathTests(unittest.TestCase):
    """Pin the variance-preserving sin/cos mix used by retake."""

    SHAPE = (2, 8, 16)

    def test_variance_zero_is_noop(self):
        base = _draw(self.SHAPE, seed=1)
        retake = _draw(self.SHAPE, seed=2)
        mixed = _retake_mix(base, retake, 0.0)
        self.assertTrue(torch.equal(mixed, base))

    def test_variance_one_collapses_to_retake(self):
        base = _draw(self.SHAPE, seed=1)
        retake = _draw(self.SHAPE, seed=2)
        mixed = _retake_mix(base, retake, 1.0)
        # cos(π/2) is not exactly zero in float, so allow tiny epsilon.
        self.assertTrue(torch.allclose(mixed, retake, atol=1e-6))

    def test_unit_variance_preserved(self):
        """cos²+sin² = 1 → mixing two i.i.d. N(0,1) draws stays N(0,1)."""
        base = torch.randn(8192, generator=torch.Generator().manual_seed(11))
        retake = torch.randn(8192, generator=torch.Generator().manual_seed(22))
        for v in (0.25, 0.5, 0.75):
            mixed = _retake_mix(base, retake, v)
            self.assertAlmostEqual(mixed.mean().item(), 0.0, delta=0.05)
            # Tolerance is loose because we only check mathematical preservation,
            # not the empirical std of a single 8192-sample draw.
            self.assertAlmostEqual(mixed.std().item(), 1.0, delta=0.05)

    def test_determinism_same_seeds(self):
        base_a = _draw(self.SHAPE, seed=42)
        retake_a = _draw(self.SHAPE, seed=99)
        base_b = _draw(self.SHAPE, seed=42)
        retake_b = _draw(self.SHAPE, seed=99)
        mixed_a = _retake_mix(base_a, retake_a, 0.5)
        mixed_b = _retake_mix(base_b, retake_b, 0.5)
        self.assertTrue(torch.equal(mixed_a, mixed_b))

    def test_different_retake_seeds_diverge(self):
        base = _draw(self.SHAPE, seed=42)
        retake_a = _draw(self.SHAPE, seed=99)
        retake_b = _draw(self.SHAPE, seed=100)
        mixed_a = _retake_mix(base, retake_a, 0.5)
        mixed_b = _retake_mix(base, retake_b, 0.5)
        self.assertFalse(torch.equal(mixed_a, mixed_b))


class _RuntimeHost(TaskUtilsMixin, GenerateMusicRequestMixin):
    """Minimal host that exposes the runtime mixin without a real model."""

    def __init__(self):
        self.batch_size = 1
        self.current_offload_cost = 0.0

    def _vram_guard_reduce_batch(self, actual_batch_size, audio_duration=None):
        return actual_batch_size


class RetakeRuntimeGateTests(unittest.TestCase):
    """Verify ``_prepare_generate_music_runtime`` only resolves retake seeds when v>0."""

    def setUp(self):
        self.host = _RuntimeHost()

    def test_variance_zero_does_not_resolve_retake_seeds(self):
        runtime = self.host._prepare_generate_music_runtime(
            batch_size=2,
            audio_duration=10.0,
            repainting_end=None,
            seed=42,
            use_random_seed=False,
            retake_seed="123",
            retake_variance=0.0,
        )
        self.assertIsNone(runtime["actual_retake_seed_list"])
        self.assertEqual(runtime["retake_seed_value_for_ui"], "")

    def test_variance_positive_resolves_explicit_retake_seed(self):
        runtime = self.host._prepare_generate_music_runtime(
            batch_size=1,
            audio_duration=10.0,
            repainting_end=None,
            seed=42,
            use_random_seed=False,
            retake_seed="555",
            retake_variance=0.5,
        )
        self.assertEqual(runtime["actual_retake_seed_list"], [555])
        self.assertEqual(runtime["retake_seed_value_for_ui"], "555")

    def test_variance_positive_with_none_retake_seed_falls_back_random(self):
        runtime = self.host._prepare_generate_music_runtime(
            batch_size=2,
            audio_duration=10.0,
            repainting_end=None,
            seed=42,
            use_random_seed=False,
            retake_seed=None,
            retake_variance=0.5,
        )
        seeds = runtime["actual_retake_seed_list"]
        self.assertEqual(len(seeds), 2)
        for s in seeds:
            self.assertIsInstance(s, int)
            self.assertGreaterEqual(s, 0)
        self.assertTrue(runtime["retake_seed_value_for_ui"])

    def test_default_retake_kwargs_omitted_preserves_legacy_behavior(self):
        """Callers that do not pass retake kwargs must keep the old contract."""
        runtime = self.host._prepare_generate_music_runtime(
            batch_size=1,
            audio_duration=10.0,
            repainting_end=None,
            seed=42,
            use_random_seed=False,
        )
        self.assertIsNone(runtime["actual_retake_seed_list"])
        self.assertEqual(runtime["retake_seed_value_for_ui"], "")
        self.assertIn("seed_value_for_ui", runtime)


if __name__ == "__main__":
    unittest.main()
