"""Unit tests for the pluggable guidance-variant registry."""

from __future__ import annotations

import unittest

import torch

from acestep.models.common.apg_guidance import (
    MomentumBuffer,
    adg_forward,
    adg_w_norm_forward,
    adg_wo_clip_forward,
    apg_forward,
    cfg_forward,
)
from acestep.models.common.guidance_registry import (
    _GUIDANCE_REGISTRY,
    _MOMENTUM_KEY,
    get_guidance_fn,
    register_guidance,
    registered_guidance_names,
)


def _fixed_tensors(seed: int = 0, shape=(1, 4, 8)):
    """Deterministic tensor pair for parity tests."""

    generator = torch.Generator().manual_seed(seed)
    pred_cond = torch.randn(*shape, generator=generator)
    pred_uncond = torch.randn(*shape, generator=generator)
    return pred_cond, pred_uncond


class GuidanceRegistryTests(unittest.TestCase):
    """Structural guarantees on the default registry contents."""

    def test_default_registry_has_five_variants(self) -> None:
        """The five baseline guidance variants must ship with the module."""

        self.assertEqual(
            sorted(registered_guidance_names()),
            ["adg", "adg_w_norm", "adg_wo_clip", "apg_classic", "cfg"],
        )

    def test_register_guidance_adds_entry(self) -> None:
        """Decorator should add a callable entry resolvable by get_guidance_fn."""

        sentinel = torch.tensor(3.14)

        @register_guidance("unit_test_noop")
        def _fake(_pc, _pu, _gs, _state, **_params):
            return sentinel

        try:
            resolved = get_guidance_fn("unit_test_noop")
            self.assertIs(resolved({}, {}, 1.0, {}), sentinel)
        finally:
            _GUIDANCE_REGISTRY.pop("unit_test_noop", None)

    def test_get_guidance_fn_unknown_raises_valueerror(self) -> None:
        """Unknown variant lookup must surface a message listing registered names."""

        with self.assertRaises(ValueError) as ctx:
            get_guidance_fn("does_not_exist")
        message = str(ctx.exception)
        self.assertIn("does_not_exist", message)
        for name in ("apg_classic", "cfg", "adg"):
            self.assertIn(name, message)


class GuidanceWrapperParityTests(unittest.TestCase):
    """Wrappers must produce byte-identical output to the raw guidance functions."""

    def test_apg_classic_wrapper_matches_apg_forward(self) -> None:
        """APG wrapper with default params equals apg_forward with fresh momentum."""

        pred_cond, pred_uncond = _fixed_tensors(seed=1)
        state: dict = {}
        guided_via_registry = get_guidance_fn("apg_classic")(
            pred_cond, pred_uncond, 5.0, state,
        )
        expected = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=5.0,
            momentum_buffer=MomentumBuffer(),
            dims=[1],
        )
        self.assertTrue(torch.allclose(guided_via_registry, expected))

    def test_cfg_wrapper_matches_cfg_forward(self) -> None:
        """CFG wrapper delegates directly to cfg_forward."""

        pred_cond, pred_uncond = _fixed_tensors(seed=2)
        actual = get_guidance_fn("cfg")(pred_cond, pred_uncond, 4.0, {})
        self.assertTrue(torch.allclose(actual, cfg_forward(pred_cond, pred_uncond, 4.0)))

    def test_adg_wrapper_matches_adg_forward(self) -> None:
        """ADG wrapper forwards latents/sigma from state to adg_forward."""

        pred_cond, pred_uncond = _fixed_tensors(seed=3)
        latents, _ = _fixed_tensors(seed=33)
        state = {"latents": latents, "sigma": 0.5}
        actual = get_guidance_fn("adg")(pred_cond, pred_uncond, 6.0, state)
        expected = adg_forward(
            latents=latents,
            noise_pred_cond=pred_cond,
            noise_pred_uncond=pred_uncond,
            sigma=0.5,
            guidance_scale=6.0,
            angle_clip=3.14 / 6,
        )
        self.assertTrue(torch.allclose(actual, expected))

    def test_adg_w_norm_wrapper_matches_raw(self) -> None:
        """ADG-with-norm wrapper matches raw adg_w_norm_forward."""

        pred_cond, pred_uncond = _fixed_tensors(seed=4)
        latents, _ = _fixed_tensors(seed=44)
        state = {"latents": latents, "sigma": 0.4}
        actual = get_guidance_fn("adg_w_norm")(pred_cond, pred_uncond, 6.0, state)
        expected = adg_w_norm_forward(
            latents=latents,
            noise_pred_cond=pred_cond,
            noise_pred_uncond=pred_uncond,
            sigma=0.4,
            guidance_scale=6.0,
        )
        self.assertTrue(torch.allclose(actual, expected))

    def test_adg_wo_clip_wrapper_matches_raw(self) -> None:
        """ADG-without-clip wrapper matches raw adg_wo_clip_forward."""

        pred_cond, pred_uncond = _fixed_tensors(seed=5)
        latents, _ = _fixed_tensors(seed=55)
        state = {"latents": latents, "sigma": 0.3}
        actual = get_guidance_fn("adg_wo_clip")(pred_cond, pred_uncond, 7.0, state)
        expected = adg_wo_clip_forward(
            latents=latents,
            noise_pred_cond=pred_cond,
            noise_pred_uncond=pred_uncond,
            sigma=0.3,
            guidance_scale=7.0,
        )
        self.assertTrue(torch.allclose(actual, expected))


