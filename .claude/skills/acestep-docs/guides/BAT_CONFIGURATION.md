# BAT File Configuration Guide

This guide explains how to configure the startup scripts (`start_gradio_ui.bat` and `start_api_server.bat`).

> **Note for uv/Python users**: If you're using `uv run acestep` or running Python directly (not using bat files), configure settings via the `.env` file instead. See [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md#environment-variables-env) for details.

## Configuration Sections

### 1. UI Language

**Location**: `start_gradio_ui.bat`

```batch
REM UI language: en (English) or zh (中文)
set LANGUAGE=en
```

**Options**:
- `en` - English interface
- `zh` - Chinese interface

**Example**:
```batch
set LANGUAGE=zh
```

---

### 2. Server Port

**Gradio UI** (`start_gradio_ui.bat`):
```batch
REM Server port
set PORT=7860
```

**API Server** (`start_api_server.bat`):
```batch
REM Server port
set PORT=8001

REM Server host
set HOST=127.0.0.1
```

**Default Ports**:
- Gradio UI: `7860` → http://127.0.0.1:7860
- API Server: `8001` → http://127.0.0.1:8001

**Changing Ports**:
```batch
REM Use port 8080 instead
set PORT=8080
```

---

### 3. Download Source

**Location**: Both `start_gradio_ui.bat` and `start_api_server.bat`

```batch
REM Download source: auto (default), huggingface, or modelscope
set DOWNLOAD_SOURCE=
```

**Options**:

| Value | When to Use | Speed |
|-------|-------------|-------|
| (empty) or `auto` | Auto-detect network | Automatic |
| `modelscope` | China mainland users | Fast in China |
| `huggingface` | Overseas users | Fast outside China |

**Examples**:

```batch
REM For Chinese users
set DOWNLOAD_SOURCE=--download-source modelscope

REM For overseas users
set DOWNLOAD_SOURCE=--download-source huggingface

REM Auto-detect (default)
set DOWNLOAD_SOURCE=
```

**How it works**:
1. Auto mode: Tests Google connectivity
   - Can access Google → HuggingFace Hub
   - Cannot access Google → ModelScope
2. Manual mode: Uses specified source
3. Fallback: If primary source fails, tries alternate source

---

### 4. Update Check

**Location**: Both startup scripts

```batch
REM Update check: true or false (requires PortableGit)
set CHECK_UPDATE=false
```

**Requirements**:
- PortableGit installed at `PortableGit\bin\git.exe`
- Valid Git repository
- Internet connection

**Options**:
- `false` (default) - No update check
- `true` - Check GitHub for updates on startup

**Example**:
```batch
set CHECK_UPDATE=true
```

**Behavior when enabled**:
1. Checks GitHub for updates (10 second timeout)
2. If update available, prompts user
3. If timeout/error, skips and continues startup

See [UPDATE_AND_BACKUP.md](UPDATE_AND_BACKUP.md) for details.

---

### 5. Model Configuration

**Location**: `start_gradio_ui.bat`

```batch
REM Model settings
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
```

**Available Models**:

| Model | Size | Performance | VRAM |
|-------|------|-------------|------|
| `acestep-v15-turbo` | Standard | Balanced | ~4GB |
| `acestep-v15-quality` | Large | High quality | ~8GB |

**Language Models**:

| LM Model | Size | Quality |
|----------|------|---------|
| `acestep-5Hz-lm-0.6B` | 0.6B | Standard |
| `acestep-5Hz-lm-1.7B` | 1.7B | Better |

**Example**:
```batch
REM Use higher quality models
set CONFIG_PATH=--config_path acestep-v15-quality
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
```

---

### 6. LLM Initialization Control

**Location**: Both `start_gradio_ui.bat` and `start_api_server.bat`

By default, LLM (Language Model) is automatically enabled/disabled based on GPU VRAM:
- **≤6GB VRAM**: LLM disabled (DiT-only mode)
- **>6GB VRAM**: LLM enabled

**Processing Flow:**
```
GPU Detection (full) → ACESTEP_INIT_LLM Override → Model Loading
```

GPU optimizations (offload, quantization, batch limits) are **always applied**.
The override only controls whether to attempt LLM loading.

You can override this behavior:

