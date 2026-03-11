"""CLI bootstrap helpers for launching the API server process."""

from __future__ import annotations

import argparse
import os
from typing import Callable, Optional

import uvicorn


def run_api_server_main(
    env_bool: Callable[[str, bool], bool],
    argv: Optional[list[str]] = None,
) -> None:
    """Parse CLI args, set environment overrides, and start uvicorn.

    Args:
        env_bool: Boolean env parser used for defaults.
        argv: Optional explicit arg list (used by tests). Defaults to process argv.
    """

    parser = argparse.ArgumentParser(description="ACE-Step API server")
    parser.add_argument(
        "--host",
        default=os.getenv("ACESTEP_API_HOST", "127.0.0.1"),
        help="Bind host (default from ACESTEP_API_HOST or 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ACESTEP_API_PORT", "8001")),
        help="Bind port (default from ACESTEP_API_PORT or 8001)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("ACESTEP_API_KEY", None),
        help="API key for authentication (default from ACESTEP_API_KEY)",
    )
    parser.add_argument(
        "--download-source",
        type=str,
        choices=["huggingface", "modelscope", "auto"],
        default=os.getenv("ACESTEP_DOWNLOAD_SOURCE", "auto"),
        help="Preferred model download source: auto (default), huggingface, or modelscope",
    )
    parser.add_argument(
        "--init-llm",
        action="store_true",
        default=env_bool("ACESTEP_INIT_LLM", False),
        help="Initialize LLM even if GPU memory is insufficient (may cause OOM). "
        "Can also be set via ACESTEP_INIT_LLM=true environment variable.",
    )
    parser.add_argument(
        "--lm-model-path",
        type=str,
        default=os.getenv("ACESTEP_LM_MODEL_PATH", ""),
        help="LM model to load (e.g., 'acestep-5Hz-lm-0.6B'). Default from ACESTEP_LM_MODEL_PATH.",
    )
    parser.add_argument(
        "--no-init",
        action="store_true",
        default=env_bool("ACESTEP_NO_INIT", False),
        help="Skip model loading at startup (models will be lazy-loaded on first request). "
        "Can also be set via ACESTEP_NO_INIT=true environment variable.",
    )
    args = parser.parse_args(args=argv)

    if args.api_key:
        os.environ["ACESTEP_API_KEY"] = args.api_key

    if args.download_source and args.download_source != "auto":
        os.environ["ACESTEP_DOWNLOAD_SOURCE"] = args.download_source
        print(f"Using preferred download source: {args.download_source}")

    if args.init_llm:
        os.environ["ACESTEP_INIT_LLM"] = "true"
        print("[API Server] LLM initialization enabled via --init-llm")

    if args.lm_model_path:
        os.environ["ACESTEP_LM_MODEL_PATH"] = args.lm_model_path
        print(f"[API Server] Using LM model: {args.lm_model_path}")

    if args.no_init:
        os.environ["ACESTEP_NO_INIT"] = "true"
        print("[API Server] --no-init: Models will NOT be loaded at startup (lazy load on first request)")

    # IMPORTANT: in-memory queue/store -> workers MUST be 1
    uvicorn.run(
        "acestep.api_server:app",
        host=str(args.host),
        port=int(args.port),
        reload=False,
        workers=1,
    )
