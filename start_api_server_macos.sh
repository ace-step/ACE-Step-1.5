#!/usr/bin/env bash
# ACE-Step REST API Server Launcher - macOS (Apple Silicon / MLX)
# This script launches the REST API server using the MLX backend
# for native Apple Silicon acceleration.
#
# Requirements: macOS with Apple Silicon (M1/M2/M3/M4)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ==================== MLX Configuration ====================
# Force MLX backend for native Apple Silicon acceleration
export ACESTEP_LM_BACKEND="mlx"

# Disable tokenizer parallelism warning
export TOKENIZERS_PARALLELISM="false"

# ==================== Server Configuration ====================
HOST="127.0.0.1"
# HOST="0.0.0.0"
PORT=8001

# API key for authentication (optional, value only)
API_KEY=""
# API_KEY="sk-your-secret-key"

# Download source settings (value only: "huggingface" or "modelscope")
DOWNLOAD_SOURCE=""
# DOWNLOAD_SOURCE="huggingface"
# DOWNLOAD_SOURCE="modelscope"

# LLM initialization settings
# Values: auto (default), true (force enable), false (force disable)
export ACESTEP_INIT_LLM=auto
# export ACESTEP_INIT_LLM=true
# export ACESTEP_INIT_LLM=false

# LM model path (value only)
LM_MODEL_PATH=""
# LM_MODEL_PATH="acestep-5Hz-lm-0.6B"

# Update check on startup (set to "false" to disable)
CHECK_UPDATE="true"
# CHECK_UPDATE="false"

# Skip model loading at startup (models will be lazy-loaded on first request)
# Set to "true" to start server quickly without loading models
# export ACESTEP_NO_INIT=false
# export ACESTEP_NO_INIT=true

# ==================== Launch ====================

# Verify macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This script is for macOS only."
    echo "For Linux, use start_api_server.sh instead."
    exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
    echo "WARNING: MLX backend requires Apple Silicon (arm64)."
    echo "Detected architecture: $ARCH"
    echo "Falling back to PyTorch backend."
    unset ACESTEP_LM_BACKEND
fi

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

    # Fetch with timeout (10s) - macOS uses gtimeout from coreutils
    local fetch_ok=0
    if command -v gtimeout &>/dev/null; then
        gtimeout 10 git fetch origin --quiet 2>/dev/null && fetch_ok=1
    elif command -v timeout &>/dev/null; then
        timeout 10 git fetch origin --quiet 2>/dev/null && fetch_ok=1
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
    git --no-pager log --oneline -10 "HEAD..origin/$branch" 2>/dev/null
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

echo "============================================"
echo "  ACE-Step 1.5 API - macOS Apple Silicon (MLX)"
echo "============================================"
echo
echo "API will be available at: http://${HOST}:${PORT}"
echo "API Documentation: http://${HOST}:${PORT}/docs"
echo

# ==================== Auto-detect Python environment ====================
# Priority: python_embedded (portable package) > uv
if [[ -f "$SCRIPT_DIR/python_embedded/bin/python3.11" ]]; then
    echo "[Environment] Found embedded Python, verifying..."

    # Proactively fix permissions and Gatekeeper BEFORE any execution attempt.
    # On macOS Sequoia, running a quarantined binary triggers a blocking popup,
    # so we must strip attributes and re-sign first.
    chmod +x "$SCRIPT_DIR/python_embedded/bin/"* 2>/dev/null || true
    echo "[Setup] Removing quarantine attributes..."
    xattr -cr "$SCRIPT_DIR/python_embedded" 2>/dev/null || true
    echo "[Setup] Re-signing binaries (ad-hoc)..."
    find "$SCRIPT_DIR/python_embedded" -type f \( -name "*.dylib" -o -name "*.so" -o -perm +111 \) \
        -exec codesign --force --sign - {} \; 2>/dev/null || true

    if "$SCRIPT_DIR/python_embedded/bin/python3.11" -c "pass" 2>/dev/null; then
        echo "[Environment] Using embedded Python."
        PYTHON_EXE="$SCRIPT_DIR/python_embedded/bin/python3.11"
        SCRIPT_PATH="$SCRIPT_DIR/acestep/api_server.py"

        # On Apple Silicon, verify MLX packages work with this macOS version.
        # python_embedded may ship wheels built for a different macOS; pip
        # reinstall fetches the correct platform wheel automatically.
        if [[ "$ARCH" == "arm64" ]]; then
            _need_mlx_fix=0
            if ! "$PYTHON_EXE" -c "import mlx.core" 2>/dev/null; then
                echo "[Setup] MLX incompatible with this macOS — will reinstall."
                _need_mlx_fix=1
            elif ! "$PYTHON_EXE" -c "from mlx_lm.utils import load" 2>/dev/null; then
                echo "[Setup] mlx-lm outdated — will upgrade."
                _need_mlx_fix=1
            fi
            if [[ $_need_mlx_fix -eq 1 ]]; then
                echo "[Setup] Fixing MLX packages (this only runs once)..."
                "$PYTHON_EXE" -m pip install --upgrade mlx mlx-lm 'transformers>=4.51.0,<4.58.0' 'vector-quantize-pytorch>=1.27.15,<1.28.0' 2>&1 | tail -1
            fi
        fi

        echo "Starting ACE-Step API Server..."
        echo

        # Build command with optional parameters
        CMD=("$PYTHON_EXE" "$SCRIPT_PATH" --host "$HOST" --port "$PORT")
        [[ -n "$API_KEY" ]] && CMD+=(--api-key "$API_KEY")
        [[ -n "$DOWNLOAD_SOURCE" ]] && CMD+=(--download-source "$DOWNLOAD_SOURCE")
        [[ -n "$LM_MODEL_PATH" ]] && CMD+=(--lm-model-path "$LM_MODEL_PATH")

        cd "$SCRIPT_DIR" && exec "${CMD[@]}"
    else
        echo "[Setup] WARNING: Embedded Python cannot run on this machine."
        echo "[Setup] This may be a CPU architecture mismatch (e.g., arm64 binary on x86_64)."
        echo "[Setup] Falling back to uv..."
        echo
    fi
fi

# ==================== Fallback: uv package manager ====================
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
            export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
            if ! command -v uv &>/dev/null; then
                echo "uv installed but not in PATH. Please restart your terminal."
                exit 1
            fi
        else
            echo "Installation failed. Please install uv manually:"
            echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            echo "  or: brew install uv"
            exit 1
        fi
    else
        echo "Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
fi

echo "[Environment] Using uv package manager..."
echo

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

echo "Starting ACE-Step API Server (MLX backend)..."
echo

# Build command with optional parameters
ACESTEP_ARGS=(acestep-api --host "$HOST" --port "$PORT")
[[ -n "$API_KEY" ]] && ACESTEP_ARGS+=(--api-key "$API_KEY")
[[ -n "$DOWNLOAD_SOURCE" ]] && ACESTEP_ARGS+=(--download-source "$DOWNLOAD_SOURCE")
[[ -n "$LM_MODEL_PATH" ]] && ACESTEP_ARGS+=(--lm-model-path "$LM_MODEL_PATH")

cd "$SCRIPT_DIR" && uv run "${ACESTEP_ARGS[@]}" || {
    echo
    echo "[Retry] Online dependency resolution failed, retrying in offline mode..."
    echo
    uv run --offline "${ACESTEP_ARGS[@]}" || {
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
