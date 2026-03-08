# Launch Script Configuration Guide

This guide explains how to configure the startup scripts for ACE-Step across all supported platforms: Windows (.bat), Linux (.sh), and macOS (.sh).

> **Note for uv/Python users**: If you're using `uv run acestep` or running Python directly (not using launch scripts), configure settings via the `.env` file instead. See [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md#environment-variables-env) for details.

## How to Modify

All configurable options are variables at the top of each script. Open the script with any text editor and modify the values.

**Windows (.bat)**:
- Set a variable: `set VARIABLE=value`
- Comment out a line: `REM set VARIABLE=value`
- Uncomment a line: Remove the leading `REM`

**Linux/macOS (.sh)**:
- Set a variable: `VARIABLE="value"`
- Comment out a line: `# VARIABLE="value"`
- Uncomment a line: Remove the leading `#`

---

## Available Launch Scripts

| Platform | Script | Purpose |
|----------|--------|---------|
| Windows (NVIDIA) | `start_gradio_ui.bat` | Gradio Web UI |
| Windows (NVIDIA) | `start_api_server.bat` | REST API Server |
| Windows (AMD ROCm) | `start_gradio_ui_rocm.bat` | Gradio Web UI for AMD GPUs |
| Windows (AMD ROCm) | `start_api_server_rocm.bat` | REST API Server for AMD GPUs |
| Linux (CUDA) | `start_gradio_ui.sh` | Gradio Web UI |
| Linux (CUDA) | `start_api_server.sh` | REST API Server |
| macOS (Apple Silicon) | `start_gradio_ui_macos.sh` | Gradio Web UI (MLX backend) |
| macOS (Apple Silicon) | `start_api_server_macos.sh` | REST API Server (MLX backend) |

---

## Configuration Sections

### 1. UI Language

Controls the language displayed in the Gradio Web UI.

**Options**: `en` (English), `zh` (Chinese), `he` (Hebrew), `ja` (Japanese)

**Windows (.bat)**:
```batch
REM UI language: en, zh, he, ja
set LANGUAGE=en
```

**Linux/macOS (.sh)**:
```bash
# UI language: en, zh, he, ja
LANGUAGE="en"
```

**Example -- switch to Chinese**:

| Platform | Setting |
|----------|---------|
| Windows | `set LANGUAGE=zh` |
| Linux/macOS | `LANGUAGE="zh"` |

> **Note**: The `LANGUAGE` variable is only available in Gradio UI scripts. API server scripts do not have a UI language setting.

---

### 2. Server Port

Controls which port the server listens on and which address it binds to.

**Gradio UI scripts**:

| Platform | Default Port | Default Address |
|----------|-------------|-----------------|
| Windows | `7860` | `127.0.0.1` |
| Linux | `7860` | `127.0.0.1` |
| macOS | `7860` | `127.0.0.1` |

**Windows (.bat)** -- Gradio UI:
```batch
REM Server settings
set PORT=7860
set SERVER_NAME=127.0.0.1
REM set SERVER_NAME=0.0.0.0
REM set SHARE=--share
```

**Linux/macOS (.sh)** -- Gradio UI:
```bash
# Server settings
PORT=7860
SERVER_NAME="127.0.0.1"
# SERVER_NAME="0.0.0.0"
SHARE=""
# SHARE="--share"
```

**API Server scripts**:

| Platform | Default Port | Default Host |
|----------|-------------|--------------|
| Windows | `8001` | `127.0.0.1` |
| Linux | `8001` | `127.0.0.1` |
| macOS | `8001` | `127.0.0.1` |

**Windows (.bat)** -- API Server:
```batch
set HOST=127.0.0.1
set PORT=8001
```

**Linux/macOS (.sh)** -- API Server:
```bash
HOST="127.0.0.1"
PORT=8001
```

**Default URLs**:
- Gradio UI: http://127.0.0.1:7860
- API Server: http://127.0.0.1:8001
- API Documentation: http://127.0.0.1:8001/docs

