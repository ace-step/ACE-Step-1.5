"""Regression tests for model-aware DCW defaults in generation orchestration."""

import unittest

from acestep.core.generation.handler.generate_music_test import _Host
from acestep.inference import GenerationParams


class ModelAwareDcwDefaultTests(unittest.TestCase):
    """Verify DCW resolves from the loaded model configuration."""

    def test_generation_params_defers_dcw_default(self):
        """The request object should preserve an unspecified DCW value."""
        self.assertIsNone(GenerationParams().dcw_enabled)

    def test_non_turbo_50_step_inference_disables_dcw_by_default(self):
        """A non-Turbo 50-step request should not enable DCW implicitly."""
        host = _Host(is_turbo=False)
        host.generate_music(
            captions="cap",
            lyrics="lyr",
            inference_steps=50,
            use_random_seed=False,
            seed=77,
        )

        forwarded = host.calls["_run_generate_music_service_with_progress"]
        self.assertEqual(forwarded["inference_steps"], 50)
        self.assertFalse(forwarded["dcw_enabled"])

    def test_turbo_keeps_dcw_enabled_by_default(self):
        """Turbo's established default should remain enabled."""
        host = _Host(is_turbo=True)
        host.generate_music(
            captions="cap",
            lyrics="lyr",
            inference_steps=8,
            use_random_seed=False,
            seed=77,
        )

        self.assertTrue(host.calls["_run_generate_music_service_with_progress"]["dcw_enabled"])

    def test_explicit_non_turbo_dcw_opt_in_is_preserved(self):
        """An explicit non-Turbo DCW choice should override the default."""
        host = _Host(is_turbo=False)
        host.generate_music(
            captions="cap",
            lyrics="lyr",
            inference_steps=50,
            dcw_enabled=True,
            use_random_seed=False,
            seed=77,
        )

        self.assertTrue(host.calls["_run_generate_music_service_with_progress"]["dcw_enabled"])


if __name__ == "__main__":
    unittest.main()