**Gradio UI** (`start_gradio_ui.bat`):
```batch
REM Force enable LLM (GPU optimizations still applied)
set INIT_LLM=--init_llm true

REM Force disable LLM (pure DiT mode, faster)
set INIT_LLM=--init_llm false
```

**API Server** (`start_api_server.bat`):
```batch
REM Auto mode (recommended) - let GPU detection decide
set ACESTEP_INIT_LLM=auto

REM Force enable LLM via environment variable
set ACESTEP_INIT_LLM=true

REM Force disable LLM
set ACESTEP_INIT_LLM=false

REM Optionally specify LM model path
set LM_MODEL_PATH=--lm-model-path acestep-5Hz-lm-0.6B
```

**When to use**:

| Setting | Use Case |
|---------|----------|
| `auto` | Let GPU detection decide (recommended) |
| `true` | Force LLM on low VRAM GPU (GPU optimizations still applied, may OOM) |
| `false` | Pure DiT mode for faster generation |

**Features affected by LLM**:
- **Thinking mode**: LLM generates audio codes for better quality
- **Chain-of-Thought (CoT)**: Auto-enhance captions, detect language, generate metadata
- **Sample mode**: Generate random songs from descriptions
- **Format mode**: Enhance user input via LLM

When LLM is disabled, these features are automatically disabled, and generation uses pure DiT mode.

---

## Complete Configuration Examples

### For Chinese Users

**start_gradio_ui.bat**:
```batch
REM UI language
set LANGUAGE=zh

REM Server port
set PORT=7860

REM Download source
set DOWNLOAD_SOURCE=--download-source modelscope

REM Update check (optional)
set CHECK_UPDATE=false

REM Model settings
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
```

### For Overseas Users

**start_gradio_ui.bat**:
```batch
REM UI language
set LANGUAGE=en

REM Server port
set PORT=7860

REM Download source
set DOWNLOAD_SOURCE=--download-source huggingface

REM Update check (optional)
set CHECK_UPDATE=false

REM Model settings
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
```

### For Portable Package with Updates

**start_gradio_ui.bat**:
```batch
REM UI language
set LANGUAGE=zh

REM Server port
set PORT=7860

REM Download source
set DOWNLOAD_SOURCE=--download-source modelscope

REM Enable update check (requires PortableGit)
set CHECK_UPDATE=true

REM Model settings
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
```

---

## API Server Configuration

**start_api_server.bat**:
```batch
REM Server host (usually keep as 127.0.0.1)
set HOST=127.0.0.1

REM Server port
set PORT=8001

REM Download source (same as Gradio UI)
set DOWNLOAD_SOURCE=--download-source modelscope

REM Update check (same as Gradio UI)
set CHECK_UPDATE=false
```

**Note**: Most users only need to configure `DOWNLOAD_SOURCE`. Other settings work well with defaults.

---

## Troubleshooting

### Changes not taking effect

**Solution**: Save the file and restart the script
```batch
# Close current process (Ctrl+C)
# Run again
start_gradio_ui.bat
```

### Model download is slow

**For Chinese users**:
```batch
set DOWNLOAD_SOURCE=--download-source modelscope
```

**For overseas users**:
```batch
set DOWNLOAD_SOURCE=--download-source huggingface
```

### Wrong language displayed

**Check**:
```batch
set LANGUAGE=zh  # Chinese
set LANGUAGE=en  # English
```

### Port already in use

**Error**: `Address already in use`

**Solution**: Change port number
```batch
REM Use different port
set PORT=7861
```

Or close the application using that port:
```batch
# Find process using port 7860
netstat -ano | findstr :7860

# Kill process (replace PID)
taskkill /PID <PID> /F
```

---

## Best Practices

1. **Make a backup** before editing:
   ```batch
   copy start_gradio_ui.bat start_gradio_ui.bat.backup
   ```

2. **Use comments** to remember your changes:
   ```batch
   REM Changed to port 8080 for testing
   set PORT=8080
   ```

3. **Test after changes**:
   - Save file
   - Close current process
   - Run script again
   - Verify changes applied

4. **Keep update backups** if using git updates - see [UPDATE_AND_BACKUP.md](UPDATE_AND_BACKUP.md)