**To expose to the network** (allow access from other devices):
- Set `SERVER_NAME` or `HOST` to `0.0.0.0`
- Or enable `SHARE` for Gradio's public sharing link

---

### 3. Download Source

Controls where model files are downloaded from. Affects all scripts that download models.

**Windows (.bat)**:
```batch
REM Download source: auto (default), huggingface, or modelscope
REM set DOWNLOAD_SOURCE=--download-source modelscope
REM set DOWNLOAD_SOURCE=--download-source huggingface
set DOWNLOAD_SOURCE=
```

**Linux/macOS (.sh)**:
```bash
# Download source: auto (default), huggingface, or modelscope
DOWNLOAD_SOURCE=""
# DOWNLOAD_SOURCE="--download-source modelscope"
# DOWNLOAD_SOURCE="--download-source huggingface"
```

**Options**:

| Value | When to Use | Speed |
|-------|-------------|-------|
| (empty) or `auto` | Auto-detect network | Automatic |
| `modelscope` | China mainland users | Fast in China |
| `huggingface` | Overseas users | Fast outside China |

**How auto-detection works**:
1. Tests Google connectivity
   - Can access Google --> uses HuggingFace Hub
   - Cannot access Google --> uses ModelScope
2. If primary source fails, falls back to the alternate source

**Examples**:

| Platform | China Users | Overseas Users |
|----------|-------------|----------------|
| Windows | `set DOWNLOAD_SOURCE=--download-source modelscope` | `set DOWNLOAD_SOURCE=--download-source huggingface` |
| Linux/macOS | `DOWNLOAD_SOURCE="--download-source modelscope"` | `DOWNLOAD_SOURCE="--download-source huggingface"` |

---

### 4. Update Check

Controls whether the script checks GitHub for updates before launching.

**Default**: `true` (enabled)

**Windows (.bat)**:
```batch
REM Update check on startup (set to false to disable)
set CHECK_UPDATE=true
REM set CHECK_UPDATE=false
```

**Linux/macOS (.sh)**:
```bash
# Update check on startup (set to "false" to disable)
CHECK_UPDATE="true"
# CHECK_UPDATE="false"
```

**Git detection by platform**:

| Platform | Git Resolution |
|----------|---------------|
| Windows | Tries `PortableGit\bin\git.exe` first, then falls back to system `git` (e.g., Git for Windows) |
| Linux | Uses system `git` |
| macOS | Uses system `git` (Xcode Command Line Tools or Homebrew) |

> **Important**: On Windows, PortableGit is no longer strictly required. If you have Git for Windows installed system-wide, the update check will find it automatically.

**Behavior when enabled**:
1. Fetches latest commits from GitHub with a 10 second timeout
2. Compares local commit hash against remote
3. If an update is available, shows new commits and prompts `Y/N`
4. If the network is unreachable or the fetch times out, automatically skips and continues startup

**Timeout handling by platform**:
- Linux: Uses `timeout` command (10 seconds)
- macOS: Uses `gtimeout` (from coreutils) or `timeout` if available, otherwise runs without timeout
- Windows: Network-level timeout via `git fetch`

See [UPDATE_AND_BACKUP.md](UPDATE_AND_BACKUP.md) for full details on the update process and file backup.

---

### 5. Model Configuration

Controls which DiT model and Language Model (LM) are loaded.

**Windows (.bat)** -- Gradio UI:
```batch
REM Model settings
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
REM set OFFLOAD_TO_CPU=--offload_to_cpu true
```

**Linux/macOS (.sh)** -- Gradio UI:
```bash
# Model settings
CONFIG_PATH="--config_path acestep-v15-turbo"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-0.6B"
# OFFLOAD_TO_CPU="--offload_to_cpu true"
OFFLOAD_TO_CPU=""
```

