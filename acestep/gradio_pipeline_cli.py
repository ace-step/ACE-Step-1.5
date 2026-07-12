"""Gradio demo CLI argument construction and GPU-mapping env wiring."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from loguru import logger

from acestep.device_map import GPU_MAPPING_ENV, format_gpu_list_text
from acestep.gradio_pipeline_cli_service import add_service_init_args
from acestep.ui.gradio.i18n import available_languages_info


def build_gradio_parser(
    *,
    auto_offload: bool,
    default_backend: str,
    default_offload_dit: bool,
    default_quantization: str | None,
) -> argparse.ArgumentParser:
    """Build the Gradio demo ArgumentParser with service and GPU-mapping flags."""
    parser = argparse.ArgumentParser(
        description="Gradio Demo for ACE-Step V1.5",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    _add_server_args(parser)
    add_service_init_args(
        parser,
        auto_offload=auto_offload,
        default_backend=default_backend,
        default_offload_dit=default_offload_dit,
        default_quantization=default_quantization,
    )
    _add_auth_and_api_args(parser)
    return parser


def apply_gpu_mapping_args(args: argparse.Namespace) -> str | None:
    """Apply ``--list-gpus`` / ``--gpu-mapping`` and return the effective mapping.

    Side effects:
        * Prints GPU inventory and exits when ``--list-gpus`` is set.
        * Writes ``ACESTEP_GPU_MAPPING`` when an explicit mapping is provided.
    """
    if args.list_gpus:
        print(format_gpu_list_text())
        sys.exit(0)

    effective = args.gpu_mapping
    if effective is None:
        return os.environ.get(GPU_MAPPING_ENV)
    if effective:
        os.environ[GPU_MAPPING_ENV] = effective
    return effective


def resolve_default_quantization(gpu_config: Any, *, is_mac: bool) -> str | None:
    """Choose the CLI default quantization method from GPU tier and capability."""
    if not gpu_config.quantization_default or is_mac:
        return None
    default = "int8_weight_only"
    try:
        import torch

        if torch.cuda.is_available():
            major, _ = torch.cuda.get_device_capability(0)
            if major < 7:
                default = "w8a8_dynamic"
    except Exception as exc:
        logger.warning(
            "[parse_args] CUDA capability probe failed while resolving "
            "quantization default: {}",
            exc,
        )
    return default


def _add_server_args(parser: argparse.ArgumentParser) -> None:
    """Register server, language, and path-related Gradio flags."""
    parser.add_argument(
        "--port", type=int, default=7860, help="Port to run the gradio server on"
    )
    parser.add_argument("--share", action="store_true", help="Create a public link")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--server-name",
        type=str,
        default="127.0.0.1",
        help="Server name (default: 127.0.0.1, use 0.0.0.0 for all interfaces)",
    )
    languages = available_languages_info()
    parser.add_argument(
        "--language",
        type=str,
        default=os.environ.get("LANGUAGE", "en"),
        choices=[language[0] for language in languages],
        help="UI language:\n  "
        + "\n  ".join(
            code
            + f" ({native_name}"
            + (f"/{name})" if name != native_name else ")")
            for code, name, native_name in languages
        ),
    )
    parser.add_argument(
        "--allowed-path",
        action="append",
        default=[],
        help="Additional allowed file paths for Gradio (repeatable).",
    )


def _add_auth_and_api_args(parser: argparse.ArgumentParser) -> None:
    """Register API enablement and Gradio authentication flags."""
    parser.add_argument(
        "--enable-api",
        action="store_true",
        help="Enable API endpoints (default: False)",
    )
    parser.add_argument(
        "--auth-username",
        type=str,
        default=None,
        help="Username for Gradio authentication",
    )
    parser.add_argument(
        "--auth-password",
        type=str,
        default=None,
        help="Password for Gradio authentication",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key for API endpoints authentication",
    )
