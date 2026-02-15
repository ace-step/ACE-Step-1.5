"""
Argparse construction for ACE-Step Training V2 CLI.

Contains ``build_root_parser`` and all ``_add_*`` argument-group helpers,
plus shared constants (``_DEFAULT_NUM_WORKERS``, ``VARIANT_DIR_MAP``).
"""

from __future__ import annotations

import argparse
import sys

# Windows uses spawn-based multiprocessing which breaks DataLoader workers
_DEFAULT_NUM_WORKERS = 0 if sys.platform == "win32" else 4

# Model variant -> checkpoint subdirectory mapping
VARIANT_DIR_MAP = {
    "turbo": "acestep-v15-turbo",
    "base": "acestep-v15-base",
    "sft": "acestep-v15-sft",
}


# ===========================================================================
# Root parser
# ===========================================================================

def build_root_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser with all subcommands."""

    formatter_class = argparse.HelpFormatter
    try:
        from acestep.training_v2.ui.help_formatter import RichHelpFormatter
        formatter_class = RichHelpFormatter
    except ImportError:
        pass

    root = argparse.ArgumentParser(
        prog="train.py",
        description="ACE-Step Training V2 -- corrected LoRA fine-tuning CLI",
        formatter_class=formatter_class,
    )

    root.add_argument(
        "--plain",
        action="store_true",
        default=False,
        help="Disable Rich output; use plain text (also set automatically when stdout is not a TTY)",
    )
    root.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Skip the confirmation prompt and start training immediately",
    )

    subparsers = root.add_subparsers(dest="subcommand", required=True)

    # -- vanilla -------------------------------------------------------------
    p_vanilla = subparsers.add_parser(
        "vanilla",
        help="Reproduce existing (bugged) training for backward compatibility",
        formatter_class=formatter_class,
    )
    _add_common_training_args(p_vanilla)

    # -- fixed ---------------------------------------------------------------
    p_fixed = subparsers.add_parser(
        "fixed",
        help="Corrected training: continuous timesteps + CFG dropout",
        formatter_class=formatter_class,
    )
    _add_common_training_args(p_fixed)
    _add_fixed_args(p_fixed)

    # -- estimate ------------------------------------------------------------
    p_estimate = subparsers.add_parser(
        "estimate",
        help="Gradient sensitivity analysis (no training)",
        formatter_class=formatter_class,
    )
    _add_model_args(p_estimate)
    _add_device_args(p_estimate)
    _add_estimation_args(p_estimate)
    p_estimate.add_argument(
        "--dataset-dir",
        type=str,
        required=True,
        help="Directory containing preprocessed .pt files",
    )
    p_estimate.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Batch size for estimation forward passes (default: 1)",
    )
    p_estimate.add_argument(
        "--num-workers",
        type=int,
        default=_DEFAULT_NUM_WORKERS,
        help=f"DataLoader workers (default: {_DEFAULT_NUM_WORKERS}; 0 on Windows)",
    )
    p_estimate.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )

    return root


# ===========================================================================
# Argument groups
# ===========================================================================

def _add_model_args(parser: argparse.ArgumentParser) -> None:
    """Add --checkpoint-dir, --model-variant, and --base-model."""
    g = parser.add_argument_group("Model / paths")
    g.add_argument(
        "--checkpoint-dir",
        type=str,
        required=True,
        help="Path to checkpoints root directory",
    )
    g.add_argument(
        "--model-variant",
        type=str,
        default="turbo",
        help=(
            "Model variant or subfolder name (default: turbo). "
            "Official: turbo, base, sft. "
            "For fine-tunes: use the exact folder name under checkpoint-dir."
        ),
    )
    g.add_argument(
        "--base-model",
        type=str,
        default=None,
        choices=["turbo", "base", "sft"],
        help=(
            "Base model a fine-tune was trained from (turbo/base/sft). "
            "Used to condition timestep sampling. Auto-detected for official models."
        ),
    )


def _add_device_args(parser: argparse.ArgumentParser) -> None:
    """Add --device and --precision."""
    g = parser.add_argument_group("Device / platform")
    g.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device: auto, cuda, cuda:0, mps, xpu, cpu (default: auto)",
    )
    g.add_argument(
        "--precision",
        type=str,
        default="auto",
        choices=["auto", "bf16", "fp16", "fp32"],
        help="Precision: auto, bf16, fp16, fp32 (default: auto)",
    )


def _add_common_training_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by vanilla / fixed subcommands."""
    _add_model_args(parser)
    _add_device_args(parser)

    # -- Data ----------------------------------------------------------------
    g_data = parser.add_argument_group("Data")
    g_data.add_argument(
        "--dataset-dir",
        type=str,
        required=True,
        help="Directory containing preprocessed .pt files",
    )
    g_data.add_argument(
        "--num-workers",
        type=int,
        default=_DEFAULT_NUM_WORKERS,
        help=f"DataLoader workers (default: {_DEFAULT_NUM_WORKERS}; 0 on Windows)",
    )
    g_data.add_argument(
        "--pin-memory",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pin memory for GPU transfer (default: True)",
    )
    g_data.add_argument(
        "--prefetch-factor",
        type=int,
        default=2 if _DEFAULT_NUM_WORKERS > 0 else 0,
        help="DataLoader prefetch factor (default: 2; 0 on Windows)",
    )
    g_data.add_argument(
        "--persistent-workers",
        action=argparse.BooleanOptionalAction,
        default=_DEFAULT_NUM_WORKERS > 0,
        help="Keep workers alive between epochs (default: True; False on Windows)",
    )

    # -- Training hyperparams ------------------------------------------------
    g_train = parser.add_argument_group("Training")
    g_train.add_argument("--lr", "--learning-rate", type=float, default=1e-4, dest="learning_rate", help="Initial learning rate (default: 1e-4)")
    g_train.add_argument("--batch-size", type=int, default=1, help="Training batch size (default: 1)")
    g_train.add_argument("--gradient-accumulation", type=int, default=4, help="Gradient accumulation steps (default: 4)")
    g_train.add_argument("--epochs", type=int, default=100, help="Maximum training epochs (default: 100)")
    g_train.add_argument("--warmup-steps", type=int, default=100, help="LR warmup steps (default: 100)")
    g_train.add_argument("--weight-decay", type=float, default=0.01, help="AdamW weight decay (default: 0.01)")
    g_train.add_argument("--max-grad-norm", type=float, default=1.0, help="Gradient clipping norm (default: 1.0)")
    g_train.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    g_train.add_argument("--shift", type=float, default=3.0, help="Noise schedule shift (turbo=3.0, base/sft=1.0)")
    g_train.add_argument("--num-inference-steps", type=int, default=8, help="Inference steps for timestep schedule (turbo=8, base/sft=50)")
    g_train.add_argument("--optimizer-type", type=str, default="adamw", choices=["adamw", "adamw8bit", "adafactor", "prodigy"], help="Optimizer (default: adamw)")
    g_train.add_argument("--scheduler-type", type=str, default="cosine", choices=["cosine", "cosine_restarts", "linear", "constant", "constant_with_warmup"], help="LR scheduler (default: cosine)")
    g_train.add_argument("--gradient-checkpointing", action=argparse.BooleanOptionalAction, default=True, help="Recompute activations to save VRAM (~40-60%% less, ~10-30%% slower). On by default; use --no-gradient-checkpointing to disable")
    g_train.add_argument("--offload-encoder", action=argparse.BooleanOptionalAction, default=False, help="Move encoder/VAE to CPU after setup (saves ~2-4GB VRAM)")

    # -- Adapter selection ---------------------------------------------------
    g_adapter = parser.add_argument_group("Adapter")
    g_adapter.add_argument("--adapter-type", type=str, default="lora", choices=["lora", "lokr"], help="Adapter type: lora (PEFT) or lokr (LyCORIS) (default: lora)")

    # -- LoRA hyperparams ---------------------------------------------------
    g_lora = parser.add_argument_group("LoRA (used when --adapter-type=lora)")
    g_lora.add_argument("--rank", "-r", type=int, default=64, help="LoRA rank (default: 64)")
    g_lora.add_argument("--alpha", type=int, default=128, help="LoRA alpha (default: 128)")
    g_lora.add_argument("--dropout", type=float, default=0.1, help="LoRA dropout (default: 0.1)")
    g_lora.add_argument("--target-modules", nargs="+", default=["q_proj", "k_proj", "v_proj", "o_proj"], help="Modules to apply adapter to")
    g_lora.add_argument("--bias", type=str, default="none", choices=["none", "all", "lora_only"], help="Bias training mode (default: none)")
    g_lora.add_argument("--attention-type", type=str, default="both", choices=["self", "cross", "both"], help="Attention layers to target (default: both)")

    # -- LoKR hyperparams ---------------------------------------------------
    g_lokr = parser.add_argument_group("LoKR (used when --adapter-type=lokr)")
    g_lokr.add_argument("--lokr-linear-dim", type=int, default=64, help="LoKR linear dimension (default: 64)")
    g_lokr.add_argument("--lokr-linear-alpha", type=int, default=128, help="LoKR linear alpha (default: 128)")
    g_lokr.add_argument("--lokr-factor", type=int, default=-1, help="LoKR factor; -1 for auto (default: -1)")
    g_lokr.add_argument("--lokr-decompose-both", action="store_true", default=False, help="Decompose both Kronecker factors")
    g_lokr.add_argument("--lokr-use-tucker", action="store_true", default=False, help="Use Tucker decomposition")
    g_lokr.add_argument("--lokr-use-scalar", action="store_true", default=False, help="Use scalar scaling")
    g_lokr.add_argument("--lokr-weight-decompose", action="store_true", default=False, help="Enable DoRA-style weight decomposition")

    # -- Checkpointing -------------------------------------------------------
    g_ckpt = parser.add_argument_group("Checkpointing")
    g_ckpt.add_argument("--output-dir", type=str, required=True, help="Output directory for LoRA weights")
    g_ckpt.add_argument("--save-every", type=int, default=10, help="Save checkpoint every N epochs (default: 10)")
    g_ckpt.add_argument("--resume-from", type=str, default=None, help="Path to checkpoint dir to resume from")

    # -- Logging / TensorBoard -----------------------------------------------
    g_log = parser.add_argument_group("Logging / TensorBoard")
    g_log.add_argument("--log-dir", type=str, default=None, help="TensorBoard log directory (default: {output-dir}/runs)")
    g_log.add_argument("--log-every", type=int, default=10, help="Log basic metrics every N steps (default: 10)")
    g_log.add_argument("--log-heavy-every", type=int, default=50, help="Log per-layer gradient norms every N steps (default: 50)")
    g_log.add_argument("--sample-every-n-epochs", type=int, default=0, help="Generate audio sample every N epochs; 0=disabled (default: 0)")

    # -- Preprocessing -------------------------------------------------------
    g_pre = parser.add_argument_group("Preprocessing")
    g_pre.add_argument("--preprocess", action="store_true", default=False, help="Run preprocessing before training")
    g_pre.add_argument("--audio-dir", type=str, default=None, help="Source audio directory (preprocessing)")
    g_pre.add_argument("--dataset-json", type=str, default=None, help="Labeled dataset JSON file (preprocessing)")
    g_pre.add_argument("--tensor-output", type=str, default=None, help="Output directory for .pt tensor files (preprocessing)")
    g_pre.add_argument("--max-duration", type=float, default=240.0, help="Max audio duration in seconds (default: 240)")


def _add_fixed_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments specific to the fixed subcommand."""
    g = parser.add_argument_group("Corrected training")
    g.add_argument("--cfg-ratio", type=float, default=0.15, help="CFG dropout probability (default: 0.15)")



def _add_estimation_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for the estimate subcommand."""
    g = parser.add_argument_group("Estimation")
    g.add_argument("--estimate-batches", type=int, default=None, help="Number of batches for estimation (default: auto from GPU)")
    g.add_argument("--top-k", type=int, default=16, help="Number of top modules to select (default: 16)")
    g.add_argument("--granularity", type=str, default="module", choices=["layer", "module"], help="Estimation granularity (default: module)")
    g.add_argument("--output", type=str, default=None, dest="estimate_output", help="Path to write module config JSON (estimate only)")
