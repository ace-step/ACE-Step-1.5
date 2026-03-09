#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Minimal AceFlow UI launcher for standard ACE-Step uv workflow
# Optional overrides before launch:
#   export PORT=7861
#   export SERVER_NAME=127.0.0.1
#   export ACEFLOW_CONFIG_PATH=acestep-v15-turbo
#   export ACEFLOW_LM_MODEL_PATH=acestep-5Hz-lm-4B
#   export ACEFLOW_DEVICE=auto
#   export ACEFLOW_RESULTS_DIR="$SCRIPT_DIR/aceflow_outputs"

: "${PORT:=7861}"
: "${SERVER_NAME:=127.0.0.1}"
: "${ACEFLOW_CONFIG_PATH:=acestep-v15-turbo}"
: "${ACEFLOW_LM_MODEL_PATH:=acestep-5Hz-lm-4B}"
: "${ACEFLOW_DEVICE:=auto}"
: "${ACEFLOW_RESULTS_DIR:=$SCRIPT_DIR/aceflow_outputs}"

echo "Starting AceFlow UI..."
echo "Server will be available at: http://${SERVER_NAME}:${PORT}"
echo

if ! command -v uv >/dev/null 2>&1; then
    if [[ -x "$HOME/.local/bin/uv" ]]; then
        export PATH="$HOME/.local/bin:$PATH"
    elif [[ -x "$HOME/.cargo/bin/uv" ]]; then
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
fi

if ! command -v uv >/dev/null 2>&1; then
    echo
    echo "========================================"
    echo "uv package manager not found!"
    echo "========================================"
    echo
    echo "ACE-Step requires the uv package manager."
    echo
    exit 1
fi

echo "[Environment] Using uv package manager..."
echo

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
            exit 1
        fi
    fi

    echo
    echo "========================================"
    echo "Environment setup completed!"
    echo "========================================"
    echo
fi

export ACESTEP_REMOTE_CONFIG_PATH="$ACEFLOW_CONFIG_PATH"
export ACESTEP_REMOTE_LM_MODEL_PATH="$ACEFLOW_LM_MODEL_PATH"
export ACESTEP_REMOTE_DEVICE="$ACEFLOW_DEVICE"
export ACESTEP_REMOTE_RESULTS_DIR="$ACEFLOW_RESULTS_DIR"

echo "[AceFlow] CFG=$ACESTEP_REMOTE_CONFIG_PATH | LM=$ACESTEP_REMOTE_LM_MODEL_PATH | DEVICE=$ACESTEP_REMOTE_DEVICE"
echo

ACESTEP_ARGS=(python -m acestep.ui.aceflow.run --host "$SERVER_NAME" --port "$PORT")

cd "$SCRIPT_DIR" && uv run "${ACESTEP_ARGS[@]}" || {
    echo
    echo "[Retry] Online dependency resolution failed, retrying in offline mode..."
    echo
    cd "$SCRIPT_DIR" && uv run --offline "${ACESTEP_ARGS[@]}" || {
        echo
        echo "========================================"
        echo "[Error] Failed to start AceFlow UI"
        echo "========================================"
        echo
        exit 1
    }
}
