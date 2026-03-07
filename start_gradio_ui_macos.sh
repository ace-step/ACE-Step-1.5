#!/usr/bin/env bash
# ACE-Step Gradio Web UI Launcher - macOS (Apple Silicon / MLX)
# This script launches the Gradio web interface using the MLX backend
# for native Apple Silicon acceleration.
#
# Requirements: macOS with Apple Silicon (M1/M2/M3/M4)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ==================== Load .env Configuration ====================
# Load settings from .env file if it exists
_load_env_file() {
    local env_file="${SCRIPT_DIR}/.env"
    if [[ ! -f "$env_file" ]]; then
        return 0
    fi
    
    echo "[Config] Loading configuration from .env file..."
    
    # Read .env file and export variables
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        # Skip empty lines and comments
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        
        # Trim whitespace from key and value
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        
        # Map .env variable names to script variables
        case "$key" in
            ACESTEP_CONFIG_PATH)
                [[ -n "$value" ]] && CONFIG_PATH="--config_path $value"
                ;;
            ACESTEP_LM_MODEL_PATH)
                [[ -n "$value" ]] && LM_MODEL_PATH="--lm_model_path $value"
                ;;
            ACESTEP_INIT_LLM)
                if [[ -n "$value" && "$value" != "auto" ]]; then
                    INIT_LLM="--init_llm $value"
                fi
                ;;
            ACESTEP_DOWNLOAD_SOURCE)
                if [[ -n "$value" && "$value" != "auto" ]]; then
                    DOWNLOAD_SOURCE="--download-source $value"
                fi
                ;;
            ACESTEP_API_KEY)
                [[ -n "$value" ]] && API_KEY="--api-key $value"
                ;;
            PORT)
                [[ -n "$value" ]] && PORT="$value"
                ;;
            SERVER_NAME)
                [[ -n "$value" ]] && SERVER_NAME="$value"
                ;;
            LANGUAGE)
                [[ -n "$value" ]] && LANGUAGE="$value"
                ;;
            ACESTEP_BATCH_SIZE)
                [[ -n "$value" ]] && BATCH_SIZE="--batch_size $value"
                ;;
        esac
    done < "$env_file"
    
    echo "[Config] Configuration loaded from .env"
}

_load_env_file

# ==================== MLX Configuration ====================
# Force MLX backend for native Apple Silicon acceleration
export ACESTEP_LM_BACKEND="mlx"

# Disable tokenizer parallelism warning
export TOKENIZERS_PARALLELISM="false"

# ==================== Server Configuration ====================
# Default values (used if not set in .env file)
# You can override these by uncommenting and modifying the lines below
# or by creating a .env file (recommended to survive updates)

: "${PORT:=7860}"
: "${SERVER_NAME:=127.0.0.1}"
# SERVER_NAME="0.0.0.0"
SHARE="${SHARE:-}"
# SHARE="--share"

# UI language: en, zh, he, ja
: "${LANGUAGE:=en}"

# Batch size: default batch size for generation (1 to GPU-dependent max)
# When not specified, defaults to min(2, GPU_max)
BATCH_SIZE="${BATCH_SIZE:-}"
# BATCH_SIZE="--batch_size 4"

# ==================== Model Configuration ====================
: "${CONFIG_PATH:=--config_path acestep-v15-turbo}"
: "${LM_MODEL_PATH:=--lm_model_path acestep-5Hz-lm-0.6B}"

# CPU offload (recommended for models larger than 0.6B on devices with limited memory)
# OFFLOAD_TO_CPU="--offload_to_cpu true"
OFFLOAD_TO_CPU="${OFFLOAD_TO_CPU:-}"

# LLM initialization: auto (default), true, false
INIT_LLM="${INIT_LLM:-}"
# INIT_LLM="--init_llm auto"
# INIT_LLM="--init_llm true"
# INIT_LLM="--init_llm false"

# Download source: auto, huggingface, modelscope
DOWNLOAD_SOURCE="${DOWNLOAD_SOURCE:-}"
# DOWNLOAD_SOURCE="--download-source huggingface"

# Auto-initialize models on startup
: "${INIT_SERVICE:=--init_service true}"

# LM backend: mlx for Apple Silicon native acceleration
BACKEND="--backend mlx"

# API settings
ENABLE_API="${ENABLE_API:-}"
# ENABLE_API="--enable-api"
API_KEY="${API_KEY:-}"
# API_KEY="--api-key sk-your-secret-key"

# Authentication
AUTH_USERNAME="${AUTH_USERNAME:-}"
# AUTH_USERNAME="--auth-username admin"
AUTH_PASSWORD="${AUTH_PASSWORD:-}"
# AUTH_PASSWORD="--auth-password password"

# Update check on startup (set to "false" to disable)
: "${CHECK_UPDATE:=true}"
# CHECK_UPDATE="false"

# ==================== Launch ====================

