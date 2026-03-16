#!/usr/bin/env bash
# ACE-Step REST API Server Launcher - Linux (CUDA)
# This script launches the REST API server for ACE-Step

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ==================== Configuration ====================
# Uncomment and modify the parameters below as needed

# Server settings
HOST="127.0.0.1"
# HOST="0.0.0.0"
PORT=8001

# API key for authentication (optional)
API_KEY=""
# API_KEY="--api-key sk-your-secret-key"

# Download source settings
# Preferred download source: auto (default), huggingface, or modelscope
DOWNLOAD_SOURCE=""
# DOWNLOAD_SOURCE="--download-source modelscope"
# DOWNLOAD_SOURCE="--download-source huggingface"

# LLM (Language Model) initialization settings
# By default, LLM is auto-enabled/disabled based on GPU VRAM:
#   - <=6GB VRAM: LLM disabled (DiT-only mode)
#   - >6GB VRAM: LLM enabled
# Values: auto (default), true (force enable), false (force disable)
export ACESTEP_INIT_LLM=auto
# export ACESTEP_INIT_LLM=true
# export ACESTEP_INIT_LLM=false

# LM model path (optional, only used when LLM is enabled)
# Available models: acestep-5Hz-lm-0.6B, acestep-5Hz-lm-1.7B, acestep-5Hz-lm-4B
LM_MODEL_PATH=""
# LM_MODEL_PATH="--lm-model-path acestep-5Hz-lm-0.6B"

# Update check on startup (set to "false" to disable)
CHECK_UPDATE="true"
# CHECK_UPDATE="false"

# Skip model loading at startup (models will be lazy-loaded on first request)
# Set to "true" to start server quickly without loading models
# export ACESTEP_NO_INIT=false
# export ACESTEP_NO_INIT=true

# ==================== Launch ====================

# ==================== Startup Update Check ====================
_startup_update_check() {
    [[ "$CHECK_UPDATE" != "true" ]] && return 0
    command -v git &>/dev/null || return 0
    cd "$SCRIPT_DIR" || return 0
    git rev-parse --git-dir &>/dev/null 2>&1 || return 0

    local branch commit remote_commit
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")"
    commit="$(git rev-parse --short HEAD 2>/dev/null || echo "")"
    [[ -z "$commit" ]] && return 0

    echo "[Update] Checking for updates..."

    # Fetch with timeout (10s)
    local fetch_ok=0
    if command -v timeout &>/dev/null; then
        timeout 10 git fetch origin --quiet 2>/dev/null && fetch_ok=1
    elif command -v gtimeout &>/dev/null; then
        gtimeout 10 git fetch origin --quiet 2>/dev/null && fetch_ok=1
    else
        git fetch origin --quiet 2>/dev/null && fetch_ok=1
    fi

    if [[ $fetch_ok -eq 0 ]]; then
        echo "[Update] Network unreachable, skipping."
        echo
        return 0
    fi

    remote_commit="$(git rev-parse --short "origin/$branch" 2>/dev/null || echo "")"

    if [[ -z "$remote_commit" || "$commit" == "$remote_commit" ]]; then
        echo "[Update] Already up to date ($commit)."
        echo
        return 0
    fi

    echo
    echo "========================================"
    echo "  Update available!"
    echo "========================================"
    echo "  Current: $commit  ->  Latest: $remote_commit"
    echo
    echo "  Recent changes:"
    git --no-pager log --oneline "HEAD..origin/$branch" 2>/dev/null | head -10
    echo

    read -rp "Update now before starting? (Y/N): " update_choice
    if [[ "${update_choice^^}" == "Y" ]]; then
        if [[ -f "$SCRIPT_DIR/check_update.sh" ]]; then
            bash "$SCRIPT_DIR/check_update.sh"
        else
            echo "Pulling latest changes..."
            git pull --ff-only origin "$branch" 2>/dev/null || {
                echo "[Update] Update failed. Please run: git pull"
            }
        fi
    else
        echo "[Update] Skipped. Run ./check_update.sh to update later."
    fi
    echo
}
_startup_update_check

echo "Starting ACE-Step REST API Server..."
echo "API will be available at: http://${HOST}:${PORT}"
echo "API Documentation: http://${HOST}:${PORT}/docs"
echo

# Check if uv is installed
if ! command -v uv &>/dev/null; then
    if [[ -x "$HOME/.local/bin/uv" ]]; then
        export PATH="$HOME/.local/bin:$PATH"
    elif [[ -x "$HOME/.cargo/bin/uv" ]]; then
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
fi

