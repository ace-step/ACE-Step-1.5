FROM nvidia/cuda:12.8.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system deps + Python 3.11
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common curl git ffmpeg libsndfile1 \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3.11 python3.11-venv python3.11-dev \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY . .

# Install dependencies
RUN uv sync

# Models will be mounted at /app/checkpoints
VOLUME /app/checkpoints

# Gradio UI port
EXPOSE 7860
# API port
EXPOSE 8001

# Default: launch Gradio UI
CMD ["uv", "run", "acestep"]