# Verify Apple Silicon
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This script is for macOS only."
    echo "For Linux, use start_gradio_ui.sh instead."
    exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
    echo "WARNING: This script is optimized for Apple Silicon (arm64)."
    echo "Detected architecture: $ARCH"
    echo "MLX backend requires Apple Silicon. Falling back to PyTorch backend."
    echo
    BACKEND="--backend pt"
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
    if [[ "$(echo "$update_choice" | tr '[:lower:]' '[:upper:]')" == "Y" ]]; then
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
echo "  ACE-Step 1.5 - macOS Apple Silicon (MLX)"
echo "============================================"
echo
echo "Server will be available at: http://${SERVER_NAME}:${PORT}"
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
        SCRIPT_PATH="$SCRIPT_DIR/acestep/acestep_v15_pipeline.py"

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

        echo "Starting ACE-Step Gradio UI..."
        echo

        # Build command with optional parameters
        CMD="--port $PORT --server-name $SERVER_NAME --language $LANGUAGE"
        [[ -n "$SHARE" ]] && CMD="$CMD $SHARE"
        [[ -n "$CONFIG_PATH" ]] && CMD="$CMD $CONFIG_PATH"
        [[ -n "$LM_MODEL_PATH" ]] && CMD="$CMD $LM_MODEL_PATH"
        [[ -n "$OFFLOAD_TO_CPU" ]] && CMD="$CMD $OFFLOAD_TO_CPU"
        [[ -n "$INIT_LLM" ]] && CMD="$CMD $INIT_LLM"
        [[ -n "$DOWNLOAD_SOURCE" ]] && CMD="$CMD $DOWNLOAD_SOURCE"
        [[ -n "$INIT_SERVICE" ]] && CMD="$CMD $INIT_SERVICE"
        [[ -n "${BATCH_SIZE:-}" ]] && CMD="$CMD $BATCH_SIZE"
        [[ -n "$BACKEND" ]] && CMD="$CMD $BACKEND"
        [[ -n "$ENABLE_API" ]] && CMD="$CMD $ENABLE_API"
        [[ -n "$API_KEY" ]] && CMD="$CMD $API_KEY"
        [[ -n "$AUTH_USERNAME" ]] && CMD="$CMD $AUTH_USERNAME"
        [[ -n "$AUTH_PASSWORD" ]] && CMD="$CMD $AUTH_PASSWORD"

        cd "$SCRIPT_DIR" && exec "$PYTHON_EXE" "$SCRIPT_PATH" $CMD
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

    if [[ "$(echo "$INSTALL_UV" | tr '[:lower:]' '[:upper:]')" == "Y" ]]; then
        echo
        bash "$SCRIPT_DIR/install_uv.sh" --silent
        INSTALL_RESULT=$?

        if [[ $INSTALL_RESULT -eq 0 ]]; then
            export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
            if ! command -v uv &>/dev/null; then
                echo "uv installed but not in PATH. Please restart your terminal."
                exit 1
            fi
            echo "uv installed successfully!"
            echo
        else
            echo "Installation failed. Please install uv manually:"
            echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            echo "  or: brew install uv"
            exit 1
        fi
    else
        echo "Installation cancelled."
        echo "Please install uv:"
        echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "  or: brew install uv"
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

echo "Starting ACE-Step Gradio UI (MLX backend)..."
echo

# Build command with optional parameters
ACESTEP_ARGS="acestep --port $PORT --server-name $SERVER_NAME --language $LANGUAGE"
[[ -n "$SHARE" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $SHARE"
[[ -n "$CONFIG_PATH" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $CONFIG_PATH"
[[ -n "$LM_MODEL_PATH" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $LM_MODEL_PATH"
[[ -n "$OFFLOAD_TO_CPU" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $OFFLOAD_TO_CPU"
[[ -n "$INIT_LLM" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $INIT_LLM"
[[ -n "$DOWNLOAD_SOURCE" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $DOWNLOAD_SOURCE"
[[ -n "$INIT_SERVICE" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $INIT_SERVICE"
[[ -n "$BATCH_SIZE" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $BATCH_SIZE"
[[ -n "$BACKEND" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $BACKEND"
[[ -n "$ENABLE_API" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $ENABLE_API"
[[ -n "$API_KEY" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $API_KEY"
[[ -n "$AUTH_USERNAME" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $AUTH_USERNAME"
[[ -n "$AUTH_PASSWORD" ]] && ACESTEP_ARGS="$ACESTEP_ARGS $AUTH_PASSWORD"

cd "$SCRIPT_DIR" && uv run $ACESTEP_ARGS || {
    echo
    echo "[Retry] Online dependency resolution failed, retrying in offline mode..."
    echo
    uv run --offline $ACESTEP_ARGS || {
        echo
        echo "========================================"
        echo "[Error] Failed to start ACE-Step"
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