if ! command -v uv &>/dev/null; then
    echo
    echo "========================================"
    echo "uv package manager not found!"
    echo "========================================"
    echo
    echo "ACE-Step requires the uv package manager."
    echo
    read -rp "Install uv now? (Y/N): " INSTALL_UV

    if [[ "${INSTALL_UV^^}" == "Y" ]]; then
        echo
        bash "$SCRIPT_DIR/install_uv.sh" --silent
        INSTALL_RESULT=$?

        if [[ $INSTALL_RESULT -eq 0 ]]; then
            echo
            echo "uv installed successfully!"
            export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

            if ! command -v uv &>/dev/null; then
                echo "uv installed but not in PATH. Please restart your terminal."
                exit 1
            fi
        else
            echo "Installation failed. Please install uv manually:"
            echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            exit 1
        fi
    else
        echo "Installation cancelled."
        echo "Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
fi

echo "[Environment] Using uv package manager..."
echo

# Ensure PyTorch build supports legacy NVIDIA GPUs (e.g., Pascal/Quadro P1000).
# Newer CUDA wheels can omit sm_61, which causes runtime model-init failures.
_ensure_legacy_nvidia_torch_compat() {
    [[ "${ACESTEP_SKIP_LEGACY_TORCH_FIX:-}" == "true" ]] && return 0
    [[ ! -x "$SCRIPT_DIR/.venv/bin/python" ]] && return 0

    local compat_status
    if (cd "$SCRIPT_DIR" && .venv/bin/python -c \
        "import os, sys; sys.path.insert(0, os.getcwd()); from acestep.launcher_compat import legacy_torch_fix_probe_exit_code; raise SystemExit(legacy_torch_fix_probe_exit_code())"); then
        return 0
    else
        compat_status=$?
    fi

    if [[ "$compat_status" -eq 0 ]]; then
        return 0
    fi
    if [[ "$compat_status" -ne 42 ]]; then
        echo "[Compatibility] Error: legacy NVIDIA compatibility probe failed with exit code $compat_status."
        return "$compat_status"
    fi

    echo "[Compatibility] Applying legacy NVIDIA torch build (CUDA 12.1, supports sm_61)..."
    if (cd "$SCRIPT_DIR" && uv pip install --python .venv/bin/python --force-reinstall \
        --index-url https://download.pytorch.org/whl/cu121 \
        torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121); then
        echo "[Compatibility] Legacy torch install complete."
        # Keep a legacy-compatible torchao so INT8 quantization remains available
        # on low-VRAM Pascal/Quadro GPUs.
        if (cd "$SCRIPT_DIR" && uv pip install --python .venv/bin/python --force-reinstall torchao==0.11.0 >/dev/null 2>&1); then
            echo "[Compatibility] Installed torchao==0.11.0 (legacy-compatible)."
        else
            echo "[Compatibility] Warning: failed to install torchao==0.11.0. Quantization may be unavailable."
        fi
    else
        echo "[Compatibility] Warning: failed to install legacy torch automatically."
        echo "[Compatibility] Run manually:"
        echo "  uv pip install --python .venv/bin/python --force-reinstall --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121"
        return 1
    fi
}

# Check if virtual environment exists
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    echo "[Setup] Virtual environment not found. Setting up environment..."
    echo "This will take a few minutes on first run."
    echo
    echo "Running: uv sync"
    echo

    if ! (cd "$SCRIPT_DIR" && uv sync); then
        echo
        echo "[Retry] Online sync failed, retrying in offline mode..."
        echo
        if ! (cd "$SCRIPT_DIR" && uv sync --offline); then
            echo
            echo "========================================"
            echo "[Error] Failed to setup environment"
            echo "========================================"
            echo
            echo "Both online and offline modes failed."
            echo "Please check:"
            echo "  1. Your internet connection (required for first-time setup)"
            echo "  2. Ensure you have enough disk space"
            echo "  3. Try running: uv sync manually"
            exit 1
        fi
    fi

    echo
    echo "========================================"
    echo "Environment setup completed!"
    echo "========================================"
    echo
fi

_ensure_legacy_nvidia_torch_compat

echo "Starting ACE-Step API Server..."
echo

# Build command with optional parameters
ACESTEP_ARGS="acestep-api --host $HOST --port $PORT"
[[ -n "$API_KEY" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $API_KEY"
[[ -n "$DOWNLOAD_SOURCE" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $DOWNLOAD_SOURCE"
[[ -n "$LM_MODEL_PATH" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $LM_MODEL_PATH"

cd "$SCRIPT_DIR" && uv run --no-sync $ACESTEP_ARGS || {
    echo
    echo "[Retry] Online dependency resolution failed, retrying in offline mode..."
    echo
    uv run --offline --no-sync $ACESTEP_ARGS || {
        echo
        echo "========================================"
        echo "[Error] Failed to start ACE-Step API Server"
        echo "========================================"
        echo
        echo "Both online and offline modes failed."
        echo "Please check:"
        echo "  1. Your internet connection (for first-time setup)"
        echo "  2. If dependencies were previously installed (offline mode requires a prior successful install)"
        echo "  3. Try running: uv sync --offline"
        exit 1
    }
}
