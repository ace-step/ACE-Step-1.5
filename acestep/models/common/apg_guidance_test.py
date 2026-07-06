"""Unit tests for APG guidance helpers."""

from __future__ import annotations

import unittest

import torch

from acestep.models.common.apg_guidance import MomentumBuffer, apg_forward, project


class ApgGuidanceDeviceTests(unittest.TestCase):
    """Verify guidance math preserves tensor device placement."""

    def test_project_preserves_cpu_device(self):
        v0 = torch.randn(2, 4, 8)
        v1 = torch.randn(2, 4, 8)
        parallel, orthogonal = project(v0, v1, dims=[1])
        self.assertEqual(parallel.device, v0.device)
        self.assertEqual(orthogonal.device, v0.device)

    def test_apg_forward_preserves_cpu_device(self):
        pred_cond = torch.randn(2, 4, 8)
        pred_uncond = pred_cond + 0.25
        guided = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=7.0,
            momentum_buffer=MomentumBuffer(),
            dims=[1],
        )
        self.assertEqual(guided.device, pred_cond.device)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_project_preserves_non_default_cuda_index(self):
        if torch.cuda.device_count() < 2:
            self.skipTest("Need at least 2 CUDA devices")
        device = torch.device("cuda:1")
        v0 = torch.randn(2, 4, 8, device=device)
        v1 = torch.randn(2, 4, 8, device=device)
        parallel, orthogonal = project(v0, v1, dims=[1])
        self.assertEqual(parallel.device, device)
        self.assertEqual(orthogonal.device, device)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_apg_forward_preserves_non_default_cuda_index(self):
        if torch.cuda.device_count() < 2:
            self.skipTest("Need at least 2 CUDA devices")
        device = torch.device("cuda:1")
        pred_cond = torch.randn(2, 4, 8, device=device)
        pred_uncond = pred_cond + 0.25
        guided = apg_forward(
            pred_cond=pred_cond,
            pred_uncond=pred_uncond,
            guidance_scale=7.0,
            momentum_buffer=MomentumBuffer(),
            dims=[1],
        )
        self.assertEqual(guided.device, device)


if __name__ == "__main__":
    unittest.main()
