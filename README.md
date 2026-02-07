<h1 align="center">ACE-Step 1.5</h1>
<h1 align="center">Pushing the Boundaries of Open-Source Music Generation</h1>
<p align="center">
    <a href="https://ace-step.github.io/ace-step-v1.5.github.io/">Project</a> |
    <a href="https://huggingface.co/ACE-Step/Ace-Step1.5">Hugging Face</a> |
    <a href="https://modelscope.cn/models/ACE-Step/Ace-Step1.5">ModelScope</a> |
    <a href="https://huggingface.co/spaces/ACE-Step/Ace-Step-v1.5">Space Demo</a> |
    <a href="https://discord.gg/PeWDxrkdj7">Discord</a> |
    <a href="https://arxiv.org/abs/2602.00744">Technical Report</a>
</p>

<p align="center">
    <img src="./assets/orgnization_logos.png" width="100%" alt="StepFun Logo">
</p>

## Table of Contents

- [✨ Features](#-features)
- [📦 Installation](#-installation)
- [📥 Model Download](#-model-download)
- [🚀 Usage](#-usage)
- [📖 Tutorial](#-tutorial)
- [🔨 Train](#-train)
- [🏗️ Architecture](#️-architecture)
- [🦁 Model Zoo](#-model-zoo)

## 📝 Abstract
🚀 We present ACE-Step v1.5, a highly efficient open-source music foundation model that brings commercial-grade generation to consumer hardware. On commonly used evaluation metrics, ACE-Step v1.5 achieves quality beyond most commercial music models while remaining extremely fast—under 2 seconds per full song on an A100 and under 10 seconds on an RTX 3090. The model runs locally with less than 4GB of VRAM, and supports lightweight personalization: users can train a LoRA from just a few songs to capture their own style.

🌉 At its core lies a novel hybrid architecture where the Language Model (LM) functions as an omni-capable planner: it transforms simple user queries into comprehensive song blueprints—scaling from short loops to 10-minute compositions—while synthesizing metadata, lyrics, and captions via Chain-of-Thought to guide the Diffusion Transformer (DiT). ⚡ Uniquely, this alignment is achieved through intrinsic reinforcement learning relying solely on the model's internal mechanisms, thereby eliminating the biases inherent in external reward models or human preferences. 🎚️

🔮 Beyond standard synthesis, ACE-Step v1.5 unifies precise stylistic control with versatile editing capabilities—such as cover generation, repainting, and vocal-to-BGM conversion—while maintaining strict adherence to prompts across 50+ languages. This paves the way for powerful tools that seamlessly integrate into the creative workflows of music artists, producers, and content creators. 🎸


## ✨ Features

<p align="center">
    <img src="./assets/application_map.png" width="100%" alt="ACE-Step Framework">
</p>

### ⚡ Performance
- ✅ **Ultra-Fast Generation** — Under 2s per full song on A100, under 10s on RTX 3090 (0.5s to 10s on A100 depending on think mode & diffusion steps)
- ✅ **Flexible Duration** — Supports 10 seconds to 10 minutes (600s) audio generation
- ✅ **Batch Generation** — Generate up to 8 songs simultaneously

### 🎵 Generation Quality
- ✅ **Commercial-Grade Output** — Quality beyond most commercial music models (between Suno v4.5 and Suno v5)
- ✅ **Rich Style Support** — 1000+ instruments and styles with fine-grained timbre description
- ✅ **Multi-Language Lyrics** — Supports 50+ languages with lyrics prompt for structure & style control

### 🎛️ Versatility & Control

| Feature | Description |
|---------|-------------|
| ✅ Reference Audio Input | Use reference audio to guide generation style |
| ✅ Cover Generation | Create covers from existing audio |
| ✅ Repaint & Edit | Selective local audio editing and regeneration |
| ✅ Track Separation | Separate audio into individual stems |
| ✅ Multi-Track Generation | Add layers like Suno Studio's "Add Layer" feature |
| ✅ Vocal2BGM | Auto-generate accompaniment for vocal tracks |
| ✅ Metadata Control | Control duration, BPM, key/scale, time signature |
| ✅ Simple Mode | Generate full songs from simple descriptions |
| ✅ Query Rewriting | Auto LM expansion of tags and lyrics |
| ✅ Audio Understanding | Extract BPM, key/scale, time signature & caption from audio |
| ✅ LRC Generation | Auto-generate lyric timestamps for generated music |
| ✅ LoRA Training | One-click annotation & training in Gradio. 8 songs, 1 hour on 3090 (12GB VRAM) |
| ✅ Quality Scoring | Automatic quality assessment for generated audio |

## Staying ahead
-----------------
Star ACE-Step on GitHub and be instantly notified of new releases
![](assets/star.gif)

## 📦 Installation

> **Requirements:** Python 3.11, CUDA GPU recommended (works on CPU/MPS but slower)

### AMD / ROCm GPUs

ACE-Step works with AMD GPUs via PyTorch ROCm builds.

**Important:** The `uv run acestep` workflow currently installs CUDA PyTorch wheels and may overwrite an existing ROCm setup. `uv run acestep` is optimized for CUDA environments and may override ROCm PyTorch installations.

#### Recommended workflow for AMD / ROCm users

1. Create and activate a virtual environment manually:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install a ROCm-compatible PyTorch build:

   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/rocm6.0
   ```

3. Install ACE-Step dependencies without using uv run:

   ```bash
   pip install -e .
   ```

4. Start the service directly:

   ```bash
   python -m acestep.acestep_v15_pipeline --port 7680
   ```

This avoids CUDA wheel replacement and has been confirmed to work on ROCm systems. On Windows, use `.venv\Scripts\activate` and the same steps.

### 🪟 Windows Portable Package (Recommended for Windows)

For Windows users, we provide a portable package with pre-installed dependencies:

1. Download and extract: [ACE-Step-1.5.7z](https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z)
2. The package includes `python_embeded` with all dependencies pre-installed
3. **Requirements:** CUDA 12.8

#### 🚀 Quick Start Scripts

The portable package includes convenient batch scripts for easy operation:

| Script | Description | Usage |
|--------|-------------|-------|
| **start_gradio_ui.bat** | Launch Gradio Web UI | Double-click or run from terminal |
| **start_api_server.bat** | Launch REST API Server | Double-click or run from terminal |

**Basic Usage:**

```bash
# Launch Gradio Web UI (Recommended)
start_gradio_ui.bat

# Launch REST API Server
start_api_server.bat
```

Both scripts support:
- ✅ Auto environment detection (`python_embeded` or `uv`)
- ✅ Auto install `uv` if needed (via winget or PowerShell)
- ✅ Configurable download source (HuggingFace/ModelScope)
- ✅ Optional Git update check before startup
- ✅ Customizable language, models, and parameters

#### 📝 Configuration

Edit the scripts to customize settings:

**start_gradio_ui.bat:**
```batch
REM UI language (en, zh, ja)
set LANGUAGE=zh

REM Download source (auto, huggingface, modelscope)
set DOWNLOAD_SOURCE=--download-source modelscope

REM Git update check (true/false) - requires PortableGit
set CHECK_UPDATE=true

REM Model configuration
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B

REM LLM initialization (auto/true/false)
REM Auto: enabled if VRAM > 6GB, disabled otherwise
REM set INIT_LLM=--init_llm true   # Force enable (may cause OOM on low VRAM)
REM set INIT_LLM=--init_llm false  # Force disable (DiT-only mode)
```

**start_api_server.bat:**
```batch
REM LLM initialization via environment variable
REM set ACESTEP_INIT_LLM=true   # Force enable LLM
REM set ACESTEP_INIT_LLM=false  # Force disable LLM (DiT-only mode)

REM LM model path (optional)
REM set LM_MODEL_PATH=--lm-model-path acestep-5Hz-lm-0.6B
```

#### 🔄 Update & Maintenance Tools

| Script | Purpose | When to Use |
|--------|---------|-------------|
| **check_update.bat** | Check and update from GitHub | When you want to update to the latest version |
| **merge_config.bat** | Merge backed-up configurations | After updating when config conflicts occur |
| **install_uv.bat** | Install uv package manager | If uv installation failed during startup |
| **quick_test.bat** | Test environment setup | To verify your environment is working |
| **test_git_update.bat** | Test Git update functionality | To verify PortableGit is working correctly |

**Update Workflow:**

```bash
# 1. Check for updates (requires PortableGit/)
check_update.bat

# 2. If conflicts occur, your changes are backed up automatically
# 3. After update, merge your settings back
merge_config.bat

# Options:
# - Compare backup with current files (side-by-side in Notepad)
# - Restore files from backup
# - List all backed-up files
# - Delete old backups
```

**Environment Testing:**

```bash
# Test your setup
quick_test.bat

# This checks:
# - Python installation (python_embeded or system Python)
# - uv installation and PATH
# - GPU availability (CUDA/ROCm)
# - Basic imports
```

#### 📦 Portable Git Support

If you have `PortableGit/` folder in your package, you can:

1. **Enable Auto-Updates:** Edit `start_gradio_ui.bat` or `start_api_server.bat`
   ```batch
   set CHECK_UPDATE=true
   ```

2. **Manual Update Check:**
   ```bash
   check_update.bat
   ```

3. **Conflict Handling:** When your modified files conflict with GitHub updates:
   - Files are automatically backed up to `.update_backup_YYYYMMDD_HHMMSS/`
   - Use `merge_config.bat` to compare and merge changes
   - Supports all file types: `.bat`, `.py`, `.yaml`, `.json`, etc.

**Update Features:**
- ⏱️ 10-second timeout protection (won't block startup if GitHub is unreachable)
- 💾 Smart conflict detection and backup
- 🔄 Automatic rollback on failure
- 📁 Preserves directory structure in backups

#### 🛠️ Advanced Options

**Environment Detection Priority:**
1. `python_embeded\python.exe` (if exists)
2. `uv run acestep` (if uv is installed)
3. Auto-install uv via winget or PowerShell

**Download Source:**
- `auto`: Auto-detect best source (checks Google accessibility)
- `huggingface`: Use HuggingFace Hub
- `modelscope`: Use ModelScope

---

### Standard Installation (All Platforms)

> **AMD / ROCm users:** `uv run acestep` is optimized for CUDA and may override ROCm PyTorch. Use the [AMD / ROCm workflow](#amd--rocm-gpus) above instead.

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

#### 🖥️ Gradio Web UI (Recommended)

**Using uv:**
```bash
uv run acestep
```

**Using Python directly:**

> **Note:** Make sure to activate your Python environment first:
> - **Windows portable package**: Use `python_embeded\python.exe` instead of `python`
> - **Conda environment**: Run `conda activate your_env_name` first
> - **venv**: Run `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows) first
> - **System Python**: Use `python` or `python3` directly

```bash
# Windows portable package
python_embeded\python.exe acestep\acestep_v15_pipeline.py

# Conda/venv/system Python
python acestep/acestep_v15_pipeline.py
```

Open http://localhost:7860 in your browser. Models will be downloaded automatically on first run.

#### 🌐 REST API Server

**Using uv:**
```bash
uv run acestep-api
```

**Using Python directly:**

> **Note:** Make sure to activate your Python environment first (see note above).

```bash
# Windows portable package
python_embeded\python.exe acestep\api_server.py

# Conda/venv/system Python
python acestep/api_server.py
```

API runs at http://localhost:8001. See [API Documentation](./docs/en/API.md) for endpoints.

### Command Line Options

**Gradio UI (`acestep`):**

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | 7860 | Server port |
| `--server-name` | 127.0.0.1 | Server address (use `0.0.0.0` for network access) |
| `--share` | false | Create public Gradio link |
| `--language` | en | UI language: `en`, `zh`, `ja` |
| `--init_service` | false | Auto-initialize models on startup |
| `--init_llm` | auto | LLM initialization: `true` (force), `false` (disable), omit for auto |
| `--config_path` | auto | DiT model (e.g., `acestep-v15-turbo`, `acestep-v15-turbo-shift3`) |
| `--lm_model_path` | auto | LM model (e.g., `acestep-5Hz-lm-0.6B`, `acestep-5Hz-lm-1.7B`) |
| `--offload_to_cpu` | auto | CPU offload (auto-enabled if VRAM < 16GB) |
| `--download-source` | auto | Model download source: `auto`, `huggingface`, or `modelscope` |
| `--enable-api` | false | Enable REST API endpoints alongside Gradio UI |
| `--api-key` | none | API key for API endpoints authentication |
| `--auth-username` | none | Username for Gradio authentication |
| `--auth-password` | none | Password for Gradio authentication |

**Examples:**

> **Note for Python users:** Replace `python` with your environment's Python executable:
> - Windows portable package: `python_embeded\python.exe`
> - Conda: Activate environment first, then use `python`
> - venv: Activate environment first, then use `python`
> - System: Use `python` or `python3`

```bash
# Public access with Chinese UI
uv run acestep --server-name 0.0.0.0 --share --language zh
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --server-name 0.0.0.0 --share --language zh

# Pre-initialize models on startup
uv run acestep --init_service true --config_path acestep-v15-turbo
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --init_service true --config_path acestep-v15-turbo

# Enable API endpoints with authentication
uv run acestep --enable-api --api-key sk-your-secret-key --port 8001
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --enable-api --api-key sk-your-secret-key --port 8001

# Enable both Gradio auth and API auth
uv run acestep --enable-api --api-key sk-123456 --auth-username admin --auth-password password
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --enable-api --api-key sk-123456 --auth-username admin --auth-password password

# Use ModelScope as download source
uv run acestep --download-source modelscope
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --download-source modelscope

# Use HuggingFace Hub as download source
uv run acestep --download-source huggingface
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --download-source huggingface
```

### Environment Variables (.env)

For `uv` or Python users, you can configure ACE-Step using environment variables in a `.env` file:

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your settings
```

**Key environment variables:**

| Variable | Values | Description |
|----------|--------|-------------|
| `ACESTEP_INIT_LLM` | (empty), `true`, `false` | LLM initialization mode |
| `ACESTEP_CONFIG_PATH` | model name | DiT model path |
| `ACESTEP_LM_MODEL_PATH` | model name | LM model path |
| `ACESTEP_DOWNLOAD_SOURCE` | `auto`, `huggingface`, `modelscope` | Download source |
| `ACESTEP_API_KEY` | string | API authentication key |

**LLM Initialization (`ACESTEP_INIT_LLM`):**

Processing flow: `GPU Detection (full) → ACESTEP_INIT_LLM Override → Model Loading`

GPU optimizations (offload, quantization, batch limits) are **always applied**. The override only controls whether to attempt LLM loading.

| Value | Behavior |
|-------|----------|
| `auto` (or empty) | Use GPU auto-detection result (recommended) |
| `true` / `1` / `yes` | Force enable LLM after GPU detection (may cause OOM) |
| `false` / `0` / `no` | Force disable for pure DiT mode, faster generation |

**Example `.env` for different scenarios:**

```bash
# Auto mode (recommended) - let GPU detection decide
ACESTEP_INIT_LLM=auto

# Force enable on low VRAM GPU (GPU optimizations still applied)
ACESTEP_INIT_LLM=true
ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B

# Force disable LLM for faster generation
ACESTEP_INIT_LLM=false
```

### Development

```bash
# Add dependencies
uv add package-name
uv add --dev package-name

# Update all dependencies
uv sync --upgrade
```

## 🎮 Other GPU Support

### Intel GPU
Currently, we support Intel GPUs.
- **Tested Device**: Windows laptop with Ultra 9 285H integrated graphics.
- **Settings**:
  - `offload` is disabled by default.
  - `compile` and `quantization` are enabled by default.
- **Capabilities**: LLM inference is supported (tested with `acestep-5Hz-lm-0.6B`).
  - *Note*: LLM inference speed might decrease when generating audio longer than 2 minutes.
  - *Note*: `nanovllm` acceleration for LLM inference is currently NOT supported on Intel GPUs.
- **Test Environment**: PyTorch 2.8.0 from [Intel Extension for PyTorch](https://pytorch-extension.intel.com/?request=platform).
- **Intel Discrete GPUs**: Expected to work, but not tested yet as the developer does not have available devices. Waiting for community feedback.

## 📥 Model Download

Models are automatically downloaded from [HuggingFace](https://huggingface.co/ACE-Step/Ace-Step1.5) or [ModelScope](https://modelscope.cn/organization/ACE-Step) on first run. You can also manually download models using the CLI or `huggingface-cli`.

### Download Source Configuration

ACE-Step supports multiple download sources with automatic fallback:

| Source | Description | Configuration |
|--------|-------------|---------------|
| **auto** (default) | Automatic detection based on network, selects best source | `--download-source auto` or omit |
| **modelscope** | Use ModelScope as download source | `--download-source modelscope` |
| **huggingface** | Use HuggingFace Hub as download source | `--download-source huggingface` |

**How it works:**
- **Auto mode** (default): Tests Google connectivity. If accessible → HuggingFace Hub; if not → ModelScope
- **Manual mode**: Uses your specified source, with automatic fallback to alternate source on failure
- **Fallback protection**: If primary source fails, automatically tries the other source

**Examples:**

> **Note for Python users:** Replace `python` with your environment's Python executable (see note in Launch section above).

```bash
# Use ModelScope
uv run acestep --download-source modelscope
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --download-source modelscope

# Use HuggingFace Hub
uv run acestep --download-source huggingface
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --download-source huggingface

# Auto-detect (default, no configuration needed)
uv run acestep
# Or using Python directly:
python acestep/acestep_v15_pipeline.py
```

**For Windows portable package users**, edit `start_gradio_ui.bat` or `start_api_server.bat`:

```batch
REM Use ModelScope
set DOWNLOAD_SOURCE=--download-source modelscope

REM Use HuggingFace Hub
set DOWNLOAD_SOURCE=--download-source huggingface

REM Auto-detect (default)
set DOWNLOAD_SOURCE=
```

**For command line users:**

> **Note for Python users:** Replace `python` with your environment's Python executable (see note in Launch section above).

```bash
# Using uv
uv run acestep --download-source modelscope

# Using Python directly
python acestep/acestep_v15_pipeline.py --download-source modelscope
```

### Automatic Download

When you run `acestep` or `acestep-api`, the system will:
1. Check if the required models exist in `./checkpoints`
2. If not found, automatically download them using the configured source (or auto-detect)

### Manual Download with CLI

> **Note for Python users:** Replace `python` with your environment's Python executable (see note in Launch section above).

**Using uv:**
```bash
# Download main model (includes everything needed to run)
uv run acestep-download

# Download all available models (including optional variants)
uv run acestep-download --all

# Download from ModelScope
uv run acestep-download --download-source modelscope

# Download from HuggingFace Hub
uv run acestep-download --download-source huggingface

# Download a specific model
uv run acestep-download --model acestep-v15-sft

# List all available models
uv run acestep-download --list

# Download to a custom directory
uv run acestep-download --dir /path/to/checkpoints
```

**Using Python directly:**
```bash
# Download main model (includes everything needed to run)
python -m acestep.model_downloader

# Download all available models (including optional variants)
python -m acestep.model_downloader --all

# Download from ModelScope
python -m acestep.model_downloader --download-source modelscope

# Download from HuggingFace Hub
python -m acestep.model_downloader --download-source huggingface

# Download a specific model
python -m acestep.model_downloader --model acestep-v15-sft

# List all available models
python -m acestep.model_downloader --list

# Download to a custom directory
python -m acestep.model_downloader --dir /path/to/checkpoints
```

### Manual Download with huggingface-cli

You can also use `huggingface-cli` directly:

```bash
# Download main model (includes vae, Qwen3-Embedding-0.6B, acestep-v15-turbo, acestep-5Hz-lm-1.7B)
huggingface-cli download ACE-Step/Ace-Step1.5 --local-dir ./checkpoints

# Download optional LM models
huggingface-cli download ACE-Step/acestep-5Hz-lm-0.6B --local-dir ./checkpoints/acestep-5Hz-lm-0.6B
huggingface-cli download ACE-Step/acestep-5Hz-lm-4B --local-dir ./checkpoints/acestep-5Hz-lm-4B

# Download optional DiT models
huggingface-cli download ACE-Step/acestep-v15-base --local-dir ./checkpoints/acestep-v15-base
huggingface-cli download ACE-Step/acestep-v15-sft --local-dir ./checkpoints/acestep-v15-sft
huggingface-cli download ACE-Step/acestep-v15-turbo-shift1 --local-dir ./checkpoints/acestep-v15-turbo-shift1
huggingface-cli download ACE-Step/acestep-v15-turbo-shift3 --local-dir ./checkpoints/acestep-v15-turbo-shift3
huggingface-cli download ACE-Step/acestep-v15-turbo-continuous --local-dir ./checkpoints/acestep-v15-turbo-continuous
```

### Available Models

| Model | HuggingFace Repo | Description |
|-------|------------------|-------------|
| **Main** | [ACE-Step/Ace-Step1.5](https://huggingface.co/ACE-Step/Ace-Step1.5) | Core components: vae, Qwen3-Embedding-0.6B, acestep-v15-turbo, acestep-5Hz-lm-1.7B |
| acestep-5Hz-lm-0.6B | [ACE-Step/acestep-5Hz-lm-0.6B](https://huggingface.co/ACE-Step/acestep-5Hz-lm-0.6B) | Lightweight LM model (0.6B params) |
| acestep-5Hz-lm-4B | [ACE-Step/acestep-5Hz-lm-4B](https://huggingface.co/ACE-Step/acestep-5Hz-lm-4B) | Large LM model (4B params) |
| acestep-v15-base | [ACE-Step/acestep-v15-base](https://huggingface.co/ACE-Step/acestep-v15-base) | Base DiT model |
| acestep-v15-sft | [ACE-Step/acestep-v15-sft](https://huggingface.co/ACE-Step/acestep-v15-sft) | SFT DiT model |
| acestep-v15-turbo-shift1 | [ACE-Step/acestep-v15-turbo-shift1](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift1) | Turbo DiT with shift1 |
| acestep-v15-turbo-shift3 | [ACE-Step/acestep-v15-turbo-shift3](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift3) | Turbo DiT with shift3 |
| acestep-v15-turbo-continuous | [ACE-Step/acestep-v15-turbo-continuous](https://huggingface.co/ACE-Step/acestep-v15-turbo-continuous) | Turbo DiT with continuous shift (1-5) |

### 💡 Which Model Should I Choose?

ACE-Step automatically adapts to your GPU's VRAM. Here's a quick guide:

| Your GPU VRAM | Recommended LM Model | Notes |
|---------------|---------------------|-------|
| **≤6GB** | None (DiT only) | LM disabled by default to save memory |
| **6-12GB** | `acestep-5Hz-lm-0.6B` | Lightweight, good balance |
| **12-16GB** | `acestep-5Hz-lm-1.7B` | Better quality |
| **≥16GB** | `acestep-5Hz-lm-4B` | Best quality and audio understanding |

> 📖 **For detailed GPU compatibility information** (duration limits, batch sizes, memory optimization), see GPU Compatibility Guide: [English](./docs/en/GPU_COMPATIBILITY.md) | [中文](./docs/zh/GPU_COMPATIBILITY.md) | [日本語](./docs/ja/GPU_COMPATIBILITY.md)


## 🚀 Usage

We provide multiple ways to use ACE-Step:

| Method | Description | Documentation |
|--------|-------------|---------------|
| 🖥️ **Gradio Web UI** | Interactive web interface for music generation | [Gradio Guide](./docs/en/GRADIO_GUIDE.md) |
| 🎚️ **Studio UI (Experimental)** | Optional HTML frontend for REST API (DAW-like) | [Studio UI](./docs/en/studio.md) |
| 🐍 **Python API** | Programmatic access for integration | [Inference API](./docs/en/INFERENCE.md) |
| 🌐 **REST API** | HTTP-based async API for services | [REST API](./docs/en/API.md) |

**📚 Documentation available in:** [English](./docs/en/) | [中文](./docs/zh/) | [日本語](./docs/ja/)

### Experimental Studio UI

An optional, frontend-only HTML Studio UI is available for users who prefer a more structured interface. It uses the same REST API and does not change backend behavior. Start the API server, then open `ui/studio.html` in a browser and point it at your API URL. See [Studio UI](./docs/en/studio.md).

## 📖 Tutorial

**🎯 Must Read:** Comprehensive guide to ACE-Step 1.5's design philosophy and usage methods.

| Language | Link |
|----------|------|
| 🇺🇸 English | [English Tutorial](./docs/en/Tutorial.md) |
| 🇨🇳 中文 | [中文教程](./docs/zh/Tutorial.md) |
| 🇯🇵 日本語 | [日本語チュートリアル](./docs/ja/Tutorial.md) |

This tutorial covers:
- Mental models and design philosophy
- Model architecture and selection
- Input control (text and audio)
- Inference hyperparameters
- Random factors and optimization strategies

## 🔨 Train

See the **LoRA Training** tab in Gradio UI for one-click training, or check [Gradio Guide - LoRA Training](./docs/en/GRADIO_GUIDE.md#lora-training) for details.

## 🏗️ Architecture

<p align="center">
    <img src="./assets/ACE-Step_framework.png" width="100%" alt="ACE-Step Framework">
</p>

## 🦁 Model Zoo

<p align="center">
    <img src="./assets/model_zoo.png" width="100%" alt="Model Zoo">
</p>

### DiT Models

| DiT Model | Pre-Training | SFT | RL | CFG | Step | Refer audio | Text2Music | Cover | Repaint | Extract | Lego | Complete | Quality | Diversity | Fine-Tunability | Hugging Face |
|-----------|:------------:|:---:|:--:|:---:|:----:|:-----------:|:----------:|:-----:|:-------:|:-------:|:----:|:--------:|:-------:|:---------:|:---------------:|--------------|
| `acestep-v15-base` | ✅ | ❌ | ❌ | ✅ | 50 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Medium | High | Easy | [Link](https://huggingface.co/ACE-Step/acestep-v15-base) |
| `acestep-v15-sft` | ✅ | ✅ | ❌ | ✅ | 50 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | High | Medium | Easy | [Link](https://huggingface.co/ACE-Step/acestep-v15-sft) |
| `acestep-v15-turbo` | ✅ | ✅ | ❌ | ❌ | 8 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | Very High | Medium | Medium | [Link](https://huggingface.co/ACE-Step/Ace-Step1.5) |
| `acestep-v15-turbo-rl` | ✅ | ✅ | ✅ | ❌ | 8 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | Very High | Medium | Medium | To be released |

### LM Models

| LM Model | Pretrain from | Pre-Training | SFT | RL | CoT metas | Query rewrite | Audio Understanding | Composition Capability | Copy Melody | Hugging Face |
|----------|---------------|:------------:|:---:|:--:|:---------:|:-------------:|:-------------------:|:----------------------:|:-----------:|--------------|
| `acestep-5Hz-lm-0.6B` | Qwen3-0.6B | ✅ | ✅ | ✅ | ✅ | ✅ | Medium | Medium | Weak | ✅ |
| `acestep-5Hz-lm-1.7B` | Qwen3-1.7B | ✅ | ✅ | ✅ | ✅ | ✅ | Medium | Medium | Medium | ✅ |
| `acestep-5Hz-lm-4B` | Qwen3-4B | ✅ | ✅ | ✅ | ✅ | ✅ | Strong | Strong | Strong | ✅ |

## 📜 License & Disclaimer

This project is licensed under [MIT](./LICENSE)

ACE-Step enables original music generation across diverse genres, with applications in creative production, education, and entertainment. While designed to support positive and artistic use cases, we acknowledge potential risks such as unintentional copyright infringement due to stylistic similarity, inappropriate blending of cultural elements, and misuse for generating harmful content. To ensure responsible use, we encourage users to verify the originality of generated works, clearly disclose AI involvement, and obtain appropriate permissions when adapting protected styles or materials. By using ACE-Step, you agree to uphold these principles and respect artistic integrity, cultural diversity, and legal compliance. The authors are not responsible for any misuse of the model, including but not limited to copyright violations, cultural insensitivity, or the generation of harmful content.

🔔 Important Notice  
The only official website for the ACE-Step project is our GitHub Pages site.    
 We do not operate any other websites.  
🚫 Fake domains include but are not limited to:
ac\*\*p.com, a\*\*p.org, a\*\*\*c.org  
⚠️ Please be cautious. Do not visit, trust, or make payments on any of those sites.

## 🙏 Acknowledgements

This project is co-led by ACE Studio and StepFun.


## 📖 Citation

If you find this project useful for your research, please consider citing:

```BibTeX
@misc{gong2026acestep,
	title={ACE-Step 1.5: Pushing the Boundaries of Open-Source Music Generation},
	author={Junmin Gong, Yulin Song, Wenxiao Zhao, Sen Wang, Shengyuan Xu, Jing Guo}, 
	howpublished={\url{https://github.com/ace-step/ACE-Step-1.5}},
	year={2026},
	note={GitHub repository}
}
```
