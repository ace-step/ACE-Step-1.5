# Environment Setup Guide

This guide covers Python environment setup for ACE-Step on Windows, Linux, and macOS.

## Environment Options

### Windows

**Option 1: python_embeded (Portable Package)**
- **Best for**: New users, zero-configuration setup
- **Pros**: Extract and run, no installation required
- **Cons**: Large download size (~7GB)
- **Location**: `python_embeded\python.exe`
- **Download**: https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z

**Option 2: uv (Package Manager)**
- **Best for**: Developers, Git repository users
- **Pros**: Smaller installation, easy updates, excellent tooling
- **Cons**: Requires uv installation
- **Installation**: See [Installing uv](#installing-uv) below

### Linux

**uv (Package Manager)**
- **Only supported option** (no portable package available for Linux)
- **Best for**: All Linux users
- **Requires**: uv package manager
- **Backend**: vllm (default) or pt (PyTorch)
- **Installation**: See [Installing uv](#installing-uv) below

### macOS (Apple Silicon)

**uv with MLX Backend**
- **Only supported option** (no portable package available for macOS)
- **Best for**: All macOS Apple Silicon (M1/M2/M3/M4) users
- **Requires**: uv package manager
- **Backend**: mlx (native Apple Silicon acceleration)
- **Dedicated scripts**: `start_gradio_ui_macos.sh`, `start_api_server_macos.sh`
- **Installation**: See [Installing uv](#installing-uv) below

Note: Intel Macs can use the standard `start_gradio_ui.sh` with the PyTorch (pt) backend, but Apple Silicon Macs should use the macOS-specific scripts for optimal performance.

## Automatic Detection

### Windows (bat scripts)

The `.bat` startup scripts detect the environment in this order:

1. **First**: Check for `python_embeded\python.exe`
   - If found: Use embedded Python directly
   - If not found: Continue to step 2

2. **Second**: Check for `uv` command
   - If found: Use uv
   - If not found: Prompt to install uv

**Example output:**
```
[Environment] Using embedded Python...
```
or
```
[Environment] Embedded Python not found, checking for uv...
[Environment] Using uv package manager...
```

### Linux/macOS (sh scripts)

The `.sh` startup scripts detect the environment in this order:

1. **First**: Check for `uv` in PATH
   - Also checks `~/.local/bin/uv` and `~/.cargo/bin/uv`
   - If found: Use uv
   - If not found: Prompt to install uv

2. **If not found**: Offer automatic installation
   - Calls `install_uv.sh --silent` to install uv
   - Updates PATH and continues

**Example output (Linux):**
```
[Environment] Using uv package manager...
```

**Example output (macOS):**
```
============================================
  ACE-Step 1.5 - macOS Apple Silicon (MLX)
============================================
[Environment] Using uv package manager...
```

## Installing uv

### All Platforms

**Automatic**: When you run a startup script and uv is not found, you will be prompted:

```
uv package manager not found!

Install uv now? (Y/N):
```

Type `Y` and press Enter. The script will automatically install uv using the appropriate method for your platform.

### Windows Methods

**Method 1: PowerShell (Recommended)**
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

**Method 2: winget (Windows 10 1809+, Windows 11)**
```batch
winget install --id=astral-sh.uv -e
```

**Method 3: Run the install script**
```batch
install_uv.bat
```

The `install_uv.bat` script tries PowerShell first, then falls back to winget if PowerShell fails.

### Linux Methods

**Method 1: curl installer (Recommended)**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Method 2: Run the install script**
```bash
chmod +x install_uv.sh
./install_uv.sh
```

The `install_uv.sh` script uses `curl` or `wget` to download and run the official installer.

### macOS Methods

**Method 1: curl installer (Recommended)**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Method 2: Homebrew**
```bash
brew install uv
```

**Method 3: Run the install script**
```bash
chmod +x install_uv.sh
./install_uv.sh
```

The `install_uv.sh` script works on both Linux and macOS, and will suggest `brew install curl` on macOS if neither `curl` nor `wget` is available.

## Installation Locations

### Windows

**PowerShell installation:**
```
%USERPROFILE%\.local\bin\uv.exe
Example: C:\Users\YourName\.local\bin\uv.exe
```

**winget installation:**
```
%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe
Example: C:\Users\YourName\AppData\Local\Microsoft\WinGet\Links\uv.exe
```

### Linux

**Default installation (curl installer):**
```
~/.local/bin/uv
Example: /home/yourname/.local/bin/uv
```

**Alternative location (cargo):**
```
~/.cargo/bin/uv
Example: /home/yourname/.cargo/bin/uv
```

### macOS

**Default installation (curl installer):**
```
~/.local/bin/uv
Example: /Users/yourname/.local/bin/uv
```

**Alternative location (cargo):**
```
~/.cargo/bin/uv
Example: /Users/yourname/.cargo/bin/uv
```

**Homebrew installation:**
```
/opt/homebrew/bin/uv  (Apple Silicon)
/usr/local/bin/uv     (Intel)
```

## First Run

### Windows with python_embeded

```batch
REM Download and extract portable package from:
REM https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z

REM Run the startup script
start_gradio_ui.bat

REM Output:
REM [Environment] Using embedded Python...
REM Starting ACE-Step Gradio UI...
```

### Windows with uv

```batch
REM First time: uv will create a virtual environment and sync dependencies
start_gradio_ui.bat

REM Output:
REM [Environment] Using uv package manager...
REM [Setup] Virtual environment not found. Setting up environment...
REM Running: uv sync
```

### Linux with uv

```bash
# Make scripts executable (first time only)
chmod +x start_gradio_ui.sh install_uv.sh

# First time: uv will create a virtual environment and sync dependencies
./start_gradio_ui.sh

# Output:
# [Environment] Using uv package manager...
# [Setup] Virtual environment not found. Setting up environment...
# Running: uv sync
```

### macOS (Apple Silicon) with uv

```bash
# Make scripts executable (first time only)
chmod +x start_gradio_ui_macos.sh install_uv.sh

# Use the macOS-specific script for MLX backend
./start_gradio_ui_macos.sh

# Output:
# ============================================
#   ACE-Step 1.5 - macOS Apple Silicon (MLX)
# ============================================
# [Environment] Using uv package manager...
# [Setup] Virtual environment not found. Setting up environment...
# Running: uv sync
```

Note: On macOS Apple Silicon, always use `start_gradio_ui_macos.sh` instead of `start_gradio_ui.sh` to enable the MLX backend for native acceleration.

## Troubleshooting

### "uv not found" after installation

**Windows**

Cause: PATH not refreshed after installation.

Solution 1: Restart your terminal (close and reopen Command Prompt or PowerShell).

Solution 2: Use the full path temporarily:
```batch
%USERPROFILE%\.local\bin\uv.exe run acestep
```

**Linux/macOS**

Cause: uv installed but not in PATH.

Solution 1: Restart your terminal or source your profile:
```bash
source ~/.bashrc    # or ~/.zshrc on macOS
```

Solution 2: Add uv to your PATH manually:
```bash
# For ~/.local/bin installation
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# For macOS with zsh (default shell)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Solution 3: Use the full path temporarily:
```bash
~/.local/bin/uv run acestep
```

### Permission issues (Linux/macOS)

**Symptom**: `Permission denied` when running scripts.

**Solution**:
```bash
chmod +x start_gradio_ui.sh
chmod +x start_gradio_ui_macos.sh
chmod +x install_uv.sh
```

**Symptom**: `Permission denied` during uv installation.

**Solution**: The curl installer installs to `~/.local/bin` which should not require root. If you see permission errors:
```bash
# Ensure the directory exists and is writable
mkdir -p ~/.local/bin
```

Do not use `sudo` with the uv installer.

### winget not available (Windows)

**Symptom**:
```
'winget' is not recognized as an internal or external command
```

**Solution**:
- Windows 11: Should be pre-installed. Try updating Windows.
- Windows 10: Install "App Installer" from the Microsoft Store.
- Alternative: Use the PowerShell installation method instead:
  ```powershell
  irm https://astral.sh/uv/install.ps1 | iex
  ```

### Installation fails

**Common causes**:
- Network connection issues
- Firewall blocking downloads
- Antivirus software interference (Windows)
- Missing `curl` or `wget` (Linux/macOS)

**Solutions**:

1. Check your internet connection.
2. Temporarily disable firewall/antivirus (Windows).
3. Try an alternative installation method:
   - **Windows**: Use PowerShell method if winget fails, or vice versa.
   - **Linux**: Install `curl` first (`sudo apt install curl` on Ubuntu/Debian, `sudo yum install curl` on CentOS/RHEL).
   - **macOS**: Use `brew install uv` as an alternative.
4. **Windows only**: Use the portable package instead: https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z

## Switching Environments (Windows Only)

Windows is the only platform with two environment options. Linux and macOS use uv exclusively.

### From python_embeded to uv

```batch
REM 1. Install uv
install_uv.bat

REM 2. Rename or delete python_embeded folder
rename python_embeded python_embeded_backup

REM 3. Run startup script (will use uv)
start_gradio_ui.bat
```

### From uv to python_embeded

```batch
REM 1. Download portable package
REM https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z

REM 2. Extract python_embeded folder to project root

REM 3. Run startup script (will use python_embeded)
start_gradio_ui.bat
```

## Environment Variables (.env)

ACE-Step can be configured using environment variables in a `.env` file.

### Setup

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your preferred settings
```

### Available Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACESTEP_INIT_LLM` | auto | LLM initialization control |
| `ACESTEP_CONFIG_PATH` | acestep-v15-turbo | DiT model path |
| `ACESTEP_LM_MODEL_PATH` | acestep-5Hz-lm-1.7B | LM model path |
| `ACESTEP_DEVICE` | auto | Device: auto, cuda, cpu, xpu |
| `ACESTEP_LM_BACKEND` | vllm | LM backend: vllm, pt, mlx |
| `ACESTEP_DOWNLOAD_SOURCE` | auto | Download source |
| `ACESTEP_API_KEY` | (none) | API authentication key |

### ACESTEP_LM_BACKEND

Controls which backend is used for the Language Model.

| Value | Platform | Description |
|-------|----------|-------------|
| `vllm` | Linux (CUDA) | Default. Fastest backend for NVIDIA GPUs. |
| `pt` | All | PyTorch native backend. Works everywhere but slower. |
| `mlx` | macOS (Apple Silicon) | Native Apple Silicon acceleration via MLX. |

**Platform-specific recommendations:**
- **Windows**: Use `vllm` (default) with NVIDIA GPU, or `pt` as fallback.
- **Linux**: Use `vllm` (default) with NVIDIA GPU, or `pt` as fallback.
- **macOS Apple Silicon**: Use `mlx` for best performance. The `start_gradio_ui_macos.sh` script sets this automatically via `export ACESTEP_LM_BACKEND="mlx"`.

**Example .env for macOS Apple Silicon:**
```bash
ACESTEP_LM_BACKEND=mlx
ACESTEP_CONFIG_PATH=acestep-v15-turbo
ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B
```

### ACESTEP_INIT_LLM - LLM Initialization Control

Controls whether the Language Model (5Hz LM) is initialized at startup.

**Processing Flow:**
```
GPU Detection (full) --> ACESTEP_INIT_LLM Override --> Model Loading
```

- GPU optimizations (offload, quantization, batch limits) are **always applied**
- `ACESTEP_INIT_LLM` only overrides the "should we load LLM" decision
- Model validation shows warnings but does not block when forcing

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
| Thinking mode | LLM generates audio codes | No |
| CoT caption | LLM enhances captions | No (auto-disabled) |
| CoT language | LLM detects vocal language | No (auto-disabled) |
| Sample mode | Generate from description | No |
| Format mode | LLM-enhanced input | No |
| Basic generation | DiT-based synthesis | Yes |
| Cover/Repaint | Audio editing tasks | Yes |

Note: When using the API server, CoT features (`use_cot_caption`, `use_cot_language`) are automatically disabled when LLM is unavailable, allowing basic generation to proceed.

## Environment Comparison

| Feature | python_embeded (Windows) | uv (Windows) | uv (Linux) | uv (macOS) |
|---------|--------------------------|---------------|-------------|-------------|
| Setup Difficulty | Zero config | Need install | Need install | Need install |
| Startup Speed | Fast | Fast | Fast | Fast |
| Update Ease | Re-download | uv command | uv command | uv command |
| Environment Isolation | Complete | Virtual env | Virtual env | Virtual env |
| Development | Basic | Excellent | Excellent | Excellent |
| Beginner Friendly | Best | Good | Good | Good |
| GPU Backend | CUDA | CUDA | CUDA (vllm) | MLX (Apple Silicon) |
| Install Script | N/A | install_uv.bat | install_uv.sh | install_uv.sh |
| Launch Script | start_gradio_ui.bat | start_gradio_ui.bat | start_gradio_ui.sh | start_gradio_ui_macos.sh |

## Recommendations

### Windows

**Use python_embeded if:**
- First time using ACE-Step
- Want zero configuration
- Do not need frequent updates
- Prefer a self-contained package

**Use uv if:**
- Developer or experienced with Python
- Need to modify dependencies
- Using the Git repository
- Want smaller installation size
- Need frequent code updates

### Linux

**Use uv (only option):**
- Install uv via the curl installer or `install_uv.sh`
- Use `start_gradio_ui.sh` to launch
- NVIDIA GPU with CUDA is recommended for vllm backend
- CPU-only is possible with `ACESTEP_DEVICE=cpu` and `ACESTEP_LM_BACKEND=pt`

### macOS (Apple Silicon)

**Use uv with MLX backend (recommended):**
- Install uv via curl installer, Homebrew, or `install_uv.sh`
- Use `start_gradio_ui_macos.sh` to launch (sets MLX backend automatically)
- The 0.6B LM model (`acestep-5Hz-lm-0.6B`) is recommended for devices with limited unified memory
- Set `ACESTEP_LM_BACKEND=mlx` in `.env` if launching manually
- Intel Macs should use `start_gradio_ui.sh` with `ACESTEP_LM_BACKEND=pt` instead
