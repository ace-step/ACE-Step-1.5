# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build, Run, and Test Commands

```bash
# Install dependencies
uv sync

# Run Gradio web UI
uv run acestep

# Run REST API server
uv run acestep-api

# Download models
uv run acestep-download

# Run all tests
uv run python -m unittest discover -s . -p "*_test.py"
uv run python -m unittest discover -s . -p "test_*.py"

# Run a single test file
uv run python -m unittest acestep.training.test_lora_utils

# Run a specific test class or method
uv run python -m unittest acestep.training.test_lora_utils.TestUnwrapDecoder
uv run python -m unittest acestep.training.test_lora_utils.TestUnwrapDecoder.test_returns_module_directly

# Run all tests in a directory
uv run python -m unittest discover -s acestep/training -p "*_test.py"
```

## Architecture

ACE-Step 1.5 is a music generation model combining two neural networks:

- **Language Model (LM):** Qwen3-based (0.6B/1.7B/4B params) that acts as a planner — rewrites prompts, synthesizes metadata (BPM, key, duration), and generates lyrics/captions.
- **Diffusion Transformer (DiT):** Performs iterative noise-to-audio synthesis in latent space. Variants: base, sft, turbo, turbo-rl.
- **VAE:** Encodes/decodes between audio waveforms and latent representations.

**Generation pipeline flow:** LLM processing → text encoding + conditioning → diffusion denoising → VAE decode → post-processing (normalization, fading, quality scoring).

**Task types:** text2music, cover, repaint, lego, extract, complete.

### Key Source Layout

- `acestep/handler.py` — **AceStepHandler**, the main orchestrator composed of 20+ mixins from `acestep/core/`
- `acestep/core/` — Core mixins: generation, audio processing, diffusion, VAE, conditioning, LoRA management
- `acestep/inference.py` — `GenerationParams` dataclass and generation logic
- `acestep/llm_inference.py` — `LLMHandler` for LLM inference and text processing
- `acestep/gpu_config.py` — Hardware detection and VRAM-based model selection
- `acestep/acestep_v15_pipeline.py` — Gradio UI entry point
- `acestep/api_server.py` — FastAPI REST API server (async job queue, single worker)
- `acestep/api/` — API route handlers and job management
- `acestep/ui/gradio/` — Gradio interface components, events, and i18n (50+ languages)
- `acestep/models/` — Model configs: base, sft, turbo, mlx variants
- `acestep/training/` and `acestep/training_v2/` — LoRA/LoKR training pipeline
- `acestep/third_parts/nano-vllm/` — Vendored optimized LLM inference

### Multi-Platform Support

Supports CUDA, ROCm, Intel XPU, MPS, MLX, and CPU. **Do not alter non-target platform paths** unless the task requires it. Use `gpu_config.py` for hardware detection. VRAM tiers auto-select LM model size (6GB→0.6B, 8GB→0.6B/1.7B, 16GB+→4B).

## Code Conventions

- **Python 3.11-3.12**, PEP 8, 4 spaces, double quotes, max 100 char lines
- **Naming:** `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants
- **Logging:** `from loguru import logger` — never use `print()` except CLI output
- **Imports:** stdlib → third-party → local, alphabetical within groups
- **Type hints:** Required for new/modified functions
- **Docstrings:** Mandatory for modules, classes, and public functions
- **Tests:** `unittest`-style, files named `*_test.py` or `test_*.py`, use `unittest.mock` for mocking GPU/filesystem/network
- **Module size:** Target ≤150 LOC, hard cap 200 LOC. Split by responsibility.
- **Dependencies:** `uv add <package>` to add to `pyproject.toml`

## Change Control

- One problem per PR, minimal scope — no drive-by refactors or formatting sweeps
- Preserve existing public interfaces unless the task explicitly requires changes
- Gate WIP/unstable features behind flags; don't expose unfinished flows by default
- Add focused tests for every behavior change: success path + regression/edge case
- See `AGENTS.md` for full decomposition policy and PR checklist
