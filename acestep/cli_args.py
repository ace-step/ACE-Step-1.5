"""Argument parsing helpers shared by ACE-Step CLI entrypoints."""

from __future__ import annotations

import argparse

_QUANTIZATION_ALIASES = {
    "int8_weight_only": "int8_weight_only",
    "fp8_weight_only": "fp8_weight_only",
    "w8a8_dynamic": "w8a8_dynamic",
}
_NONE_ALIASES = {"", "none", "null"}


def parse_quantization_arg(value: str | None) -> str | None:
    """Parse ``--quantization`` values from CLI input.

    Args:
        value: Raw CLI value.

    Returns:
        Canonical quantization method or ``None`` for disabled quantization.

    Raises:
        argparse.ArgumentTypeError: If the value is not supported.
    """
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in _NONE_ALIASES:
        return None

    quantization = _QUANTIZATION_ALIASES.get(normalized)
    if quantization is not None:
        return quantization

    raise argparse.ArgumentTypeError(
        "Invalid quantization value. Use int8_weight_only, fp8_weight_only, "
        "w8a8_dynamic, or none."
    )
