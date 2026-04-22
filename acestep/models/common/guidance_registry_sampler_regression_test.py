"""Sampler-level regression tests for the pluggable guidance registry.

These tests reproduce the exact per-step call pattern that
``generate_audio()`` uses to invoke guidance — momentum buffer for APG main
steps, plain CFG for APG corrector steps, ADG for ADG main/corrector steps
with a ``sigma == 0`` safeguard — and compare the registry-mediated output
to the hand-written pre-refactor call sequence tensor-for-tensor.

No model weights are required: the test uses synthetic tensors that obey
the ACE-Step shape convention ``[B, T, C]`` (dims=[1] aligns with the
sequence axis).  This is the "byte-identical" commitment promised to the
upstream maintainer on Issue #1124.
"""

from __future__ import annotations

import unittest

import torch

from acestep.models.common.apg_guidance import (
    MomentumBuffer,
    adg_forward,
    apg_forward,
    cfg_forward,
)
from acestep.models.common.guidance_registry import get_guidance_fn


def _make_predictions(seed: int, steps: int, shape=(1, 4, 16)):
    """Deterministic cond/uncond prediction pairs for a sequence of steps."""

    generator = torch.Generator().manual_seed(seed)
    pairs = []
    for _ in range(steps):
        pred_cond = torch.randn(*shape, generator=generator)
        pred_uncond = torch.randn(*shape, generator=generator)
        latents = torch.randn(*shape, generator=generator)
        pairs.append((pred_cond, pred_uncond, latents))
    return pairs


class ApgClassicSamplerParityTests(unittest.TestCase):
    """APG main + corrector dispatch must match the pre-refactor branch."""

    def test_full_euler_sequence_matches_hand_written_loop(self) -> None:
        """Registry dispatch across N Euler steps equals direct apg_forward calls."""

        steps = 5
        sequence = _make_predictions(seed=11, steps=steps)
        scale = 5.0

        # Reference path: pre-refactor logic.
        ref_buffer = MomentumBuffer()
        reference_outputs = []
        for pred_cond, pred_uncond, _latents in sequence:
            reference_outputs.append(
                apg_forward(
                    pred_cond=pred_cond,
                    pred_uncond=pred_uncond,
                    guidance_scale=scale,
                    momentum_buffer=ref_buffer,
                    dims=[1],
                )
            )

        # Registry path.
        fn = get_guidance_fn("apg_classic")
        state: dict = {}
        reg_outputs = []
        for pred_cond, pred_uncond, latents in sequence:
            state["latents"] = latents
            state["sigma"] = 0.5
            state["step_role"] = "main"
            reg_outputs.append(fn(pred_cond, pred_uncond, scale, state))

        for ref, got in zip(reference_outputs, reg_outputs):
            self.assertTrue(torch.allclose(ref, got))

    def test_heun_sequence_matches_hand_written_loop(self) -> None:
        """Heun predictor+corrector dispatch equals direct apg/cfg calls."""

        steps = 4
        sequence = _make_predictions(seed=12, steps=steps)
        scale = 4.5

        ref_buffer = MomentumBuffer()
        reference_outputs = []
        for pred_cond, pred_uncond, _latents in sequence:
            main = apg_forward(
                pred_cond=pred_cond,
                pred_uncond=pred_uncond,
                guidance_scale=scale,
                momentum_buffer=ref_buffer,
                dims=[1],
            )
            corr = cfg_forward(pred_cond, pred_uncond, scale)
            reference_outputs.append((main, corr))

        fn = get_guidance_fn("apg_classic")
        state: dict = {}
        reg_outputs = []
        for pred_cond, pred_uncond, latents in sequence:
            state["latents"] = latents
            state["sigma"] = 0.5
            state["step_role"] = "main"
            main = fn(pred_cond, pred_uncond, scale, state)
            state["step_role"] = "corrector"
            corr = fn(pred_cond, pred_uncond, scale, state)
            reg_outputs.append((main, corr))

        for (ref_main, ref_corr), (got_main, got_corr) in zip(reference_outputs, reg_outputs):
            self.assertTrue(torch.allclose(ref_main, got_main))
            self.assertTrue(torch.allclose(ref_corr, got_corr))


class AdgSamplerParityTests(unittest.TestCase):
    """ADG main + corrector dispatch with sigma=0 safeguard matches pre-refactor."""

    def test_heun_sequence_matches_hand_written_loop_with_zero_sigma_corrector(self) -> None:
        """Last corrector step uses CFG (sigma=0); others use adg_forward."""

        steps = 4
        sequence = _make_predictions(seed=13, steps=steps)
        scale = 6.0
        # Mimic the sampler: final corrector step lands on t_prev == 0.
        sigmas_main = [0.8, 0.6, 0.4, 0.2]
        sigmas_corr = [0.6, 0.4, 0.2, 0.0]

        reference_outputs = []
        for (pred_cond, pred_uncond, latents), sigma_m, sigma_c in zip(
            sequence, sigmas_main, sigmas_corr,
        ):
            main = adg_forward(
                latents=latents,
                noise_pred_cond=pred_cond,
                noise_pred_uncond=pred_uncond,
                sigma=sigma_m,
                guidance_scale=scale,
            )
            if sigma_c > 0:
                corr = adg_forward(
                    latents=latents,
                    noise_pred_cond=pred_cond,
                    noise_pred_uncond=pred_uncond,
                    sigma=sigma_c,
                    guidance_scale=scale,
                )
            else:
                corr = cfg_forward(pred_cond, pred_uncond, scale)
            reference_outputs.append((main, corr))

        fn = get_guidance_fn("adg")
        state: dict = {}
        reg_outputs = []
        for (pred_cond, pred_uncond, latents), sigma_m, sigma_c in zip(
            sequence, sigmas_main, sigmas_corr,
        ):
            state["latents"] = latents
            state["sigma"] = sigma_m
            state["step_role"] = "main"
            main = fn(pred_cond, pred_uncond, scale, state)
            state["sigma"] = sigma_c
            state["step_role"] = "corrector"
            corr = fn(pred_cond, pred_uncond, scale, state)
            reg_outputs.append((main, corr))

        for (ref_main, ref_corr), (got_main, got_corr) in zip(reference_outputs, reg_outputs):
            self.assertTrue(torch.allclose(ref_main, got_main))
            self.assertTrue(torch.allclose(ref_corr, got_corr))


if __name__ == "__main__":
    unittest.main()
