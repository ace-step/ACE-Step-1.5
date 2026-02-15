# ACE-Step 1.5 Installation Guide

**Language / 语言 / 言語:** [English](INSTALL.md) | [中文](../zh/INSTALL.md) | [日本語](../ja/INSTALL.md)

---

## Table of Contents

- [Requirements](#requirements)
- [Quick Start (All Platforms)](#quick-start-all-platforms)
- [Launch Scripts](#-launch-scripts)
- [Windows Portable Package](#-windows-portable-package)
- [AMD / ROCm GPUs](#amd--rocm-gpus)
- [Intel GPUs](#intel-gpus)
- [CPU-Only Mode](#cpu-only-mode)
- [Linux Notes](#linux-notes)
- [Environment Variables (.env)](#environment-variables-env)
- [Command Line Options](#command-line-options)
- [Model Download](#-model-download)
- [Which Model Should I Choose?](#-which-model-should-i-choose)
- [Development](#development)

---

## Requirements

| Item | Requirement |
|------|-------------|
| Python | 3.11-3.12 (stable release, not pre-release)<br>**Note:** ROCm on Windows requires Python 3.12 |
| GPU | CUDA GPU recommended; MPS / ROCm / Intel XPU / CPU also supported |
| VRAM | ≥4GB for DiT-only mode; ≥6GB for LLM+DiT |
| Disk | ~10GB for core models |

---

## Quick Start (All Platforms)

### 1. Install uv (Package Manager)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone & Install

```bash
git clone https://github.com/ACE-Step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync
```

### 3. Launch

**Gradio Web UI (Recommended):**

```bash
uv run acestep
```

**REST API Server:**

```bash
uv run acestep-api
```

**Using Python directly** (Conda / venv / system Python):

```bash
# Activate your environment first, then:
python acestep/acestep_v15_pipeline.py          # Gradio UI
python acestep/api_server.py                     # REST API
```

> Models are downloaded automatically on first run. Open http://localhost:7860 (Gradio) or http://localhost:8001 (API).

---

## 🚀 Launch Scripts

Ready-to-use launch scripts for all platforms. These scripts handle environment detection, dependency installation, and application startup automatically. All scripts check for updates on startup by default (configurable).

### Available Scripts

| Platform | Script | Description |
|----------|--------|-------------|
| **Windows** | `start_gradio_ui.bat` | Launch Gradio Web UI (CUDA) |
| **Windows** | `start_api_server.bat` | Launch REST API Server (CUDA) |
| **Windows** | `start_gradio_ui_rocm.bat` | Launch Gradio Web UI (AMD ROCm) |
| **Windows** | `start_api_server_rocm.bat` | Launch REST API Server (AMD ROCm) |
| **Linux** | `start_gradio_ui.sh` | Launch Gradio Web UI (CUDA) |
| **Linux** | `start_api_server.sh` | Launch REST API Server (CUDA) |
| **macOS** | `start_gradio_ui_macos.sh` | Launch Gradio Web UI (MLX) |
| **macOS** | `start_api_server_macos.sh` | Launch REST API Server (MLX) |

### Windows

```bash
# Launch Gradio Web UI (NVIDIA CUDA)
start_gradio_ui.bat

# Launch REST API Server (NVIDIA CUDA)
start_api_server.bat

# Launch Gradio Web UI (AMD ROCm)
start_gradio_ui_rocm.bat

# Launch REST API Server (AMD ROCm)
start_api_server_rocm.bat
```

> **ROCm users:** The ROCm scripts (`start_gradio_ui_rocm.bat`, `start_api_server_rocm.bat`) auto-set `HSA_OVERRIDE_GFX_VERSION`, `ACESTEP_LM_BACKEND=pt`, `MIOPEN_FIND_MODE=FAST` and other ROCm-specific environment variables. They use a separate `venv_rocm` virtual environment to avoid CUDA/ROCm wheel conflicts.

### Linux

```bash
# Make executable (first time only)
chmod +x start_gradio_ui.sh start_api_server.sh

# Launch Gradio Web UI
./start_gradio_ui.sh

# Launch REST API Server
./start_api_server.sh
```

> **Note:** Git must be installed via your system package manager (`sudo apt install git`, `sudo yum install git`, `sudo pacman -S git`).

### macOS (Apple Silicon / MLX)

macOS scripts use the **MLX backend** for native Apple Silicon acceleration (M1/M2/M3/M4).

```bash
# Make executable (first time only)
chmod +x start_gradio_ui_macos.sh start_api_server_macos.sh

# Launch Gradio Web UI with MLX backend
./start_gradio_ui_macos.sh

# Launch REST API Server with MLX backend
./start_api_server_macos.sh
```

The macOS scripts automatically set `ACESTEP_LM_BACKEND=mlx` and `--backend mlx` for native Apple Silicon acceleration, and fall back to PyTorch backend on non-arm64 machines.

> **Note:** Install git via `xcode-select --install` or `brew install git`.

### Script Features

- Startup update check (enabled by default, configurable)
- Auto environment detection (portable Python or uv)
- Auto install `uv` if needed
- Configurable download source (HuggingFace/ModelScope)
- Customizable models and parameters

### How to Modify Configuration

All configurable options are defined as variables at the top of each script. To customize, open the script with a text editor and modify the variable values.

**Example: Change UI language to Chinese and use the 1.7B LM model**

<table>
<tr><th>Windows (.bat)</th><th>Linux / macOS (.sh)</th></tr>
<tr><td>

Find these lines in `start_gradio_ui.bat`:
```batch
set LANGUAGE=en
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
```
Change to:
```batch
set LANGUAGE=zh
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
```

</td><td>

Find these lines in `start_gradio_ui.sh`:
```bash
LANGUAGE="en"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-0.6B"
```
Change to:
```bash
LANGUAGE="zh"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-1.7B"
```

</td></tr>
</table>

**Example: Disable startup update check**

<table>
<tr><th>Windows (.bat)</th><th>Linux / macOS (.sh)</th></tr>
<tr><td>

```batch
REM set CHECK_UPDATE=true
set CHECK_UPDATE=false
```

</td><td>

```bash
# CHECK_UPDATE="true"
CHECK_UPDATE="false"
```

</td></tr>
</table>

**Example: Enable a commented-out option** — remove the comment prefix (`REM` for .bat, `#` for .sh):

<table>
<tr><th>Windows (.bat)</th><th>Linux / macOS (.sh)</th></tr>
<tr><td>

Before:
```batch
REM set SHARE=--share
```
After:
```batch
set SHARE=--share
```

</td><td>

Before:
```bash
# SHARE="--share"
```
After:
```bash
SHARE="--share"
```

</td></tr>
</table>

**Common configurable options:**

| Option | Gradio UI | API Server | Description |
|--------|:---------:|:----------:|-------------|
| `LANGUAGE` | ✅ | — | UI language: `en`, `zh`, `he`, `ja` |
| `PORT` | ✅ | ✅ | Server port (default: 7860 / 8001) |
| `SERVER_NAME` / `HOST` | ✅ | ✅ | Bind address (`127.0.0.1` or `0.0.0.0`) |
| `CHECK_UPDATE` | ✅ | ✅ | Startup update check (`true` / `false`) |
| `CONFIG_PATH` | ✅ | — | DiT model (`acestep-v15-turbo`, etc.) |
| `LM_MODEL_PATH` | ✅ | ✅ | LM model (`acestep-5Hz-lm-0.6B` / `1.7B` / `4B`) |
| `DOWNLOAD_SOURCE` | ✅ | ✅ | Download source (`huggingface` / `modelscope`) |
| `SHARE` | ✅ | — | Create public Gradio link |
| `INIT_LLM` | ✅ | — | Force LLM on/off (`true` / `false` / `auto`) |
| `OFFLOAD_TO_CPU` | ✅ | — | CPU offload for low-VRAM GPUs |

### Update & Maintenance Tools

| Script (Windows) | Script (Linux/macOS) | Purpose |
|-------------------|----------------------|---------|
| `check_update.bat` | `check_update.sh` | Check and update from GitHub |
| `merge_config.bat` | `merge_config.sh` | Merge backed-up configurations after update |
| `install_uv.bat` | `install_uv.sh` | Install uv package manager |
| `quick_test.bat` | `quick_test.sh` | Test environment setup |

**Update workflow:**

```bash
# Windows                          # Linux / macOS
check_update.bat                    ./check_update.sh
merge_config.bat                    ./merge_config.sh
```

---

## 🪟 Windows Portable Package

For Windows users, we provide a portable package with pre-installed dependencies:

1. Download and extract: [ACE-Step-1.5.7z](https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z)
2. The package includes `python_embeded` with all dependencies pre-installed
3. **Requirements:** CUDA 12.8

### Quick Start Scripts

| Script | Description |
|--------|-------------|
| `start_gradio_ui.bat` | Launch Gradio Web UI |
| `start_api_server.bat` | Launch REST API Server |

Both scripts support auto environment detection, auto `uv` install, configurable download source, optional Git update check, and customizable models/parameters.

### Configuration

**`start_gradio_ui.bat`:**

```batch
REM UI language (en, zh, he, ja)
set LANGUAGE=zh

REM Download source (auto, huggingface, modelscope)
set DOWNLOAD_SOURCE=--download-source modelscope

REM Git update check (true/false)
set CHECK_UPDATE=true

REM Model configuration
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
```

**`start_api_server.bat`:**

```batch
REM LLM initialization via environment variable
REM set ACESTEP_INIT_LLM=true   # Force enable LLM
REM set ACESTEP_INIT_LLM=false  # Force disable LLM (DiT-only mode)
```

### Update & Maintenance

| Script | Purpose |
|--------|---------|
| `check_update.bat` | Check and update from GitHub |
| `merge_config.bat` | Merge backed-up configurations after update |
| `install_uv.bat` | Install uv package manager |
| `quick_test.bat` | Test environment setup |
| `test_git_update.bat` | Test Git update functionality |

**Update workflow:**

```bash
check_update.bat          # 1. Check for updates (requires PortableGit/)
merge_config.bat          # 2. Merge settings back if conflicts occur
```

### Portable Git Support

Place a `PortableGit/` folder in your package to enable auto-updates:

```batch
set CHECK_UPDATE=true     # in start_gradio_ui.bat or start_api_server.bat
```

Features: 10s timeout protection, smart conflict detection & backup, automatic rollback on failure, directory structure preserved in backups.

### Environment Detection Priority

1. `python_embeded\python.exe` (if exists)
2. `uv run acestep` (if uv is installed)
3. Auto-install uv via winget or PowerShell

---

## AMD / ROCm GPUs

> ⚠️ `uv run acestep` installs CUDA PyTorch wheels and may overwrite an existing ROCm setup.

### Windows - ROCm 7.2 (Python 3.12 Required)

**Important:** AMD ROCm 7.2 on Windows requires **Python 3.12** (AMD officially provides Python 3.12 wheels only).

```bash
# 1. Ensure you have Python 3.12 installed
python --version  # Should show Python 3.12.x

# 2. Create and activate a virtual environment
python -m venv venv_rocm
venv_rocm\Scripts\activate

# 3. Follow the installation steps in requirements-rocm.txt
# This installs ROCm SDK and PyTorch wheels from AMD's repository

# 4. Install dependencies
pip install -r requirements-rocm.txt

# 5. Launch with the ROCm-specific launcher
start_gradio_ui_rocm.bat
# OR
start_api_server_rocm.bat
```

See [`requirements-rocm.txt`](../../requirements-rocm.txt) for detailed ROCm 7.2 installation steps.

### Linux - ROCm 6.0+ (Python 3.11 or 3.12)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install ROCm-compatible PyTorch
pip install torch --index-url https://download.pytorch.org/whl/rocm6.0

# 3. Install ACE-Step
pip install -e .

# 4. Start the service
python -m acestep.acestep_v15_pipeline --port 7680
```

> **Note:** `torchcodec` is not available for AMD ROCm GPUs due to CUDA-specific dependencies. ACE-Step automatically uses `soundfile` as a fallback for audio I/O, which provides full functionality on ROCm platforms.

### GPU Detection Troubleshooting

If you see "No GPU detected, running on CPU" with an AMD GPU:

1. Run the diagnostic tool: `python scripts/check_gpu.py`
2. For RDNA3 GPUs, set `HSA_OVERRIDE_GFX_VERSION`:

| GPU | Value |
|-----|-------|
| RX 7900 XT/XTX, RX 9070 XT | `export HSA_OVERRIDE_GFX_VERSION=11.0.0` |
| RX 7800 XT, RX 7700 XT | `export HSA_OVERRIDE_GFX_VERSION=11.0.1` |
| RX 7600 | `export HSA_OVERRIDE_GFX_VERSION=11.0.2` |

3. On Windows, use `start_gradio_ui_rocm.bat` / `start_api_server_rocm.bat` which set required environment variables automatically.
4. Verify ROCm installation: `rocm-smi` should list your GPU.

### Linux (cachy-os / RDNA4)

See [ACE-Step1.5-Rocm-Manual-Linux.md](ACE-Step1.5-Rocm-Manual-Linux.md) for a detailed ROCm manual tested with RDNA4 on cachy-os.

---

## Intel GPUs

| Item | Detail |
|------|--------|
| Tested Device | Windows laptop with Ultra 9 285H integrated graphics |
| Offload | Disabled by default |
| Compile & Quantization | Enabled by default |
| LLM Inference | Supported (tested with `acestep-5Hz-lm-0.6B`) |
| nanovllm acceleration | NOT supported on Intel GPUs |
| Test Environment | PyTorch 2.8.0 from [Intel Extension for PyTorch](https://pytorch-extension.intel.com/?request=platform) |

> **Note:** LLM inference speed may decrease when generating audio longer than 2 minutes. Intel discrete GPUs are expected to work but not yet tested.
> 
> **Audio I/O:** `torchcodec` is not available for Intel XPU GPUs. ACE-Step automatically uses `soundfile` as a fallback for audio I/O, which provides full functionality on Intel platforms.

---

## CPU-Only Mode

ACE-Step can run on CPU for **inference only**, but performance will be significantly slower.

- Training (including LoRA) on CPU is **not recommended**.
- For low-VRAM systems, DiT-only mode (LLM disabled) is supported.

If you do not have a GPU, consider:
- Using cloud GPU providers
- Running inference-only workflows
- Using DiT-only mode with `ACESTEP_INIT_LLM=false`

---

## Linux Notes

### Python 3.11 Pre-Release Issue

Some Linux distributions (including Ubuntu) ship Python 3.11.0rc1, which is a **pre-release** build. This can cause segmentation faults with the vLLM backend.

**Recommendation:** Use a stable Python release (≥ 3.11.12). On Ubuntu, install via the deadsnakes PPA.

If upgrading Python is not possible, use the PyTorch backend:

```bash
uv run acestep --backend pt
```

---

## Environment Variables (.env)

The `.env` file provides a centralized way to configure ACE-Step. Settings in `.env` are:
- Used by Python scripts (CLI, API server, Gradio UI)
- **Now also used by launcher scripts** (`start_gradio_ui.bat`, `start_gradio_ui.sh`, etc.)
- **Preserved across repository updates** (unlike hardcoded values in launcher scripts)

```bash
cp .env.example .env   # Copy and edit
```

### Benefits of Using .env

✅ **Survives Updates**: Your custom model paths and settings won't be overwritten when you update ACE-Step  
✅ **Cross-Platform**: Same configuration works on Windows, Linux, and macOS  
✅ **Version Control Safe**: `.env` is in `.gitignore`, so your personal settings stay private

### Key Variables

| Variable | Values | Description |
|----------|--------|-------------|
| `ACESTEP_INIT_LLM` | `auto` / `true` / `false` | LLM initialization mode |
| `ACESTEP_CONFIG_PATH` | model name | DiT model path |
| `ACESTEP_LM_MODEL_PATH` | model name | LM model path |
| `ACESTEP_DOWNLOAD_SOURCE` | `auto` / `huggingface` / `modelscope` | Download source |
| `ACESTEP_API_KEY` | string | API authentication key |
| `PORT` | number | Server port (default: 7860) |
| `SERVER_NAME` | IP address | Server host (default: 127.0.0.1) |
| `LANGUAGE` | `en` / `zh` / `he` / `ja` | UI language (default: en) |

### LLM Initialization (`ACESTEP_INIT_LLM`)

Processing flow: `GPU Detection → ACESTEP_INIT_LLM Override → Model Loading`

| Value | Behavior |
|-------|----------|
| `auto` (or empty) | Use GPU auto-detection result (recommended) |
| `true` / `1` / `yes` | Force enable LLM after GPU detection (may cause OOM) |
| `false` / `0` / `no` | Force disable for pure DiT mode |

**Example `.env` for different scenarios:**

```bash
# Auto mode (recommended)
ACESTEP_INIT_LLM=auto

# Force enable on low VRAM GPU
ACESTEP_INIT_LLM=true
ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B

# Force disable LLM for faster generation
ACESTEP_INIT_LLM=false
```

---

## Command Line Options

### Gradio UI (`acestep`)

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | 7860 | Server port |
| `--server-name` | 127.0.0.1 | Server address (use `0.0.0.0` for network access) |
| `--share` | false | Create public Gradio link |
| `--language` | en | UI language: `en`, `zh`, `he`, `ja` |
| `--init_service` | false | Auto-initialize models on startup |
| `--init_llm` | auto | LLM init: `true` / `false` / omit for auto |
| `--config_path` | auto | DiT model (e.g., `acestep-v15-turbo`) |
| `--lm_model_path` | auto | LM model (e.g., `acestep-5Hz-lm-1.7B`) |
| `--offload_to_cpu` | auto | CPU offload (auto-enabled if VRAM < 20GB) |
| `--download-source` | auto | Model source: `auto` / `huggingface` / `modelscope` |
| `--enable-api` | false | Enable REST API alongside Gradio UI |
| `--api-key` | none | API key for authentication |
| `--auth-username` | none | Gradio authentication username |
| `--auth-password` | none | Gradio authentication password |

**Examples:**

```bash
# Public access with Chinese UI
uv run acestep --server-name 0.0.0.0 --share --language zh

# Pre-initialize models on startup
uv run acestep --init_service true --config_path acestep-v15-turbo

# Enable API endpoints with authentication
uv run acestep --enable-api --api-key sk-your-secret-key --port 8001

# Use ModelScope as download source
uv run acestep --download-source modelscope
```

---

## 📥 Model Download

Models are automatically downloaded from [HuggingFace](https://huggingface.co/ACE-Step/Ace-Step1.5) or [ModelScope](https://modelscope.cn/organization/ACE-Step) on first run.

### CLI Download

```bash
uv run acestep-download                              # Download main model
uv run acestep-download --all                         # Download all models
uv run acestep-download --download-source modelscope  # From ModelScope
uv run acestep-download --model acestep-v15-sft       # Specific model
uv run acestep-download --list                        # List all available
```

Or with Python directly:

```bash
python -m acestep.model_downloader                    # Download main model
python -m acestep.model_downloader --all              # Download all models
```

### Manual Download (huggingface-cli)

```bash
# Main model (vae, Qwen3-Embedding-0.6B, acestep-v15-turbo, acestep-5Hz-lm-1.7B)
huggingface-cli download ACE-Step/Ace-Step1.5 --local-dir ./checkpoints

# Optional models
huggingface-cli download ACE-Step/acestep-5Hz-lm-0.6B --local-dir ./checkpoints/acestep-5Hz-lm-0.6B
huggingface-cli download ACE-Step/acestep-5Hz-lm-4B --local-dir ./checkpoints/acestep-5Hz-lm-4B
```

### Available Models

| Model | Description | HuggingFace |
|-------|-------------|-------------|
| **Ace-Step1.5** (Main) | Core: vae, Qwen3-Embedding-0.6B, acestep-v15-turbo, acestep-5Hz-lm-1.7B | [Link](https://huggingface.co/ACE-Step/Ace-Step1.5) |
| acestep-5Hz-lm-0.6B | Lightweight LM (0.6B params) | [Link](https://huggingface.co/ACE-Step/acestep-5Hz-lm-0.6B) |
| acestep-5Hz-lm-4B | Large LM (4B params) | [Link](https://huggingface.co/ACE-Step/acestep-5Hz-lm-4B) |
| acestep-v15-base | Base DiT model | [Link](https://huggingface.co/ACE-Step/acestep-v15-base) |
| acestep-v15-sft | SFT DiT model | [Link](https://huggingface.co/ACE-Step/acestep-v15-sft) |
| acestep-v15-turbo-shift1 | Turbo DiT with shift1 | [Link](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift1) |
| acestep-v15-turbo-shift3 | Turbo DiT with shift3 | [Link](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift3) |
| acestep-v15-turbo-continuous | Turbo DiT with continuous shift (1-5) | [Link](https://huggingface.co/ACE-Step/acestep-v15-turbo-continuous) |

---

## 💡 Which Model Should I Choose?

ACE-Step automatically adapts to your GPU's VRAM. The UI pre-configures all settings (LM model, backend, offloading, quantization) based on your detected GPU tier:

| Your GPU VRAM | Recommended LM Model | Backend | Notes |
|---------------|---------------------|---------|-------|
| **≤6GB** | None (DiT only) | — | LM disabled by default; INT8 quantization + full CPU offload |
| **6-8GB** | `acestep-5Hz-lm-0.6B` | `pt` | Lightweight LM with PyTorch backend |
| **8-16GB** | `0.6B` / `1.7B` | `vllm` | 0.6B for 8-12GB, 1.7B for 12-16GB |
| **16-24GB** | `acestep-5Hz-lm-1.7B` | `vllm` | 4B available on 20GB+; no offload on 20GB+ |
| **≥24GB** | `acestep-5Hz-lm-4B` | `vllm` | Best quality, all models fit without offload |

> 📖 For detailed GPU compatibility information (tier table, duration limits, batch sizes, adaptive UI defaults, memory optimization), see [GPU Compatibility Guide](GPU_COMPATIBILITY.md).

---

## Development

```bash
# Add dependencies
uv add package-name
uv add --dev package-name

# Update all dependencies
uv sync --upgrade
```
