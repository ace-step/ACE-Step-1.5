"""Gradio demo startup: CLI DiT/LM model initialization."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Optional

from acestep.device_map import log_lm_device_deprecation
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.model_downloader import ensure_lm_model


def initialize_from_cli(
    args: argparse.Namespace,
    *,
    gpu_config: Any,
    effective_gpu_mapping: Optional[str],
    project_root: str,
    output_dir: str,
) -> tuple[dict[str, Any], AceStepHandler, LLMHandler]:
    """Initialize DiT/LM handlers from CLI args and return UI init_params."""
    print("Initializing service from command line...")
    dit_handler = AceStepHandler()
    llm_handler = LLMHandler()

    if args.config_path is None:
        available_models = dit_handler.get_available_acestep_v15_models()
        if not available_models:
            print(
                "Error: No available models found. Please specify --config_path",
                file=sys.stderr,
            )
            sys.exit(1)
        args.config_path = (
            "acestep-v15-turbo"
            if "acestep-v15-turbo" in available_models
            else available_models[0]
        )
        print(f"Auto-selected config_path: {args.config_path}")

    use_flash_attention = args.use_flash_attention
    if use_flash_attention is None:
        use_flash_attention = dit_handler.is_flash_attention_available(args.device)

    prefer_source = None
    if args.download_source and args.download_source != "auto":
        prefer_source = args.download_source
        print(f"Using preferred download source: {prefer_source}")

    print(f"Initializing DiT model: {args.config_path} on {args.device}...")
    compile_model = os.environ.get("ACESTEP_COMPILE_MODEL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    init_status, enable_generate = dit_handler.initialize_service(
        project_root=project_root,
        config_path=args.config_path,
        device=args.device,
        use_flash_attention=use_flash_attention,
        compile_model=compile_model,
        offload_to_cpu=args.offload_to_cpu,
        offload_dit_to_cpu=args.offload_dit_to_cpu,
        quantization=args.quantization,
        prefer_source=prefer_source,
        gpu_mapping=effective_gpu_mapping,
    )
    if not enable_generate:
        print(f"Error initializing DiT model: {init_status}", file=sys.stderr)
        sys.exit(1)
    print("DiT model initialized successfully")

    if args.init_llm is None:
        args.init_llm = gpu_config.init_lm_default
        print(f"Auto-setting init_llm to {args.init_llm} based on GPU configuration")

    if args.init_llm:
        init_status = _initialize_lm_from_cli(
            args,
            dit_handler=dit_handler,
            llm_handler=llm_handler,
            project_root=project_root,
            effective_gpu_mapping=effective_gpu_mapping,
            init_status=init_status,
            prefer_source=prefer_source,
        )

    init_params = {
        "pre_initialized": True,
        "service_mode": args.service_mode,
        "checkpoint": args.checkpoint,
        "config_path": args.config_path,
        "device": args.device,
        "gpu_mapping": effective_gpu_mapping,
        "init_llm": args.init_llm,
        "lm_model_path": args.lm_model_path,
        "backend": args.backend,
        "use_flash_attention": use_flash_attention,
        "offload_to_cpu": args.offload_to_cpu,
        "offload_dit_to_cpu": args.offload_dit_to_cpu,
        "quantization": args.quantization,
        "init_status": init_status,
        "enable_generate": enable_generate,
        "dit_handler": dit_handler,
        "llm_handler": llm_handler,
        "language": args.language,
        "gpu_config": gpu_config,
        "output_dir": output_dir,
        "default_batch_size": args.batch_size,
    }
    print("Service initialization completed successfully!")
    return init_params, dit_handler, llm_handler


def _initialize_lm_from_cli(
    args: argparse.Namespace,
    *,
    dit_handler: AceStepHandler,
    llm_handler: LLMHandler,
    project_root: str,
    effective_gpu_mapping: Optional[str],
    init_status: str,
    prefer_source: Optional[str],
) -> str:
    """Download/initialize the 5Hz LM using the mapped device when available."""
    if args.lm_model_path is None:
        available_lm_models = llm_handler.get_available_5hz_lm_models()
        if available_lm_models:
            args.lm_model_path = available_lm_models[0]
            print(f"Using default LM model: {args.lm_model_path}")
        else:
            print(
                "Warning: No LM models available, skipping LM initialization",
                file=sys.stderr,
            )
            args.init_llm = False
            return init_status

    if not (args.init_llm and args.lm_model_path):
        return init_status

    checkpoint_dir = os.path.join(project_root, "checkpoints")
    try:
        dl_ok, dl_msg = ensure_lm_model(
            model_name=args.lm_model_path,
            checkpoints_dir=checkpoint_dir,
            prefer_source=prefer_source,
        )
        if not dl_ok:
            print(f"Warning: LM model download failed: {dl_msg}", file=sys.stderr)
    except Exception as exc:
        print(f"Warning: Failed to download LM model: {exc}", file=sys.stderr)

    lm_device = args.device
    device_map = getattr(dit_handler, "device_map", None)
    if device_map is not None and device_map.lm is not None:
        lm_device = device_map.lm
    log_lm_device_deprecation(
        explicit_lm_device=os.environ.get("ACESTEP_LM_DEVICE"),
        gpu_mapping_env=effective_gpu_mapping,
        using_device_map_lm=bool(device_map is not None and device_map.lm is not None),
    )
    print(f"Initializing 5Hz LM: {args.lm_model_path} on {lm_device}...")
    lm_status, lm_success = llm_handler.initialize(
        checkpoint_dir=checkpoint_dir,
        lm_model_path=args.lm_model_path,
        backend=args.backend,
        device=lm_device,
        offload_to_cpu=args.offload_to_cpu,
        dtype=None,
    )
    if lm_success:
        print("5Hz LM initialized successfully")
    else:
        print(f"Warning: 5Hz LM initialization failed: {lm_status}", file=sys.stderr)
    return f"{init_status}\n{lm_status}"