**API Server** -- Windows (.bat):
```batch
REM LM model path (optional, only used when LLM is enabled)
REM set LM_MODEL_PATH=--lm-model-path acestep-5Hz-lm-0.6B
```

**API Server** -- Linux/macOS (.sh):
```bash
# LM model path (optional, only used when LLM is enabled)
LM_MODEL_PATH=""
# LM_MODEL_PATH="--lm-model-path acestep-5Hz-lm-0.6B"
```

> **Note**: The API server uses `--lm-model-path` (hyphens) while the Gradio UI uses `--lm_model_path` (underscores).

**Available DiT Models**:

| Model | Description |
|-------|-------------|
| `acestep-v15-turbo` | Default turbo model (8 steps, no CFG) |
| `acestep-v15-base` | Base model (50 steps, with CFG, high diversity) |
| `acestep-v15-sft` | SFT model (50 steps, with CFG, high quality) |
| `acestep-v15-turbo-shift1` | Turbo with shift1 |
| `acestep-v15-turbo-shift3` | Turbo with shift3 |
| `acestep-v15-turbo-continuous` | Turbo with continuous shift (1-5) |

**Available Language Models**:

| LM Model | Size | Quality |
|----------|------|---------|
| `acestep-5Hz-lm-0.6B` | 0.6B | Standard |
| `acestep-5Hz-lm-1.7B` | 1.7B | Better |
| `acestep-5Hz-lm-4B` | 4B | Best (requires more VRAM/RAM) |

**CPU Offload**: Enable `OFFLOAD_TO_CPU` when using larger models (especially 4B) on GPUs with limited VRAM. Models shuttle between CPU and GPU as needed, adding ~8-10s overhead per generation but preventing VRAM oversubscription.

---

### 6. LLM Initialization Control

Controls whether the Language Model (5Hz LM) is initialized at startup. By default, LLM is automatically enabled or disabled based on GPU VRAM:
- **<=6GB VRAM**: LLM disabled (DiT-only mode)
- **>6GB VRAM**: LLM enabled

**Processing Flow:**
```
GPU Detection (full) --> ACESTEP_INIT_LLM / INIT_LLM Override --> Model Loading
```

GPU optimizations (offload, quantization, batch limits) are **always applied** regardless of this setting. The override only controls whether to attempt LLM loading.

**Gradio UI** -- Windows (.bat):
```batch
REM LLM initialization: auto (default), true, false
REM set INIT_LLM=--init_llm auto
REM set INIT_LLM=--init_llm true
REM set INIT_LLM=--init_llm false
```

**Gradio UI** -- Linux/macOS (.sh):
```bash
# LLM initialization: auto (default), true, false
INIT_LLM=""
# INIT_LLM="--init_llm auto"
# INIT_LLM="--init_llm true"
# INIT_LLM="--init_llm false"
```

**API Server** -- Windows (.bat):
```batch
REM Values: auto (default), true (force enable), false (force disable)
REM set ACESTEP_INIT_LLM=auto
REM set ACESTEP_INIT_LLM=true
REM set ACESTEP_INIT_LLM=false
```

**API Server** -- Linux/macOS (.sh):
```bash
# Values: auto (default), true (force enable), false (force disable)
# export ACESTEP_INIT_LLM=auto
# export ACESTEP_INIT_LLM=true
# export ACESTEP_INIT_LLM=false
```

> **Note**: Gradio UI scripts use `--init_llm` as a command-line argument. API server scripts use the `ACESTEP_INIT_LLM` environment variable.

**When to use**:

| Setting | Use Case |
|---------|----------|
| `auto` (default) | Let GPU detection decide (recommended) |
| `true` | Force LLM on low VRAM GPU (GPU optimizations still applied, may cause OOM) |
| `false` | Pure DiT mode for faster generation, no LLM features |

**Features affected by LLM**:
- **Thinking mode**: LLM generates audio codes for better quality
- **Chain-of-Thought (CoT)**: Auto-enhance captions, detect language, generate metadata
- **Sample mode**: Generate random songs from descriptions
- **Format mode**: Enhance user input via LLM

