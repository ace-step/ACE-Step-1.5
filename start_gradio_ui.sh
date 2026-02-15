#!/usr/bin/env bash
# ACE-Step Gradio Web UI Launcher - Linux (CUDA)
# This script launches the Gradio web interface for ACE-Step

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

# ==================== Configuration ====================
# Default values (used if not set in .env file)
# You can override these by uncommenting and modifying the lines below
# or by creating a .env file (recommended to survive updates)

# Server settings
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

# Model settings
: "${CONFIG_PATH:=--config_path acestep-v15-turbo}"
: "${LM_MODEL_PATH:=--lm_model_path acestep-5Hz-lm-0.6B}"
# OFFLOAD_TO_CPU="--offload_to_cpu true"
OFFLOAD_TO_CPU="${OFFLOAD_TO_CPU:-}"

# LLM (Language Model) initialization settings
# By default, LLM is auto-enabled/disabled based on GPU VRAM:
#   - <=6GB VRAM: LLM disabled (DiT-only mode)
#   - >6GB VRAM: LLM enabled
# Values: auto (default), true (force enable), false (force disable)
INIT_LLM="${INIT_LLM:-}"
# INIT_LLM="--init_llm auto"
# INIT_LLM="--init_llm true"
# INIT_LLM="--init_llm false"

# Download source settings
# Preferred download source: auto (default), huggingface, or modelscope
DOWNLOAD_SOURCE="${DOWNLOAD_SOURCE:-}"
# DOWNLOAD_SOURCE="--download-source modelscope"
# DOWNLOAD_SOURCE="--download-source huggingface"

# Update check on startup (set to "false" to disable)
: "${CHECK_UPDATE:=true}"
# CHECK_UPDATE="false"

# Auto-initialize models on startup
: "${INIT_SERVICE:=--init_service true}"

# API settings (enable REST API alongside Gradio)
ENABLE_API="${ENABLE_API:-}"
# ENABLE_API="--enable-api"
API_KEY="${API_KEY:-}"
# API_KEY="--api-key sk-your-secret-key"

# Authentication settings
AUTH_USERNAME="${AUTH_USERNAME:-}"
# AUTH_USERNAME="--auth-username admin"
AUTH_PASSWORD="${AUTH_PASSWORD:-}"
# AUTH_PASSWORD="--auth-password password"

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

echo "Starting ACE-Step Gradio Web UI..."
echo "Server will be available at: http://${SERVER_NAME}:${PORT}"
echo

# ==================== Standard uv Workflow ====================
# Works on all platforms: x86_64 Linux (cu128), aarch64 Linux/DGX Spark (cu130),
# macOS (MPS), Windows (cu128). uv resolves the correct PyTorch wheels via
# platform-specific index mappings in pyproject.toml.

# Check if uv is installed
if ! command -v uv &>/dev/null; then
    # Try common install locations
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
            echo "========================================"
            echo "uv installed successfully!"
            echo "========================================"
            echo

            export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

            if command -v uv &>/dev/null; then
                echo "uv is now available!"
                uv --version
                echo
            else
                echo
                echo "uv installed but not in PATH yet."
                echo "Please restart your terminal or run:"
                echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
                echo
                exit 1
            fi
        else
            echo
            echo "========================================"
            echo "Installation failed!"
            echo "========================================"
            echo
            echo "Please install uv manually:"
            echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            echo
            exit 1
        fi
    else
        echo
        echo "Installation cancelled."
        echo
        echo "To use ACE-Step, please install uv:"
        echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo
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

    cd "$SCRIPT_DIR" && uv sync

    echo
    echo "========================================"
    echo "Environment setup completed!"
    echo "========================================"
    echo
fi

echo "Starting ACE-Step Gradio UI..."
echo

# Build command with optional parameters
CMD="uv run acestep --port $PORT --server-name $SERVER_NAME --language $LANGUAGE"
[[ -n "$SHARE" ]] && CMD="$CMD $SHARE"
[[ -n "$CONFIG_PATH" ]] && CMD="$CMD $CONFIG_PATH"
[[ -n "$LM_MODEL_PATH" ]] && CMD="$CMD $LM_MODEL_PATH"
[[ -n "$OFFLOAD_TO_CPU" ]] && CMD="$CMD $OFFLOAD_TO_CPU"
[[ -n "$INIT_LLM" ]] && CMD="$CMD $INIT_LLM"
[[ -n "$DOWNLOAD_SOURCE" ]] && CMD="$CMD $DOWNLOAD_SOURCE"
[[ -n "$INIT_SERVICE" ]] && CMD="$CMD $INIT_SERVICE"
[[ -n "$BATCH_SIZE" ]] && CMD="$CMD $BATCH_SIZE"
[[ -n "$ENABLE_API" ]] && CMD="$CMD $ENABLE_API"
[[ -n "$API_KEY" ]] && CMD="$CMD $API_KEY"
[[ -n "$AUTH_USERNAME" ]] && CMD="$CMD $AUTH_USERNAME"
[[ -n "$AUTH_PASSWORD" ]] && CMD="$CMD $AUTH_PASSWORD"

cd "$SCRIPT_DIR" && $CMD
