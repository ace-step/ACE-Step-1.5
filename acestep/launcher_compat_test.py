"""Unit tests for launcher compatibility decision logic."""

from __future__ import annotations

import types
import unittest

from acestep.launcher_compat import (
    LEGACY_TORCH_FIX_EXIT_CODE,
    determine_legacy_torch_fix,
    evaluate_legacy_torch_fix,
    legacy_torch_fix_probe_exit_code,
)


def _make_torch(
    *,
    cuda_available: bool,
    capability: tuple[int, int] = (6, 1),
    arch_list: list[str] | None = None,
) -> types.SimpleNamespace:
    """Create a minimal torch test double for compatibility checks."""
    cuda = types.SimpleNamespace(
        is_available=lambda: cuda_available,
        get_device_capability=lambda _idx=0: capability,
        get_arch_list=lambda: arch_list or [],
    )
    return types.SimpleNamespace(cuda=cuda)


class LauncherCompatDecisionTests(unittest.TestCase):
    """Validate decision logic for legacy torch compatibility fixes."""

    def test_legacy_arch_missing_requires_fix(self) -> None:
        """It requests fix when legacy GPU arch is missing from torch wheel."""
        torch_module = _make_torch(cuda_available=True, capability=(6, 1), arch_list=["sm_70"])
        decision = evaluate_legacy_torch_fix(torch_module)
        self.assertTrue(decision.should_apply)
        self.assertEqual("legacy_arch_missing", decision.reason)
        self.assertEqual("sm_61", decision.device_arch)

    def test_legacy_arch_present_skips_fix(self) -> None:
        """It skips fix when legacy arch is already supported."""
        torch_module = _make_torch(cuda_available=True, capability=(6, 1), arch_list=["sm_61", "sm_70"])
        decision = evaluate_legacy_torch_fix(torch_module)
        self.assertFalse(decision.should_apply)
        self.assertEqual("compatible_arch", decision.reason)
        self.assertEqual("sm_61", decision.device_arch)

    def test_modern_gpu_skips_fix_even_if_arch_not_listed(self) -> None:
        """It does not apply legacy fix for modern GPUs."""
        torch_module = _make_torch(cuda_available=True, capability=(8, 6), arch_list=["sm_70"])
        decision = evaluate_legacy_torch_fix(torch_module)
        self.assertFalse(decision.should_apply)
        self.assertEqual("compatible_arch", decision.reason)
        self.assertEqual("sm_86", decision.device_arch)

    def test_no_cuda_skips_fix(self) -> None:
        """It skips fix when CUDA is unavailable."""
        torch_module = _make_torch(cuda_available=False)
        decision = evaluate_legacy_torch_fix(torch_module)
        self.assertFalse(decision.should_apply)
        self.assertEqual("cuda_unavailable", decision.reason)
        self.assertIsNone(decision.device_arch)

    def test_determine_returns_probe_failed_on_exception(self) -> None:
        """It returns a safe no-fix decision when probing raises."""
        broken_cuda = types.SimpleNamespace(
            is_available=lambda: True,
            get_device_capability=lambda _idx=0: (_ for _ in ()).throw(RuntimeError("boom")),
            get_arch_list=lambda: [],
        )
        decision = determine_legacy_torch_fix(types.SimpleNamespace(cuda=broken_cuda))
        self.assertFalse(decision.should_apply)
        self.assertEqual("probe_failed", decision.reason)

    def test_probe_exit_code_maps_to_decision(self) -> None:
        """Probe exit code is 42 for required-fix and probe-failure cases, else 0."""
        needs_fix = _make_torch(cuda_available=True, capability=(6, 1), arch_list=["sm_70"])
        ok = _make_torch(cuda_available=True, capability=(8, 0), arch_list=["sm_80"])
        broken_cuda = types.SimpleNamespace(
            is_available=lambda: True,
            get_device_capability=lambda _idx=0: (_ for _ in ()).throw(RuntimeError("boom")),
            get_arch_list=lambda: [],
        )
        self.assertEqual(LEGACY_TORCH_FIX_EXIT_CODE, legacy_torch_fix_probe_exit_code(needs_fix))
        self.assertEqual(0, legacy_torch_fix_probe_exit_code(ok))
        failed_exit = legacy_torch_fix_probe_exit_code(types.SimpleNamespace(cuda=broken_cuda))
        self.assertNotEqual(0, failed_exit)
        self.assertEqual(LEGACY_TORCH_FIX_EXIT_CODE, failed_exit)


if __name__ == "__main__":
    unittest.main()
