"""API/service-mode defaults and 4B LM safety rules for Gradio startup."""

from __future__ import annotations

import argparse
import os

from acestep.gpu_config import VRAM_AUTO_OFFLOAD_THRESHOLD_GB


def apply_startup_mode_defaults(args: argparse.Namespace, gpu_memory_gb: float) -> None:
    """Apply API/service-mode env defaults and 4B LM offload safety rules."""
    if args.enable_api:
        args.init_service = True
        if args.config_path is None:
            args.config_path = os.environ.get("ACESTEP_CONFIG_PATH")
        if args.lm_model_path is None:
            args.lm_model_path = os.environ.get("ACESTEP_LM_MODEL_PATH")
        if os.environ.get("ACESTEP_LM_BACKEND"):
            args.backend = os.environ.get("ACESTEP_LM_BACKEND")

    if args.service_mode:
        print("Service mode enabled - applying preset configurations...")
        args.init_service = True
        if args.config_path is None:
            args.config_path = os.environ.get(
                "SERVICE_MODE_DIT_MODEL", "acestep-v15-turbo-fix-inst-shift-dynamic"
            )
        if args.lm_model_path is None:
            args.lm_model_path = os.environ.get(
                "SERVICE_MODE_LM_MODEL", "acestep-5Hz-lm-1.7B-v4-fix"
            )
        args.backend = os.environ.get("SERVICE_MODE_BACKEND", "vllm")
        print(f"  DiT model: {args.config_path}")
        print(f"  LM model: {args.lm_model_path}")

    if not args.offload_to_cpu and args.lm_model_path and "4B" in args.lm_model_path:
        if 0 < gpu_memory_gb <= 24:
            args.offload_to_cpu = True
            print(
                f"Auto-enabling CPU offload (4B LM model requires offloading "
                f"on {gpu_memory_gb:.0f}GB GPU)"
            )

    if args.lm_model_path and 0 < gpu_memory_gb < VRAM_AUTO_OFFLOAD_THRESHOLD_GB:
        if "4B" in args.lm_model_path:
            fallback = args.lm_model_path.replace("4B", "1.7B")
            print(
                f"WARNING: 4B LM model is too large for {gpu_memory_gb:.0f}GB GPU. "
                f"Downgrading to 1.7B variant: {fallback}"
            )
            args.lm_model_path = fallback
