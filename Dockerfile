# =============================================================================
# ACE-Step 1.5 — Generic CUDA Dockerfile
# =============================================================================
#
# Builds ACE-Step 1.5 for x86_64 Linux servers with NVIDIA GPUs.
# Uses uv for fast, reproducible dependency installation.
#
# Build:
#   docker build -t acestep .
#
# Run (Gradio UI — default):
#   docker run --gpus all -it --rm \
#     -p 7860:7860 \
#     -v $(pwd)/checkpoints:/app/checkpoints \
#     -v $(pwd)/gradio_outputs:/app/gradio_outputs \
#     acestep
#
# Run (REST API server):
#   docker run --gpus all -it --rm \
#     -p 8001:8001 \
#     -v $(pwd)/checkpoints:/app/checkpoints \
#     -e ACESTEP_MODE=api \
#     acestep
#
# =============================================================================

# ==================== Build arguments ====================
ARG CUDA_VERSION=12.8.1
ARG PYTHON_VERSION=3.11
ARG UV_VERSION=0.7

# ==================== Base image ====================
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ==================== System packages ====================
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
        build-essential \
        git \
        curl \
        wget \
        # Audio libraries
        libsndfile1 \
        libsndfile1-dev \
        ffmpeg \
        # Python build deps
        libffi-dev \
        libssl-dev \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-dev \
        python3.11-venv \
    && rm -rf /var/lib/apt/lists/*

# ==================== uv ====================
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ==================== Project source ====================
WORKDIR /app
COPY . /app/

# ==================== Install dependencies via uv ====================
# Use uv sync with the lockfile for reproducible builds.
# --no-dev skips dev dependencies, --frozen uses exact lockfile versions.
RUN uv sync --frozen --no-dev --python python3.11

# ==================== Runtime directories ====================
RUN mkdir -p /app/checkpoints /app/gradio_outputs /app/output

# ==================== Environment ====================
# Bind to all interfaces for Docker port-mapping
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV ACESTEP_API_HOST=0.0.0.0

# Default startup mode: "gradio" for the web UI, "api" for the REST server
ENV ACESTEP_MODE=gradio

# Auto-initialize models on startup
ENV ACESTEP_INIT_SERVICE=true

# Default models
ENV ACESTEP_CONFIG_PATH=acestep-v15-turbo
ENV ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-4B
ENV ACESTEP_LLM_BACKEND=pt

# Disable tokenizers parallelism warnings
ENV TOKENIZERS_PARALLELISM=false

# ==================== Ports ====================
# 7860 = Gradio web UI | 8001 = REST API server
EXPOSE 7860 8001

# ==================== Health check ====================
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -sf http://localhost:${GRADIO_PORT:-7860}/ > /dev/null 2>&1 \
     || curl -sf http://localhost:${ACESTEP_API_PORT:-8001}/health > /dev/null 2>&1 \
     || exit 1

# ==================== Entrypoint ====================
COPY <<'ENTRYPOINT_EOF' /app/docker-entrypoint.sh
#!/usr/bin/env bash
set -e

echo "==========================================="
echo "  ACE-Step 1.5"
echo "==========================================="
echo "Mode      : ${ACESTEP_MODE}"
echo "Python    : $(uv run python --version 2>&1)"
echo "PyTorch   : $(uv run python -c 'import torch; print(torch.__version__)' 2>/dev/null || echo 'N/A')"

if uv run python -c 'import torch; assert torch.cuda.is_available()' 2>/dev/null; then
    echo "CUDA      : $(uv run python -c 'import torch; print(torch.version.cuda)')"
    echo "GPU       : $(uv run python -c 'import torch; print(torch.cuda.get_device_name(0))')"
    echo "Memory    : $(uv run python -c 'import torch; p=torch.cuda.get_device_properties(0); print(f"{p.total_memory/1024**3:.1f} GB")')"
else
    echo "CUDA      : NOT AVAILABLE — running on CPU"
    echo "           (make sure you launched with --gpus all)"
fi
echo "==========================================="

# Build --init_service flags
INIT_ARGS=""
if [ "${ACESTEP_INIT_SERVICE:-true}" = "true" ]; then
    INIT_ARGS="--init_service true"
    [ -n "${ACESTEP_CONFIG_PATH:-}" ]   && INIT_ARGS="${INIT_ARGS} --config_path ${ACESTEP_CONFIG_PATH}"
    [ -n "${ACESTEP_LM_MODEL_PATH:-}" ] && INIT_ARGS="${INIT_ARGS} --init_llm true --lm_model_path ${ACESTEP_LM_MODEL_PATH}"
    echo "Auto-init    : DiT=${ACESTEP_CONFIG_PATH:-auto}  LM=${ACESTEP_LM_MODEL_PATH:-none}"
fi

if [ "${ACESTEP_MODE}" = "api" ]; then
    echo "Starting REST API server on 0.0.0.0:${ACESTEP_API_PORT:-8001} ..."
    exec uv run python -m acestep.api_server \
        --host "${ACESTEP_API_HOST:-0.0.0.0}" \
        --port "${ACESTEP_API_PORT:-8001}" \
        ${ACESTEP_EXTRA_ARGS:-}
else
    echo "Starting Gradio UI on 0.0.0.0:${GRADIO_PORT:-7860} ..."
    exec uv run python -m acestep.acestep_v15_pipeline \
        --server-name "${GRADIO_SERVER_NAME:-0.0.0.0}" \
        --port "${GRADIO_PORT:-7860}" \
        --backend "${ACESTEP_LLM_BACKEND:-pt}" \
        ${INIT_ARGS} \
        ${ACESTEP_EXTRA_ARGS:-}
fi
ENTRYPOINT_EOF

RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
