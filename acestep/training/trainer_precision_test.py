"""Unit tests for the API trainer's per-device precision selection."""

import unittest

import torch

from acestep.training.trainer import _select_compute_dtype, _select_fabric_precision


class TrainerPrecisionTests(unittest.TestCase):
    """MPS uses bfloat16. CUDA, XPU, and CPU keep their previous defaults."""

    def test_mps_uses_bfloat16(self):
        """Apple Silicon selects bfloat16 mixed precision."""
        self.assertEqual(_select_compute_dtype("mps"), torch.bfloat16)
        self.assertEqual(_select_fabric_precision("mps"), "bf16-mixed")

    def test_cuda_and_xpu_stay_on_bfloat16(self):
        """CUDA and XPU keep the bfloat16 mixed precision they already used."""
        for device_type in ("cuda", "xpu"):
            with self.subTest(device_type=device_type):
                self.assertEqual(_select_compute_dtype(device_type), torch.bfloat16)
                self.assertEqual(_select_fabric_precision(device_type), "bf16-mixed")

    def test_cpu_stays_on_fp32(self):
        """CPU training stays in float32."""
        self.assertEqual(_select_compute_dtype("cpu"), torch.float32)
        self.assertEqual(_select_fabric_precision("cpu"), "32-true")


if __name__ == "__main__":
    unittest.main()
