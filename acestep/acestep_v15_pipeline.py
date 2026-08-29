"""
ACE-Step V1.5 Pipeline
Handler wrapper connecting model and UI
"""

import os
import sys

# Load environment variables from .env file at most once per process to avoid
# epoch-boundary stalls (e.g. on Windows when Gradio yields during training)
_env_loaded = False
try:
    from dotenv import load_dotenv

    if not _env_loaded:
        _current_file = os.path.abspath(__file__)
        _project_root = os.path.dirname(os.path.dirname(_current_file))
        _env_path = os.path.join(_project_root, ".env")
        _env_example_path = os.path.join(_project_root, ".env.example")
        if os.path.exists(_env_path):
            load_dotenv(_env_path)
            print(f"Loaded configuration from {_env_path}")
        elif os.path.exists(_env_example_path):
            load_dotenv(_env_example_path)
            print(f"Loaded configuration from {_env_example_path} (fallback)")
        _env_loaded = True
except ImportError:
    pass

for proxy_var in [
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
]:
    os.environ.pop(proxy_var, None)

os.environ["TORCHAUDIO_USE_BACKEND"] = "ffmpeg"

from acestep.dataset_handler import DatasetHandler
from acestep.gpu_config import (
    VRAM_AUTO_OFFLOAD_THRESHOLD_GB,
    get_gpu_config,
    is_mps_platform,
    resolve_lm_backend,
    set_global_gpu_config,
)
from acestep.gradio_pipeline_banner import print_gpu_banner
from acestep.gradio_pipeline_cli import (
    apply_gpu_mapping_args,
    build_gradio_parser,
    resolve_default_quantization,
)
from acestep.gradio_pipeline_launch import launch_gradio_demo
from acestep.gradio_pipeline_mode_defaults import apply_startup_mode_defaults
from acestep.gradio_pipeline_startup import initialize_from_cli
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.ui.gradio import create_gradio_interface
from acestep.ui.gradio.i18n import get_i18n


def create_demo(init_params=None, language="en"):
    """Create Gradio demo interface with optional pre-initialized handlers."""
    if (
        init_params
        and init_params.get("pre_initialized")
        and "dit_handler" in init_params
    ):
        dit_handler = init_params["dit_handler"]
        llm_handler = init_params["llm_handler"]
    else:
        dit_handler = AceStepHandler()
        llm_handler = LLMHandler()

    dataset_handler = DatasetHandler()
    return create_gradio_interface(
        dit_handler,
        llm_handler,
        dataset_handler,
        init_params=init_params,
        language=language,
    )


def _resolve_startup_lm_backend(requested_backend: str | None, gpu_config) -> str:
    """Resolve the startup LM backend against hardware compatibility restrictions."""
    resolved_backend = resolve_lm_backend(requested_backend, gpu_config)
    normalized_backend = (requested_backend or "").strip().lower()
    if normalized_backend and normalized_backend != resolved_backend:
        print(
            f"Requested LM backend '{normalized_backend}' is not supported on this "
            f"hardware. Using '{resolved_backend}' instead."
        )
    return resolved_backend


def main():
    """Main entry function for the Gradio demo."""
    gpu_config = get_gpu_config()
    set_global_gpu_config(gpu_config)

    gpu_memory_gb = gpu_config.gpu_memory_gb
    is_mac = is_mps_platform()
    auto_offload = (
        (not is_mac)
        and gpu_memory_gb > 0
        and gpu_memory_gb < VRAM_AUTO_OFFLOAD_THRESHOLD_GB
    )
    default_backend = gpu_config.recommended_backend
    print_gpu_banner(gpu_config, gpu_memory_gb, is_mac, auto_offload, default_backend)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(project_root, "gradio_outputs").replace("\\", "/")
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}")
    get_i18n()

    parser = build_gradio_parser(
        auto_offload=auto_offload,
        default_backend=default_backend,
        default_offload_dit=(
            gpu_config.offload_dit_to_cpu_default if not is_mac else False
        ),
        default_quantization=resolve_default_quantization(gpu_config, is_mac=is_mac),
    )
    args = parser.parse_args()
    effective_gpu_mapping = apply_gpu_mapping_args(args)

    apply_startup_mode_defaults(args, gpu_memory_gb)
    args.backend = _resolve_startup_lm_backend(args.backend, gpu_config)
    if args.service_mode:
        print(f"  Backend: {args.backend}")

    try:
        dit_handler = None
        llm_handler = None
        init_params = None
        if args.init_service:
            init_params, dit_handler, llm_handler = initialize_from_cli(
                args,
                gpu_config=gpu_config,
                effective_gpu_mapping=effective_gpu_mapping,
                project_root=project_root,
                output_dir=output_dir,
            )
        if init_params is None:
            init_params = {
                "gpu_config": gpu_config,
                "language": args.language,
                "output_dir": output_dir,
                "default_batch_size": args.batch_size,
            }

        print(f"Creating Gradio interface with language: {args.language}...")
        demo = create_demo(init_params=init_params, language=args.language)
        launch_gradio_demo(
            demo,
            args,
            output_dir=output_dir,
            dit_handler=dit_handler,
            llm_handler=llm_handler,
        )
    except Exception as exc:
        print(f"Error launching Gradio: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
