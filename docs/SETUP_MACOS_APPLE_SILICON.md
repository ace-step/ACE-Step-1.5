# ACE-Step 1.5 — macOS Apple Silicon Setup Guide

This document records the environment setup for running ACE-Step 1.5 on macOS with Apple Silicon (M4 Max, 128 GB unified memory).

## Prerequisites

| Tool    | Version | Install                          |
|---------|---------|----------------------------------|
| Python  | 3.12.x  | `brew install python@3.12`       |
| git     | 2.49+   | `brew install git`               |
| ffmpeg  | 7.x     | `brew install ffmpeg`            |
| uv      | 0.7+    | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

## Clone & Install

```bash
git clone https://github.com/ACE-Step/ACE-Step-1.5.git
cd ACE-Step-1.5
```

### Google Drive workaround

If your project directory lives on Google Drive, the virtual environment must be on a **local** filesystem. Google Drive's file-sync drops small Python files (e.g. `torchvision/models/densenet.py`), causing `ModuleNotFoundError` at runtime.

```bash
# Create a local directory for the venv
mkdir -p ~/Dev/KYStudio/ace-step-venv

# Symlink .venv to the local path
ln -sf ~/Dev/KYStudio/ace-step-venv .venv
```

### pyproject.toml fix

The upstream `required-environments` includes a Windows entry whose PyTorch wheel (`torch==2.7.1+cu128`) does not exist, causing `uv sync` to fail on **all** platforms. Comment it out:

```toml
# In [tool.uv]
required-environments = [
    # "sys_platform == 'win32' and platform_machine == 'AMD64'",
    "sys_platform == 'linux' and platform_machine == 'x86_64'",
    "sys_platform == 'linux' and platform_machine == 'aarch64'",
    "sys_platform == 'darwin' and platform_machine == 'arm64'",
]
```

Then install:

```bash
uv sync
```

Key packages installed for macOS ARM:
- `torch >= 2.9.1` (MPS backend)
- `mlx >= 0.25.2`, `mlx-lm >= 0.20.0` (Apple Silicon native)

## Model Download

```bash
# Core model (~10 GB): VAE, Qwen3-Embedding, turbo 2B DiT, 1.7B LM
uv run acestep-download

# XL turbo DiT (~19 GB) — highest quality DiT
uv run acestep-download --model acestep-v15-xl-turbo

# 4B LM (~7.8 GB) — highest quality LM
uv run acestep-download --model acestep-5Hz-lm-4B
```

Total disk usage: **~36 GB** under `checkpoints/`.

### Model Selection Guide (Apple Silicon)

| Unified Memory | Recommended DiT        | Recommended LM       |
|----------------|------------------------|----------------------|
| ≤ 16 GB        | 2B turbo               | 0.6B (or none)       |
| 16–36 GB       | 2B turbo/sft           | 1.7B                 |
| 36–64 GB       | XL turbo               | 1.7B                 |
| ≥ 64 GB        | XL turbo/sft           | 4B                   |

## Inference Test

Run the included test script to verify the full pipeline:

```bash
uv run python test_inference.py
```

This script:
1. Initializes DiT (`acestep-v15-xl-turbo`) on MPS with MLX acceleration.
2. Initializes LLM (`acestep-5Hz-lm-4B`) with MLX backend.
3. Generates a 15-second instrumental test track.
4. Saves `test_output.wav` in the project root.

### Verify output

```bash
# File exists and is non-empty
test -f test_output.wav && echo OK

# Valid WAV format
ffprobe -v error -show_entries format=format_name,duration test_output.wav
```

### Reference Timing (M4 Max, 128 GB)

| Phase              | Time     |
|--------------------|----------|
| DiT model load     | ~17 s    |
| LLM model load     | ~28 s    |
| Inference (15s audio) | ~19 s |
| — LM Phase 1       | ~4.2 s   |
| — LM Phase 2       | ~2.9 s   |
| — DiT diffusion    | ~3.3 s   |

## Launch

```bash
# Gradio Web UI (MLX backend auto-enabled)
./start_gradio_ui_macos.sh
# or
uv run acestep

# REST API server
./start_api_server_macos.sh
# or
uv run acestep-api
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `uv sync` fails with "no solution for win32" | `torch 2.7.1+cu128` has no Windows wheels | Comment out Windows in `required-environments` |
| `ModuleNotFoundError: torchvision.models.densenet` | Google Drive drops files during sync | Symlink `.venv` to a local path |
| LLM NaN/inf on MPS | bfloat16 not fully supported for autoregressive LLM | Handler auto-uses float32 for LLM on MPS |
