FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    ffmpeg \
    git \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy all source (local path deps like nano-vllm need to be present)
COPY . .

# Install dependencies and clean cache to reclaim disk space
RUN uv sync --no-dev \
    && uv cache clean

# Environment defaults
ENV ACESTEP_CONFIG_PATH=acestep-v15-turbo
ENV ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-1.7B
ENV ACESTEP_LM_BACKEND=vllm
ENV ACESTEP_DEVICE=auto
ENV SERVER_NAME=0.0.0.0
ENV PORT=8001

EXPOSE 8001

# Run the API server
CMD ["uv", "run", "acestep-api", "--host", "0.0.0.0", "--port", "8001"]
