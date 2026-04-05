"""
fixed subcommand -- Corrected training: continuous timesteps + CFG dropout.

Uses ``FixedLoRATrainer`` which matches each model variant's own
``forward()`` training logic:

    - Continuous logit-normal timestep sampling via ``sample_timesteps()``
    - CFG dropout (``cfg_ratio=0.15``) using ``model.null_condition_emb``
    - ``r = t`` (``use_meanflow=False``)
    - Reads ``timestep_mu``, ``timestep_sigma``, ``data_proportion``
      from the model's ``config.json``

Reuses the same data pipeline (``PreprocessedDataModule``) and LoRA
utilities (``inject_lora_into_dit``, ``save_lora_weights``, etc.) as
the vanilla subcommand.

Standalone entrypoint::

    python -m acestep.training_v2.cli.train_fixed [args]

Equivalent to::

    python train.py fixed [args]
"""

from __future__ import annotations

import argparse
import gc
import sys
import traceback

from acestep.training_v2.cli.common import build_configs
from acestep.training_v2.model_loader import load_decoder_for_training
from acestep.training_v2.trainer_fixed import FixedLoRATrainer


def _cleanup_gpu() -> None:
    """Release GPU memory so the process can safely reuse it."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def run_fixed(args: argparse.Namespace) -> int:
    """Execute the fixed (corrected) training subcommand.

    Returns 0 on success, non-zero on failure.
    """
    import torch

    # -- UI setup -------------------------------------------------------------
    from acestep.training_v2.ui import set_plain_mode
    from acestep.training_v2.ui.banner import show_banner
    from acestep.training_v2.ui.config_panel import show_config, confirm_start
    from acestep.training_v2.ui.errors import handle_error, show_info
    from acestep.training_v2.ui.progress import track_training
    from acestep.training_v2.ui.summary import show_summary

    if getattr(args, "plain", False):
        set_plain_mode(True)

    # -- Matmul precision (matches handler.initialize_service behaviour) ------
    torch.set_float32_matmul_precision("medium")

    # -- Build V2 config objects from CLI args --------------------------------
    adapter_cfg, train_cfg = build_configs(args)

    # -- Banner (skip if wizard already showed one) ---------------------------
    if not getattr(args, "_from_wizard", False):
        show_banner(
            subcommand="fixed",
            device=train_cfg.device,
            precision=train_cfg.precision,
        )

    # -- Config summary & confirmation (always shown) -----------------------
    show_config(adapter_cfg, train_cfg, subcommand="fixed")
    skip_confirm = getattr(args, "yes", False)
    if not confirm_start(skip=skip_confirm):
        return 0

    model = None
    trainer = None
    try:
        # -- Load model -------------------------------------------------------
        try:
            show_info(f"Loading model (variant={train_cfg.model_variant}, device={train_cfg.device})")
            model = load_decoder_for_training(
                checkpoint_dir=train_cfg.checkpoint_dir,
                variant=train_cfg.model_variant,
                device=train_cfg.device,
                precision=train_cfg.precision,
            )
        except Exception as exc:
            handle_error(exc, context="Model loading", show_traceback=True)
            return 1

        # -- Train ------------------------------------------------------------
        try:
            trainer = FixedLoRATrainer(model, adapter_cfg, train_cfg)

            stats = track_training(
                training_iter=trainer.train(),
                max_epochs=train_cfg.max_epochs,
                device=train_cfg.device,
            )

            # -- Summary ------------------------------------------------------
            show_summary(
                stats=stats,
                output_dir=train_cfg.output_dir,
                log_dir=str(train_cfg.effective_log_dir),
            )
        except KeyboardInterrupt:
            show_info("Training interrupted by user (Ctrl+C)")
            return 130
        except Exception as exc:
            handle_error(exc, context="Training", show_traceback=True)
            return 1

        return 0
    finally:
        # Explicitly release GPU memory so the session loop can reuse it.
        del trainer
        del model
        _cleanup_gpu()


def _run_preprocess(args: argparse.Namespace) -> int:
    """Run the two-pass preprocessing pipeline from the standalone entrypoint.

    Args:
        args: Parsed CLI arguments with ``audio_dir``, ``tensor_output``,
              ``checkpoint_dir``, ``model_variant``, ``max_duration``,
              ``device``, and ``precision`` attributes.

    Returns:
        0 on success, 1 on failure.
    """
    from acestep.training_v2.preprocess import preprocess_audio_files

    audio_dir = args.audio_dir
    dataset_json = args.dataset_json
    tensor_output = args.tensor_output

    if not audio_dir and not dataset_json:
        print("[FAIL] --audio-dir or --dataset-json is required for preprocessing.", file=sys.stderr)
        return 1
    if not tensor_output:
        print("[FAIL] --tensor-output is required for preprocessing.", file=sys.stderr)
        return 1

    source_label = dataset_json if dataset_json else audio_dir
    print("\n" + "=" * 60)
    print("  Preprocessing Summary")
    print("=" * 60)
    print(f"  Source:        {source_label}")
    print(f"  Output:        {tensor_output}")
    print(f"  Checkpoint:    {args.checkpoint_dir}")
    print(f"  Model variant: {args.model_variant}")
    print(f"  Max duration:  {args.max_duration}s")
    print("=" * 60)
    print("[INFO] Two-pass pipeline (sequential model loading for low VRAM)")

    try:
        result = preprocess_audio_files(
            audio_dir=audio_dir,
            output_dir=tensor_output,
            checkpoint_dir=args.checkpoint_dir,
            variant=args.model_variant,
            max_duration=args.max_duration,
            dataset_json=dataset_json,
            device=args.device,
            precision=args.precision,
        )
    except Exception as exc:
        print(f"[FAIL] Preprocessing failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1
    finally:
        _cleanup_gpu()

    print("\n[OK] Preprocessing complete:")
    print(f"     Processed: {result['processed']}/{result['total']}")
    if result["failed"]:
        print(f"     Failed:    {result['failed']}")
    print(f"     Output:    {result['output_dir']}")
    print("\n[INFO] You can now train with:")
    print(f"       python -m acestep.training_v2.cli.train_fixed --dataset-dir {result['output_dir']} ...")
    return 0


def main() -> int:
    """Standalone CLI entry point for the ``fixed`` training subcommand.

    Supports invocation as ``python -m acestep.training_v2.cli.train_fixed``,
    which is equivalent to ``python train.py fixed``.  Handles both normal
    training and the ``--preprocess`` preprocessing mode.

    Returns:
        Integer exit code: 0 on success, non-zero on failure.
    """
    from acestep.training_v2.cli.args import build_fixed_standalone_parser
    from acestep.training_v2.cli.validation import validate_paths

    parser = build_fixed_standalone_parser()
    args = parser.parse_args()
    args.subcommand = "fixed"

    if args.preprocess:
        return _run_preprocess(args)

    if not validate_paths(args):
        return 1

    return run_fixed(args)


if __name__ == "__main__":
    sys.exit(main())
