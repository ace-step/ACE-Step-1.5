# =============================================================================
# ACE-Step 1.5 — Docker Desktop (x86_64 CUDA)
# =============================================================================
#
# Build:
#   docker build -t acestep .
#
# Run (Gradio UI):
#   docker run --gpus all -it --rm -p 7860:7860 \
#     -v ./checkpoints:/app/checkpoints \
#     -v ./gradio_outputs:/app/gradio_outputs \
#     acestep
#
# Run (REST API):
#   docker run --gpus all -it --rm -p 8001:8001 \
#     -v ./checkpoints:/app/checkpoints \
#     -e ACESTEP_MODE=api \
#     acestep
# =============================================================================

FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04

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
        ffmpeg \
        libsndfile1 \
        libsndfile1-dev \
        python3.11 \
        python3.11-dev \
        python3.11-venv \
        python3-pip \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && rm -rf /var/lib/apt/lists/*

# ==================== Pip bootstrap ====================
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
    && pip install --no-cache-dir --upgrade pip setuptools wheel

# ==================== PyTorch (CUDA 12.8) ====================
RUN pip install --no-cache-dir \
        torch==2.10.0+cu128 \
        torchvision==0.25.0+cu128 \
        torchaudio==2.10.0+cu128 \
        --index-url https://download.pytorch.org/whl/cu128

# ==================== Project source ====================
WORKDIR /app
COPY . /app/

# ==================== Python dependencies ====================
RUN pip install --no-cache-dir \
        "transformers>=4.51.0,<4.58.0" \
        "diffusers" \
        "gradio==6.2.0" \
        "matplotlib>=3.7.5" \
        "scipy>=1.10.1" \
        "soundfile>=0.13.1" \
        "loguru>=0.7.3" \
        "einops>=0.8.1" \
        "accelerate>=1.12.0" \
        "fastapi>=0.110.0" \
        "diskcache" \
        "uvicorn[standard]>=0.27.0" \
        "numba>=0.63.1" \
        "vector-quantize-pytorch>=1.27.15" \
        "torchcodec>=0.9.1" \
        "torchao>=0.14.1,<0.16.0" \
        "toml" \
        "safetensors" \
        "modelscope" \
        "peft>=0.18.0" \
        "lycoris-lora" \
        "lightning>=2.0.0" \
        "tensorboard>=2.20.0" \
        "typer-slim>=0.21.1" \
        "xxhash" \
        "pyyaml" \
    && pip install --no-cache-dir --no-deps /app/acestep/third_parts/nano-vllm

# ==================== Runtime directories ====================
RUN mkdir -p /app/checkpoints /app/gradio_outputs

# ==================== Environment defaults ====================
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV ACESTEP_MODE=gradio
ENV ACESTEP_INIT_SERVICE=true
ENV ACESTEP_CONFIG_PATH=acestep-v15-turbo
ENV ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B
ENV ACESTEP_LM_BACKEND=pt
ENV TOKENIZERS_PARALLELISM=false

# ==================== Ports ====================
EXPOSE 7860 8001

# ==================== Health check ====================
HEALTHCHECK --interval=60s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -sf http://localhost:${GRADIO_PORT:-7860}/ > /dev/null 2>&1 \
     || curl -sf http://localhost:${ACESTEP_API_PORT:-8001}/health > /dev/null 2>&1 \
     || exit 1

# ==================== Entrypoint ====================
COPY <<'EOF' /app/docker-entrypoint.sh
#!/usr/bin/env bash
set -e

echo "==========================================="
echo "  ACE-Step 1.5 — Docker Desktop"
echo "==========================================="
echo "Mode      : ${ACESTEP_MODE}"
echo "Python    : $(python --version 2>&1)"
echo "PyTorch   : $(python -c 'import torch; print(torch.__version__)' 2>/dev/null || echo 'N/A')"

if python -c 'import torch; assert torch.cuda.is_available()' 2>/dev/null; then
    echo "CUDA      : $(python -c 'import torch; print(torch.version.cuda)')"
    echo "GPU       : $(python -c 'import torch; print(torch.cuda.get_device_name(0))')"
    echo "VRAM      : $(python -c 'import torch; p=torch.cuda.get_device_properties(0); print(f"{p.total_memory/1024**3:.1f} GB")')"
else
    echo "CUDA      : NOT AVAILABLE — running on CPU"
    echo "           (make sure you launched with --gpus all)"
fi
echo "==========================================="

INIT_ARGS=""
if [ "${ACESTEP_INIT_SERVICE:-true}" = "true" ]; then
    INIT_ARGS="--init_service true"
    [ -n "${ACESTEP_CONFIG_PATH:-}" ]   && INIT_ARGS="${INIT_ARGS} --config_path ${ACESTEP_CONFIG_PATH}"
    [ -n "${ACESTEP_LM_MODEL_PATH:-}" ] && INIT_ARGS="${INIT_ARGS} --init_llm true --lm_model_path ${ACESTEP_LM_MODEL_PATH}"
fi
[ -n "${ACESTEP_LM_BACKEND:-}" ] && INIT_ARGS="${INIT_ARGS} --backend ${ACESTEP_LM_BACKEND}"

if [ "${ACESTEP_MODE}" = "api" ]; then
    echo "Starting REST API server on 0.0.0.0:${ACESTEP_API_PORT:-8001} ..."
    exec python -m acestep.api_server \
        --host "${ACESTEP_API_HOST:-0.0.0.0}" \
        --port "${ACESTEP_API_PORT:-8001}" \
        ${ACESTEP_EXTRA_ARGS:-}
else
    echo "Starting Gradio UI on 0.0.0.0:${GRADIO_PORT:-7860} ..."
    exec python -m acestep.acestep_v15_pipeline \
        --server-name "${GRADIO_SERVER_NAME:-0.0.0.0}" \
        --port "${GRADIO_PORT:-7860}" \
        ${INIT_ARGS} \
        ${ACESTEP_EXTRA_ARGS:-}
fi
EOF

RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
