"""
Path validation and target-module resolution for ACE-Step Training V2 CLI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from acestep.training_v2.cli.args import VARIANT_DIR_MAP


def validate_paths(args: argparse.Namespace) -> bool:
    """Validate that required paths exist and attach the resolved model dir.

    On success, sets ``args.model_dir`` to the resolved ``Path`` so that
    callers can consume it directly.  Returns ``True`` if all OK.

    Prints ``[FAIL]`` messages and returns ``False`` on the first error.
    """
    # All subcommands need checkpoint-dir
    ckpt_root = Path(args.checkpoint_dir)
    if not ckpt_root.is_dir():
        print(f"[FAIL] Checkpoint directory not found: {ckpt_root}", file=sys.stderr)
        return False

    # Resolve model directory: try known alias first, then literal folder name
    variant_dir = VARIANT_DIR_MAP.get(args.model_variant)
    if variant_dir and (ckpt_root / variant_dir).is_dir():
        model_dir = ckpt_root / variant_dir
    elif (ckpt_root / args.model_variant).is_dir():
        model_dir = ckpt_root / args.model_variant
    else:
        tried = variant_dir or args.model_variant
        print(
            f"[FAIL] Model directory not found: {ckpt_root / tried}\n"
            f"       Looked for '{tried}' under {ckpt_root}",
            file=sys.stderr,
        )
        return False

    # Attach resolved path so callers can use it directly
    args.model_dir = model_dir

    # Dataset dir
    ds_dir = getattr(args, "dataset_dir", None)
    if ds_dir is not None and not Path(ds_dir).is_dir():
        print(f"[FAIL] Dataset directory not found: {ds_dir}", file=sys.stderr)
        return False

    # Resume path
    resume = getattr(args, "resume_from", None)
    if resume is not None and not Path(resume).exists():
        print(f"[WARN] Resume path not found (will train from scratch): {resume}", file=sys.stderr)

    return True


def resolve_target_modules(target_modules: list, attention_type: str) -> list:
    """Resolve target modules based on attention type selection.

    Args:
        target_modules: List of module patterns (e.g. ["q_proj", "v_proj"])
        attention_type: One of "self", "cross", or "both"

    Returns:
        Resolved list of module patterns with appropriate prefixes.

    Examples:
        resolve_target_modules(["q_proj", "v_proj"], "both")
        -> ["q_proj", "v_proj"]  # unchanged, PEFT matches all

        resolve_target_modules(["q_proj", "v_proj"], "self")
        -> ["self_attn.q_proj", "self_attn.v_proj"]

        resolve_target_modules(["q_proj", "v_proj"], "cross")
        -> ["cross_attn.q_proj", "cross_attn.v_proj"]
    """
    if attention_type == "both":
        return target_modules

    prefix_map = {
        "self": "self_attn",
        "cross": "cross_attn",
    }
    prefix = prefix_map.get(attention_type)
    if prefix is None:
        return target_modules

    resolved = []
    for mod in target_modules:
        if "." in mod:
            resolved.append(mod)
        else:
            resolved.append(f"{prefix}.{mod}")

    return resolved
