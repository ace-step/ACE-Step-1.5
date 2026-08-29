"""Service-initialization flags for the Gradio demo CLI."""

from __future__ import annotations

import argparse

from acestep.cli_args import parse_quantization_arg


def add_service_init_args(
    parser: argparse.ArgumentParser,
    *,
    auto_offload: bool,
    default_backend: str,
    default_offload_dit: bool,
    default_quantization: str | None,
) -> None:
    """Register service init, model, offload, and multi-GPU mapping flags."""
    parser.add_argument(
        "--service_mode",
        type=lambda x: x.lower() in ["true", "1", "yes"],
        default=False,
        help="Enable service mode (default: False). When enabled, uses preset models and restricts UI options.",
    )
    parser.add_argument(
        "--init_service",
        type=lambda x: x.lower() in ["true", "1", "yes"],
        default=False,
        help="Initialize service on startup (default: False)",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Checkpoint file path (optional, for display purposes)",
    )
    parser.add_argument(
        "--config_path",
        type=str,
        default=None,
        help="Main model path (e.g., 'acestep-v15-turbo')",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cuda", "mps", "xpu", "cpu"],
        help="Processing device (default: auto)",
    )
    parser.add_argument(
        "--gpu-mapping",
        dest="gpu_mapping",
        type=str,
        default=None,
        metavar="MAPPING",
        help=(
            "Component GPU layout: 'auto', 'single:N', or explicit "
            "'dit:0,vae:0,text_encoder:0,lm:1'. Also reads ACESTEP_GPU_MAPPING."
        ),
    )
    parser.add_argument(
        "--list-gpus",
        action="store_true",
        help="List visible CUDA devices and exit",
    )
    parser.add_argument(
        "--init_llm",
        type=lambda x: x.lower() in ["true", "1", "yes"],
        default=None,
        help="Initialize 5Hz LM (default: auto based on GPU memory)",
    )
    parser.add_argument(
        "--lm_model_path",
        type=str,
        default=None,
        help="5Hz LM model path (e.g., 'acestep-5Hz-lm-0.6B')",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=default_backend,
        choices=["vllm", "pt", "mlx"],
        help=(
            f"5Hz LM backend (default: {default_backend}, "
            "use 'mlx' for native Apple Silicon acceleration)"
        ),
    )
    parser.add_argument(
        "--use_flash_attention",
        type=lambda x: x.lower() in ["true", "1", "yes"],
        default=None,
        help="Use flash attention (default: auto-detect)",
    )
    parser.add_argument(
        "--offload_to_cpu",
        type=lambda x: x.lower() in ["true", "1", "yes"],
        default=auto_offload,
        help=(
            f"Offload models to CPU (default: {'True' if auto_offload else 'False'}, "
            "auto-detected based on GPU VRAM)"
        ),
    )
    parser.add_argument(
        "--offload_dit_to_cpu",
        type=lambda x: x.lower() in ["true", "1", "yes"],
        default=default_offload_dit,
        help=(
            f"Offload DiT to CPU after diffusion (default: {default_offload_dit}, "
            "auto-detected based on GPU tier)"
        ),
    )
    parser.add_argument(
        "--quantization",
        type=parse_quantization_arg,
        default=default_quantization,
        help=(
            "DiT quantization method: int8_weight_only, fp8_weight_only, "
            "w8a8_dynamic, or none "
            f"(default: {default_quantization}, auto-detected based on GPU tier)"
        ),
    )
    parser.add_argument(
        "--download-source",
        type=str,
        default=None,
        choices=["huggingface", "modelscope", "auto"],
        help="Preferred model download source (default: auto-detect based on network)",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=None,
        help="Default batch size for generation (1-8). Defaults to min(2, GPU_max) if not specified",
    )
