"""Unit tests for Gradio startup LM size safety defaults."""

from __future__ import annotations

import unittest
from argparse import Namespace

from acestep.gradio_pipeline_mode_defaults import apply_startup_mode_defaults


class StartupModeDefaultsLmSizeTests(unittest.TestCase):
    """Verify 4B LM detection does not false-match larger size tokens."""

    def test_downgrade_only_matches_hyphen_4b_token(self) -> None:
        """``-4B`` downgrades; a hypothetical ``-14B`` name must stay untouched."""
        four_b = Namespace(
            enable_api=False,
            service_mode=False,
            offload_to_cpu=False,
            lm_model_path="acestep-5Hz-lm-4B",
            config_path=None,
            backend="pt",
        )
        apply_startup_mode_defaults(four_b, gpu_memory_gb=16.0)
        self.assertEqual(four_b.lm_model_path, "acestep-5Hz-lm-1.7B")

        fourteen_b = Namespace(
            enable_api=False,
            service_mode=False,
            offload_to_cpu=False,
            lm_model_path="acestep-5Hz-lm-14B",
            config_path=None,
            backend="pt",
        )
        apply_startup_mode_defaults(fourteen_b, gpu_memory_gb=16.0)
        self.assertEqual(fourteen_b.lm_model_path, "acestep-5Hz-lm-14B")

    def test_offload_only_matches_hyphen_4b_token(self) -> None:
        """CPU offload auto-enable must key off ``-4B``, not substring ``4B``."""
        four_b = Namespace(
            enable_api=False,
            service_mode=False,
            offload_to_cpu=False,
            lm_model_path="acestep-5Hz-lm-4B",
            config_path=None,
            backend="pt",
        )
        apply_startup_mode_defaults(four_b, gpu_memory_gb=24.0)
        self.assertTrue(four_b.offload_to_cpu)

        fourteen_b = Namespace(
            enable_api=False,
            service_mode=False,
            offload_to_cpu=False,
            lm_model_path="acestep-5Hz-lm-14B",
            config_path=None,
            backend="pt",
        )
        apply_startup_mode_defaults(fourteen_b, gpu_memory_gb=24.0)
        self.assertFalse(fourteen_b.offload_to_cpu)


if __name__ == "__main__":
    unittest.main()
