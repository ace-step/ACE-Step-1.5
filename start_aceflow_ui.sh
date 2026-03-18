#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ============================================================
# AceFlow official launcher - 8 GB VRAM preset ACTIVE
# ============================================================
# In AceFlow the service is initialized by the launcher, not by
# the web UI. So the options below matter before opening the page.
# ============================================================

# ===== venv =====
if [[ -f "$SCRIPT_DIR/venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/venv/bin/activate"
fi

PY="$SCRIPT_DIR/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

# ===== environment sane =====
export PYTHONNOUSERSITE=1
unset PYTHONHOME || true
unset PYTHONPATH || true
export PYTORCH_ALLOC_CONF=expandable_segments:True
export CUDA_MODULE_LOADING=LAZY

TORCH_LIB="$SCRIPT_DIR/venv/lib/python3.11/site-packages/torch/lib"
if [[ -d "$TORCH_LIB" ]]; then
  export LD_LIBRARY_PATH="$TORCH_LIB:${LD_LIBRARY_PATH:-}"
fi

# ===== Remote UI config =====
export PORT="${PORT:-7861}"
export SERVER_NAME="${SERVER_NAME:-0.0.0.0}"
export ACESTEP_REMOTE_CONFIG_PATH="${ACESTEP_REMOTE_CONFIG_PATH:-acestep-v15-turbo}"
export ACESTEP_REMOTE_LM_MODEL_PATH="${ACESTEP_REMOTE_LM_MODEL_PATH:-acestep-5Hz-lm-0.6B}"
export ACESTEP_REMOTE_DEVICE="${ACESTEP_REMOTE_DEVICE:-auto}"
export ACESTEP_REMOTE_RESULTS_DIR="${ACESTEP_REMOTE_RESULTS_DIR:-$SCRIPT_DIR/aceflow_outputs}"

# ===== 8 GB VRAM preset ACTIVE =====
export ACESTEP_REMOTE_INIT_LLM="${ACESTEP_REMOTE_INIT_LLM:-1}"
export ACESTEP_REMOTE_USE_FLASH_ATTENTION="${ACESTEP_REMOTE_USE_FLASH_ATTENTION:-1}"
export ACESTEP_REMOTE_OFFLOAD_TO_CPU="${ACESTEP_REMOTE_OFFLOAD_TO_CPU:-1}"
export ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU="${ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU:-1}"
export ACESTEP_REMOTE_COMPILE_MODEL="${ACESTEP_REMOTE_COMPILE_MODEL:-1}"
export ACESTEP_REMOTE_INT8_QUANTIZATION="${ACESTEP_REMOTE_INT8_QUANTIZATION:-1}"
export ACESTEP_REMOTE_LM_BACKEND="${ACESTEP_REMOTE_LM_BACKEND:-pt}"
export ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU="${ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU:-1}"

# ===== Alternate presets (examples only) =====
# Balanced 12-16 GB example:
# export ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-1.7B
# export ACESTEP_REMOTE_OFFLOAD_TO_CPU=0
# export ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=0
# export ACESTEP_REMOTE_INT8_QUANTIZATION=0
# export ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=0
#
# High VRAM / 5090-style example:
# export ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-4B
# export ACESTEP_REMOTE_USE_FLASH_ATTENTION=1
# export ACESTEP_REMOTE_OFFLOAD_TO_CPU=0
# export ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=0
# export ACESTEP_REMOTE_COMPILE_MODEL=0
# export ACESTEP_REMOTE_INT8_QUANTIZATION=0
# export ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=0

# ===== AceFlow =====
export ACEFLOW_AUTH_ENABLED="${ACEFLOW_AUTH_ENABLED:-0}"
export ACEFLOW_SESSION_SECURE="${ACEFLOW_SESSION_SECURE:-0}"
export ACEFLOW_BYPASS_CORE_TURBO_STEP_CLAMP="${ACEFLOW_BYPASS_CORE_TURBO_STEP_CLAMP:-1}"
export ACEFLOW_CLEANUP_TTL_SECONDS="${ACEFLOW_CLEANUP_TTL_SECONDS:-3600}"

echo "Starting ACE-Step Remote UI..."
echo "http://${SERVER_NAME}:${PORT}"
echo "[ACE] PY=${PY} | CFG=${ACESTEP_REMOTE_CONFIG_PATH} | LM=${ACESTEP_REMOTE_LM_MODEL_PATH}"
echo "[ACE] INIT_LLM=${ACESTEP_REMOTE_INIT_LLM} | OFFLOAD=${ACESTEP_REMOTE_OFFLOAD_TO_CPU} | DIT_OFFLOAD=${ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU} | INT8=${ACESTEP_REMOTE_INT8_QUANTIZATION}"
echo

exec "$PY" -m acestep.ui.aceflow.run --host "$SERVER_NAME" --port "$PORT"
