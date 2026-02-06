# Environment Setup Guide

This guide covers Python environment setup for ACE-Step.

## Environment Options

ACE-Step supports two Python environments:

### Option 1: python_embeded (Portable Package)
- **Best for**: New users, Windows portable package
- **Pros**: Zero configuration, extract and run
- **Cons**: Large size (7GB)
- **Location**: `python_embeded\python.exe`
- **Download**: https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z

### Option 2: uv (Package Manager)
- **Best for**: Developers, Git repository users
- **Cons**: Requires installation
- **Installation**: See below

## Automatic Detection

The startup scripts automatically detect your environment:

1. **First**: Check for `python_embeded\python.exe`
   - If found → Use embedded Python
   - If not found → Continue to step 2

2. **Second**: Check for `uv` command
   - If found → Use uv
   - If not found → Prompt to install uv

**Example output:**
```
[Environment] Using embedded Python...
```
or
```
[Environment] Embedded Python not found, using uv...
```

## Installing uv

### Method 1: Automatic Installation (Recommended)

Run the startup script, and if uv is not found, you'll see:

```
uv package manager not found!
Would you like to install uv now? (Y/N):
```

Type `Y` and press Enter. The script will automatically install uv.

### Method 2: Manual Installation

**Option A: Using winget (Windows 10 1809+, Windows 11)**
```batch
winget install --id=astral-sh.uv -e
```

**Option B: Using PowerShell (All Windows versions)**
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

**Option C: Run the install script**
```batch
install_uv.bat
```

## Installation Locations

**winget installation:**
```
%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe
Example: C:\Users\YourName\AppData\Local\Microsoft\WinGet\Links\uv.exe
```

**PowerShell installation:**
```
%USERPROFILE%\.local\bin\uv.exe
Example: C:\Users\YourName\.local\bin\uv.exe
```

## First Run

### With python_embeded:
```batch
# Download portable package from:
# https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z

# Extract and run the startup script
start_gradio_ui.bat
```

### With uv:
```batch
# First time: uv will sync dependencies
start_gradio_ui.bat

# Output:
# [Environment] Using uv package manager...
# Syncing dependencies...
```

## Troubleshooting

### "uv not found" after installation

**Cause**: PATH not refreshed

**Solution 1**: Restart your terminal
```batch
# Close current terminal and open a new one
start_gradio_ui.bat
```

**Solution 2**: Use full path temporarily
```batch
%USERPROFILE%\.local\bin\uv.exe run acestep
```

### winget not available

**Symptom**:
```
'winget' is not recognized as an internal or external command
```

**Solution**:
- Windows 11: Should be pre-installed, update Windows
- Windows 10: Install "App Installer" from Microsoft Store
- Alternative: Use PowerShell installation method

### Installation fails

**Common causes**:
- Network connection issues
- Firewall blocking downloads
- Antivirus software interference

**Solutions**:
1. Check internet connection
2. Temporarily disable firewall/antivirus
3. Try alternative installation method
4. Use portable package instead: https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z

## Switching Environments

### From python_embeded to uv
```batch
# 1. Install uv
install_uv.bat

# 2. Rename or delete python_embeded folder
rename python_embeded python_embeded_backup

# 3. Run startup script (will use uv)
start_gradio_ui.bat
```

### From uv to python_embeded
```batch
# 1. Download portable package
# https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z

# 2. Extract python_embeded folder to project root

# 3. Run startup script (will use python_embeded)
start_gradio_ui.bat
```

## Environment Comparison

| Feature | python_embeded | uv |
|---------|----------------|-----|
| Setup Difficulty | ⭐ Zero config | ⭐⭐ Need install |
| Startup Speed | ⭐⭐⭐⭐ Fast | ⭐⭐⭐ Fast |
| Update Ease | ⭐⭐ Re-download | ⭐⭐⭐⭐ Command |
| Environment Isolation | ⭐⭐⭐⭐ Complete | ⭐⭐⭐⭐ Virtual env |
| Development | ⭐⭐ Basic | ⭐⭐⭐⭐⭐ Excellent |
| Beginner Friendly | ⭐⭐⭐⭐⭐ Best | ⭐⭐⭐ Good |

## Recommendations

**Use python_embeded if:**
- First time using ACE-Step
- Want zero configuration
- Using Windows portable package
- Don't need frequent updates

**Use uv if:**
- Developer or experienced with Python
- Need to modify dependencies
- Using Git repository
- Want smaller installation size
- Need frequent code updates

## Environment Variables (.env)

For uv or Python users, ACE-Step can be configured using environment variables in a `.env` file.

### Setup

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your preferred settings
```

### Available Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACESTEP_INIT_LLM` | (auto) | LLM initialization control |
| `ACESTEP_CONFIG_PATH` | acestep-v15-turbo | DiT model path |
| `ACESTEP_LM_MODEL_PATH` | (auto) | LM model path |
| `ACESTEP_DEVICE` | auto | Device: auto, cuda, cpu, xpu |
| `ACESTEP_LM_BACKEND` | vllm | LM backend: vllm, pt |
| `ACESTEP_DOWNLOAD_SOURCE` | auto | Download source |
| `ACESTEP_API_KEY` | (none) | API authentication key |

### ACESTEP_INIT_LLM - LLM Initialization Control

Controls whether the Language Model (5Hz LM) is initialized at startup.

**Processing Flow:**
```
GPU Detection (full) → ACESTEP_INIT_LLM Override → Model Loading
```

- GPU optimizations (offload, quantization, batch limits) are **always applied**
- `ACESTEP_INIT_LLM` only overrides the "should we load LLM" decision
- Model validation shows warnings but doesn't block when forcing

| Value | Behavior |
|-------|----------|
| `auto` (or empty) | Use GPU auto-detection result (recommended) |
| `true` / `1` / `yes` | Force enable LLM after GPU detection (may cause OOM) |
| `false` / `0` / `no` | Force disable for pure DiT mode |

**Example configurations:**

```bash
# Auto mode (recommended) - let GPU detection decide
ACESTEP_INIT_LLM=auto

# Auto mode - leave empty (same as above)
ACESTEP_INIT_LLM=

# Force enable on low VRAM GPU (GPU optimizations still applied)
ACESTEP_INIT_LLM=true
ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B  # Use smallest model

# Force disable LLM for faster generation
ACESTEP_INIT_LLM=false
```

### Features Affected by LLM

When LLM is disabled (`ACESTEP_INIT_LLM=false`), these features are unavailable:

| Feature | Description | Available without LLM |
|---------|-------------|----------------------|
| Thinking mode | LLM generates audio codes | ❌ |
| CoT caption | LLM enhances captions | ❌ (auto-disabled) |
| CoT language | LLM detects vocal language | ❌ (auto-disabled) |
| Sample mode | Generate from description | ❌ |
| Format mode | LLM-enhanced input | ❌ |
| Basic generation | DiT-based synthesis | ✅ |
| Cover/Repaint | Audio editing tasks | ✅ |

Note: When using the API server, CoT features (`use_cot_caption`, `use_cot_language`) are automatically disabled when LLM is unavailable, allowing basic generation to proceed.