class GuidanceStateLifecycleTests(unittest.TestCase):
    """State dict semantics across multiple APG steps."""

    def test_momentum_state_persists_across_steps(self) -> None:
        """APG momentum buffer must accumulate across repeated wrapper calls."""

        pred_cond, pred_uncond = _fixed_tensors(seed=6)
        state: dict = {}
        fn = get_guidance_fn("apg_classic")

        buffer = MomentumBuffer()
        expected_first = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=3.0,
            momentum_buffer=buffer,
            dims=[1],
        )
        expected_second = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=3.0,
            momentum_buffer=buffer,
            dims=[1],
        )

        first = fn(pred_cond, pred_uncond, 3.0, state)
        self.assertIn(_MOMENTUM_KEY, state)
        second = fn(pred_cond, pred_uncond, 3.0, state)

        self.assertTrue(torch.allclose(first, expected_first))
        self.assertTrue(torch.allclose(second, expected_second))

    def test_state_dict_is_empty_at_fresh_call(self) -> None:
        """Each new generate_audio call should get a fresh empty state dict."""

        pred_cond, pred_uncond = _fixed_tensors(seed=7)
        fn = get_guidance_fn("apg_classic")

        first_state: dict = {}
        fn(pred_cond, pred_uncond, 3.0, first_state)
        self.assertIn(_MOMENTUM_KEY, first_state)

        second_state: dict = {}
        self.assertNotIn(_MOMENTUM_KEY, second_state)
        result = fn(pred_cond, pred_uncond, 3.0, second_state)
        self.assertIn(_MOMENTUM_KEY, second_state)
        self.assertTrue(torch.isfinite(result).all())


class GuidanceCorrectorStepTests(unittest.TestCase):
    """Corrector-step behaviour mirrors the pre-registry sampler."""

    def test_apg_corrector_falls_back_to_cfg(self) -> None:
        """APG corrector must emit cfg_forward output and must not touch momentum."""

        pred_cond, pred_uncond = _fixed_tensors(seed=8)
        state: dict = {"step_role": "corrector"}
        result = get_guidance_fn("apg_classic")(pred_cond, pred_uncond, 5.0, state)
        self.assertTrue(torch.allclose(result, cfg_forward(pred_cond, pred_uncond, 5.0)))
        self.assertNotIn(_MOMENTUM_KEY, state)

    def test_adg_corrector_at_sigma_zero_falls_back_to_cfg(self) -> None:
        """ADG corrector must degrade to CFG when sigma == 0 to avoid NaNs."""

        pred_cond, pred_uncond = _fixed_tensors(seed=9)
        latents, _ = _fixed_tensors(seed=99)
        state = {"latents": latents, "sigma": 0.0, "step_role": "corrector"}
        result = get_guidance_fn("adg")(pred_cond, pred_uncond, 5.0, state)
        self.assertTrue(torch.allclose(result, cfg_forward(pred_cond, pred_uncond, 5.0)))

    def test_adg_corrector_nonzero_sigma_runs_adg(self) -> None:
        """ADG corrector with sigma > 0 must match adg_forward output."""

        pred_cond, pred_uncond = _fixed_tensors(seed=10)
        latents, _ = _fixed_tensors(seed=100)
        state = {"latents": latents, "sigma": 0.5, "step_role": "corrector"}
        result = get_guidance_fn("adg")(pred_cond, pred_uncond, 5.0, state)
        expected = adg_forward(
            latents=latents,
            noise_pred_cond=pred_cond,
            noise_pred_uncond=pred_uncond,
            sigma=0.5,
            guidance_scale=5.0,
        )
        self.assertTrue(torch.allclose(result, expected))


if __name__ == "__main__":
    unittest.main()
