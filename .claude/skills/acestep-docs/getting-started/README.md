# ACE-Step Installation Guide

## Requirements

- Python 3.11
- CUDA GPU recommended (works on CPU/MPS but slower)

## Installation

### Windows Portable Package (Recommended for Windows)

1. Download and extract: [ACE-Step-1.5.7z](https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z)
2. Requirements: CUDA 12.8
3. The package includes `python_embeded` with all dependencies pre-installed

**Quick Start (Using Batch Scripts):**
```bash
# Launch Gradio Web UI
start_gradio_ui.bat

# Launch REST API Server
start_api_server.bat
```

Both scripts support:
- ✅ Auto environment detection (`python_embeded` or `uv`)
- ✅ Auto install `uv` if needed (via winget or PowerShell)
- ✅ Configurable download source (HuggingFace/ModelScope)
- ✅ Optional Git update check
- ✅ Customizable language, models, and parameters

**Manual Launch (Using Python Directly):**
```bash
# Gradio Web UI
python_embeded\python.exe acestep\acestep_v15_pipeline.py

# REST API Server
python_embeded\python.exe acestep\api_server.py
```

### Standard Installation (All Platforms)

**1. Install uv (Package Manager)**
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**2. Clone & Install**
```bash
git clone https://github.com/ACE-Step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync
```

**3. Launch**

**Using uv:**
```bash
# Gradio Web UI (http://localhost:7860)
uv run acestep

# REST API Server (http://localhost:8001)
uv run acestep-api
```

**Using Python directly:**

> **Note:** Make sure to activate your Python environment first:
> - **Conda environment**: Run `conda activate your_env_name` first
> - **venv**: Run `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows) first
> - **System Python**: Use `python` or `python3` directly

```bash
# Gradio Web UI
python acestep/acestep_v15_pipeline.py

# REST API Server
python acestep/api_server.py
```

## Model Download

Models are automatically downloaded on first run. Manual download options:

### Download Source Configuration

ACE-Step supports multiple download sources:

| Source | Description |
|--------|-------------|
| **auto** (default) | Auto-detect best source based on network |
| **modelscope** | Use ModelScope as download source |
| **huggingface** | Use HuggingFace Hub as download source |

**Using uv:**
```bash
# Download main model
uv run acestep-download

# Download from ModelScope
uv run acestep-download --download-source modelscope

# Download from HuggingFace Hub
uv run acestep-download --download-source huggingface

# Download all models
uv run acestep-download --all

# List available models
uv run acestep-download --list
```

**Using Python directly:**

> **Note:** Replace `python` with your environment's Python executable:
> - Windows portable package: `python_embeded\python.exe`
> - Conda/venv: Activate environment first, then use `python`
> - System: Use `python` or `python3`

```bash
# Download main model
python -m acestep.model_downloader

# Download from ModelScope
python -m acestep.model_downloader --download-source modelscope

# Download from HuggingFace Hub
python -m acestep.model_downloader --download-source huggingface

# Download all models
python -m acestep.model_downloader --all

# List available models
python -m acestep.model_downloader --list
```

### GPU VRAM Recommendations

| GPU VRAM | Recommended LM Model | Notes |
|----------|---------------------|-------|
| ≤6GB | None (DiT only) | LM disabled to save memory |
| 6-12GB | `acestep-5Hz-lm-0.6B` | Lightweight, good balance |
| 12-16GB | `acestep-5Hz-lm-1.7B` | Better quality |
| ≥16GB | `acestep-5Hz-lm-4B` | Best quality |

## Command Line Options

### Gradio UI (`acestep`)

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | 7860 | Server port |
| `--server-name` | 127.0.0.1 | Server address (`0.0.0.0` for network) |
| `--share` | false | Create public Gradio link |
| `--language` | en | UI language: `en`, `zh`, `ja` |
| `--init_service` | false | Auto-initialize models on startup |
| `--config_path` | auto | DiT model name |
| `--lm_model_path` | auto | LM model name |
| `--offload_to_cpu` | auto | CPU offload (auto if VRAM < 16GB) |
| `--download-source` | auto | Model download source: `auto`, `huggingface`, or `modelscope` |
| `--enable-api` | false | Enable REST API endpoints |
| `--api-key` | none | API authentication key |

**Examples:**

> **Note for Python users:** Replace `python` with your environment's Python executable (see note in Launch section above).

```bash
# Public access with Chinese UI
uv run acestep --server-name 0.0.0.0 --share --language zh
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --server-name 0.0.0.0 --share --language zh

# Pre-initialize models
uv run acestep --init_service true --config_path acestep-v15-turbo
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --init_service true --config_path acestep-v15-turbo

# Enable API with authentication
uv run acestep --enable-api --api-key sk-your-secret-key
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --enable-api --api-key sk-your-secret-key

# Use ModelScope as download source
uv run acestep --download-source modelscope
# Or using Python directly:
python acestep/acestep_v15_pipeline.py --download-source modelscope
```

### REST API Server (`acestep-api`)

Same options as Gradio UI. See [API documentation](../api/API.md) for endpoints.