When LLM is disabled, these features are automatically disabled, and generation uses pure DiT mode.

---

## Complete Configuration Examples

### Chinese Users

**Windows (.bat)** -- `start_gradio_ui.bat`:
```batch
REM UI language
set LANGUAGE=zh

REM Server port
set PORT=7860
set SERVER_NAME=127.0.0.1

REM Download source
set DOWNLOAD_SOURCE=--download-source modelscope

REM Update check
set CHECK_UPDATE=true

REM Model settings
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
```

**Linux (.sh)** -- `start_gradio_ui.sh`:
```bash
# UI language
LANGUAGE="zh"

# Server port
PORT=7860
SERVER_NAME="127.0.0.1"

# Download source
DOWNLOAD_SOURCE="--download-source modelscope"

# Update check
CHECK_UPDATE="true"

# Model settings
CONFIG_PATH="--config_path acestep-v15-turbo"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-0.6B"
```

---

### Overseas Users

**Windows (.bat)** -- `start_gradio_ui.bat`:
```batch
REM UI language
set LANGUAGE=en

REM Server port
set PORT=7860
set SERVER_NAME=127.0.0.1

REM Download source
set DOWNLOAD_SOURCE=--download-source huggingface

REM Update check
set CHECK_UPDATE=true

REM Model settings
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
```

**Linux (.sh)** -- `start_gradio_ui.sh`:
```bash
# UI language
LANGUAGE="en"

# Server port
PORT=7860
SERVER_NAME="127.0.0.1"

# Download source
DOWNLOAD_SOURCE="--download-source huggingface"

# Update check
CHECK_UPDATE="true"

# Model settings
CONFIG_PATH="--config_path acestep-v15-turbo"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-1.7B"
```

---

### macOS Users (Apple Silicon / MLX)

**`start_gradio_ui_macos.sh`**:
```bash
# MLX backend is set automatically by the script:
# export ACESTEP_LM_BACKEND="mlx"

# UI language
LANGUAGE="en"

# Server port
PORT=7860
SERVER_NAME="127.0.0.1"

# Download source (HuggingFace recommended outside China)
DOWNLOAD_SOURCE="--download-source huggingface"

# Update check
CHECK_UPDATE="true"

# Model settings
CONFIG_PATH="--config_path acestep-v15-turbo"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-0.6B"

# MLX backend (set automatically, do not change)
BACKEND="--backend mlx"

# CPU offload (enable for models larger than 0.6B on limited memory)
OFFLOAD_TO_CPU=""
# OFFLOAD_TO_CPU="--offload_to_cpu true"
```

> **Note**: The macOS scripts automatically detect Apple Silicon (arm64). On Intel Macs, the MLX backend is unavailable and the script falls back to the PyTorch backend.

---

## ROCm Configuration

The `start_gradio_ui_rocm.bat` and `start_api_server_rocm.bat` scripts include additional settings specific to AMD GPUs running ROCm on Windows.

### ROCm-Specific Variables

```batch
REM ==================== ROCm Configuration ====================
REM Force PyTorch LM backend (bypasses nano-vllm flash_attn dependency)
set ACESTEP_LM_BACKEND=pt

REM RDNA3 GPU architecture override
set HSA_OVERRIDE_GFX_VERSION=11.0.0

REM Disable torch.compile Triton backend (not available on ROCm Windows)
set TORCH_COMPILE_BACKEND=eager

REM MIOpen: fast heuristic kernel selection instead of exhaustive benchmarking
set MIOPEN_FIND_MODE=FAST

REM HuggingFace tokenizer parallelism
set TOKENIZERS_PARALLELISM=false
```

**Variable details**:

| Variable | Purpose | Common Values |
|----------|---------|---------------|
| `ACESTEP_LM_BACKEND` | Forces PyTorch backend instead of vLLM | `pt` (required for ROCm) |
| `HSA_OVERRIDE_GFX_VERSION` | Overrides GPU architecture for ROCm compatibility | `11.0.0` (gfx1100, RX 7900 XT/XTX), `11.0.1` (gfx1101, RX 7700/7800 XT), `11.0.2` (gfx1102, RX 7600) |
| `TORCH_COMPILE_BACKEND` | Sets the torch.compile backend | `eager` (required, Triton unavailable on ROCm Windows) |
| `MIOPEN_FIND_MODE` | Controls MIOpen kernel selection strategy | `FAST` (recommended; prevents first-run hangs on VAE decode) |
| `TOKENIZERS_PARALLELISM` | Controls HuggingFace tokenizer parallelism | `false` (suppresses warnings) |

**ROCm model settings**:

```batch
REM Model settings (ROCm)
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-4B

REM CPU offload: required for 4B LM on GPUs with <=20GB VRAM
set OFFLOAD_TO_CPU=--offload_to_cpu true

REM LM backend: pt (PyTorch) recommended for ROCm
set BACKEND=--backend pt
```

**ROCm virtual environment**:

The ROCm script uses a separate virtual environment (`venv_rocm`) instead of the standard `.venv` or `python_embeded`:
```batch
set VENV_DIR=%~dp0venv_rocm
```

> **Note**: The ROCm script requires a separate Python environment with ROCm-compatible PyTorch installed. See `requirements-rocm.txt` for setup instructions.

---

## Troubleshooting

### Changes not taking effect

**Solution**: Save the file and restart the script. Changes only apply on the next launch.

Windows:
```batch
REM Close current process (Ctrl+C), then run again
start_gradio_ui.bat
```

Linux/macOS:
```bash
# Close current process (Ctrl+C), then run again
./start_gradio_ui.sh
```

### Model download is slow

**For Chinese users** -- set ModelScope:

| Platform | Setting |
|----------|---------|
| Windows | `set DOWNLOAD_SOURCE=--download-source modelscope` |
| Linux/macOS | `DOWNLOAD_SOURCE="--download-source modelscope"` |

**For overseas users** -- set HuggingFace:

| Platform | Setting |
|----------|---------|
| Windows | `set DOWNLOAD_SOURCE=--download-source huggingface` |
| Linux/macOS | `DOWNLOAD_SOURCE="--download-source huggingface"` |

### Wrong language displayed

Verify the `LANGUAGE` variable in your Gradio UI script:

| Platform | Chinese | English |
|----------|---------|---------|
| Windows | `set LANGUAGE=zh` | `set LANGUAGE=en` |
| Linux/macOS | `LANGUAGE="zh"` | `LANGUAGE="en"` |

### Port already in use

**Error**: `Address already in use`

**Solution 1**: Change the port number.

| Platform | Setting |
|----------|---------|
| Windows | `set PORT=7861` |
| Linux/macOS | `PORT=7861` |

**Solution 2**: Find and close the process using the port.

Windows:
```batch
REM Find process using port 7860
netstat -ano | findstr :7860

REM Kill process (replace <PID> with the actual process ID)
taskkill /PID <PID> /F
```

Linux/macOS:
```bash
# Find process using port 7860
lsof -i :7860

# Kill process (replace <PID> with the actual process ID)
kill <PID>
```

---

## Best Practices

1. **Backup before editing**: Make a copy of the script before modifying it.
   - Windows: `copy start_gradio_ui.bat start_gradio_ui.bat.backup`
   - Linux/macOS: `cp start_gradio_ui.sh start_gradio_ui.sh.backup`

2. **Use comments to document your changes**: Add a note explaining why you changed a value so you remember later.
   - Windows: `REM Changed to port 8080 for testing`
   - Linux/macOS: `# Changed to port 8080 for testing`

3. **Test after changes**: Save the file, close any running instance, re-launch the script, and verify the changes took effect.
