"""Launcher compatibility helpers for hardware-specific startup fixes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


LEGACY_TORCH_FIX_EXIT_CODE = 42


@dataclass(frozen=True)
class LegacyTorchFixDecision:
    """Decision payload for whether launcher should apply legacy torch fix.

    Attributes:
        should_apply: Whether compatibility fix should be applied.
        reason: Short machine-readable reason for decision.
        device_arch: CUDA architecture string (for example, ``sm_61``) when available.
    """

    should_apply: bool
    reason: str
    device_arch: str | None = None


def evaluate_legacy_torch_fix(torch_module: Any) -> LegacyTorchFixDecision:
    """Evaluate legacy GPU compatibility using an injected torch-like module.

    Args:
        torch_module: Imported ``torch`` module or a test double exposing
            ``cuda.is_available()``, ``cuda.get_device_capability()``, and
            ``cuda.get_arch_list()``.

    Returns:
        Compatibility decision indicating whether to apply legacy torch wheels.
    """
    cuda = getattr(torch_module, "cuda", None)
    if cuda is None or not cuda.is_available():
        return LegacyTorchFixDecision(False, "cuda_unavailable")

    major, minor = cuda.get_device_capability(0)
    device_arch = f"sm_{major}{minor}"
    supported_arches = set(cuda.get_arch_list() or [])

    if major < 7 and device_arch not in supported_arches:
        return LegacyTorchFixDecision(True, "legacy_arch_missing", device_arch=device_arch)

    return LegacyTorchFixDecision(False, "compatible_arch", device_arch=device_arch)


def determine_legacy_torch_fix(torch_module: Any | None = None) -> LegacyTorchFixDecision:
    """Determine whether legacy torch compatibility patch is required.

    Args:
        torch_module: Optional injected ``torch`` module for tests.

    Returns:
        Compatibility decision payload.
    """
    if torch_module is None:
        try:
            import torch as imported_torch
        except Exception:
            return LegacyTorchFixDecision(False, "torch_unavailable")
        torch_module = imported_torch

    try:
        return evaluate_legacy_torch_fix(torch_module)
    except Exception:
        return LegacyTorchFixDecision(False, "probe_failed")


def legacy_torch_fix_probe_exit_code(torch_module: Any | None = None) -> int:
    """Return launcher probe exit code for legacy torch compatibility check.

    Args:
        torch_module: Optional injected ``torch`` module for tests.

    Returns:
        ``LEGACY_TORCH_FIX_EXIT_CODE`` when fix should be applied or the probe
        itself fails, otherwise ``0``.
    """
    decision = determine_legacy_torch_fix(torch_module=torch_module)
    if decision.should_apply or decision.reason == "probe_failed":
        return LEGACY_TORCH_FIX_EXIT_CODE
    return 0
