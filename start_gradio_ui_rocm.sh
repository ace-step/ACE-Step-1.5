#!/usr/bin/env bash
# ACE-Step Gradio Web UI Launcher - Linux AMD ROCm
# For AMD RX 7000/6000 series GPUs on Linux
# Requires: ROCm 6.x+ and ROCm PyTorch from https://pytorch.org/
#
# Setup:
#   1. Install ROCm: https://rocm.docs.amd.com/projects/install-on-linux/
#   2. Create venv:  python3 -m venv venv_rocm
#   3. Activate:     source venv_rocm/bin/activate
#   4. Install PyTorch for ROCm:
#      pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3
#   5. Install dependencies:
#      pip install -r requirements-rocm-linux.txt
#   6. Run this script: ./start_gradio_ui_rocm.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ==================== Load .env Configuration ====================
_load_env_file() {
    local env_file="${SCRIPT_DIR}/.env"
    if [[ ! -f "$env_file" ]]; then
        return 0
    fi

    echo "[Config] Loading configuration from .env file..."

    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue

        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"

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
        esac
    done < "$env_file"

    echo "[Config] Configuration loaded from .env"
}

_load_env_file

# ==================== ROCm Configuration ====================
# Force PyTorch LM backend (bypasses nano-vllm flash_attn dependency)
export ACESTEP_LM_BACKEND="pt"

# RDNA3 GPU architecture override (RX 7900 XT/XTX, RX 7800 XT, etc.)
# Change to 11.0.1 for gfx1101 (RX 7700 XT, RX 7800 XT)
# Change to 11.0.2 for gfx1102 (RX 7600)
export HSA_OVERRIDE_GFX_VERSION="${HSA_OVERRIDE_GFX_VERSION:-11.0.0}"

# MIOpen: use fast heuristic kernel selection instead of exhaustive benchmarking
# Without this, first-run VAE decode hangs for minutes on each conv layer
export MIOPEN_FIND_MODE="FAST"

# HuggingFace tokenizer parallelism
export TOKENIZERS_PARALLELISM="false"

# ==================== Server Configuration ====================
: "${PORT:=7860}"
: "${SERVER_NAME:=127.0.0.1}"
# SERVER_NAME="0.0.0.0"
SHARE="${SHARE:-}"
# SHARE="--share"

# UI language: en, zh, he, ja
: "${LANGUAGE:=en}"

# ==================== Model Configuration ====================
: "${CONFIG_PATH:=--config_path acestep-v15-turbo}"
: "${LM_MODEL_PATH:=--lm_model_path acestep-5Hz-lm-4B}"

# CPU offload: required for 4B LM on GPUs with <=20GB VRAM
# Disable if using 1.7B/0.6B LM or if your GPU has >=24GB VRAM
: "${OFFLOAD_TO_CPU:=--offload_to_cpu true}"

# LLM initialization: auto (default), true, false
INIT_LLM="${INIT_LLM:-}"
# INIT_LLM="--init_llm auto"

# Download source: auto, huggingface, modelscope
DOWNLOAD_SOURCE="${DOWNLOAD_SOURCE:-}"

# Auto-initialize models on startup
: "${INIT_SERVICE:=--init_service true}"

# LM backend: pt (PyTorch) recommended for ROCm
BACKEND="--backend pt"

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

# ==================== Venv Configuration ====================
VENV_DIR="${SCRIPT_DIR}/venv_rocm"

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

    local fetch_ok=0
    if command -v timeout &>/dev/null; then
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

echo "============================================"
echo "  ACE-Step 1.5 - Linux AMD ROCm Edition"
echo "============================================"
echo

# Activate venv if it exists
if [[ -f "$VENV_DIR/bin/activate" ]]; then
    echo "Activating virtual environment: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
else
    echo "WARNING: venv_rocm not found at $VENV_DIR"
    echo "Using system Python. See requirements-rocm-linux.txt for setup instructions."
fi
echo

# Verify ROCm PyTorch is installed
if ! python3 -c "
import torch
assert torch.cuda.is_available(), 'No GPU detected'
print(f'GPU: {torch.cuda.get_device_name(0)}')
hip = getattr(torch.version, 'hip', None)
print(f'HIP: {hip}' if hip else 'WARNING: Not a ROCm build')
" 2>/dev/null; then
    echo
    echo "========================================"
    echo " ERROR: ROCm PyTorch not detected!"
    echo "========================================"
    echo
    echo "Please install ROCm PyTorch first."
    echo "See requirements-rocm-linux.txt for instructions."
    echo
    echo "Quick setup:"
    echo "  python3 -m venv venv_rocm"
    echo "  source venv_rocm/bin/activate"
    echo "  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3"
    echo "  pip install -r requirements-rocm-linux.txt"
    echo
    exit 1
fi
echo

echo "Starting ACE-Step Gradio Web UI..."
echo "Server will be available at: http://${SERVER_NAME}:${PORT}"
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
[[ -n "$BACKEND" ]] && CMD="$CMD $BACKEND"
[[ -n "$ENABLE_API" ]] && CMD="$CMD $ENABLE_API"
[[ -n "$API_KEY" ]] && CMD="$CMD $API_KEY"
[[ -n "$AUTH_USERNAME" ]] && CMD="$CMD $AUTH_USERNAME"
[[ -n "$AUTH_PASSWORD" ]] && CMD="$CMD $AUTH_PASSWORD"

cd "$SCRIPT_DIR" && python3 -u acestep/acestep_v15_pipeline.py $CMD
