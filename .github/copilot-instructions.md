# ACE-Step 1.5 - GitHub Copilot Instructions

## Project Overview

ACE-Step 1.5 is an open-source music foundation model combining a Language Model (LM) as a planner with a Diffusion Transformer (DiT) for audio synthesis. It generates commercial-grade music on consumer hardware (< 4GB VRAM).

## Tech Stack

- **Python 3.11-3.12** (ROCm on Windows requires 3.12; other platforms use 3.11)
- **PyTorch 2.7+** with CUDA 12.8 (Windows/Linux), MPS (macOS ARM64)
- **Transformers 4.51.0-4.57.x** for LLM inference
- **Diffusers** for diffusion models
- **Gradio 6.2.0** for web UI
- **FastAPI + Uvicorn** for REST API server
- **uv** for dependency management
- **MLX** (Apple Silicon native acceleration, macOS ARM64)
- **nano-vllm** (optimized LLM inference, non-macOS ARM64)

## Multi-Platform Support

**CRITICAL**: Supports CUDA, ROCm, Intel XPU, MPS, MLX, and CPU. When fixing bugs or adding features:
- **DO NOT alter non-target platform paths** unless explicitly required
- Changes to CUDA code should not affect MPS/XPU/CPU paths
- Use `gpu_config.py` for hardware detection and configuration

## Code Organization

### Main Entry Points
- `acestep/acestep_v15_pipeline.py` - Gradio UI pipeline
- `acestep/api_server.py` - REST API server
- `cli.py` - Command-line interface
- `acestep/model_downloader.py` - Model downloader

### Core Modules
- `acestep/handler.py` - Audio generation handler (AceStepHandler)
- `acestep/llm_inference.py` - LLM handler for text processing
- `acestep/inference.py` - Generation logic and parameters
- `acestep/gpu_config.py` - Hardware detection and GPU configuration
- `acestep/audio_utils.py` - Audio processing utilities
- `acestep/constants.py` - Global constants

### UI & Internationalization
- `acestep/gradio_ui/` - Gradio interface components
- `acestep/gradio_ui/i18n.py` - i18n system (50+ languages)
- All user-facing strings must use i18n translation keys

### Training
- `acestep/training/` - LoRA training pipeline
- `acestep/dataset/` - Dataset handling

## Key Conventions

- **Python style**: PEP 8, 4 spaces, double quotes for strings
- **Naming**: `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants
- **Logging**: Use `loguru` logger (not `print()` except CLI output)
- **Dependencies**: Use `uv add <package>` to add to `pyproject.toml`

## Performance

- Target: 4GB VRAM - minimize memory allocations
- Lazy load models when needed
- Batch operations supported (up to 8 songs)

## Additional Resources

- **AGENTS.md**: Detailed guidance for AI coding agents
- **CONTRIBUTING.md**: Contribution workflow and guidelines
