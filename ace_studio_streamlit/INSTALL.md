"""
ACE Studio Streamlit - Installation & Setup Guide
"""

# Installation Instructions

## Prerequisites

- Python 3.8+ (tested with 3.11)
- ACE-Step main project installed (parent directory)
- pip or uv for package management

## Step 1: Install Dependencies

From the `ace_studio_streamlit` directory:

```bash
pip install -r requirements.txt
```

Or with uv (faster):

```bash
uv pip install -r requirements.txt
```

## Step 2: Configure (Optional)

Edit `config.py` to customize:
- Default generation parameters
- UI appearance
- Storage paths
- Audio formats

## Step 3: Run the App

```bash
streamlit run main.py
```

The app will open at `http://localhost:8501`

## System Requirements

### Minimum
- 4GB VRAM (CPU only)
- Intel i5 or equivalent
- 2GB RAM

### Recommended
- 8GB+ VRAM (GPU)
- RTX 3060 or equivalent
- 8GB+ RAM

### Optimal
- 16GB+ VRAM
- RTX 4090 or A100
- 16GB+ RAM

## GPU Support

### CUDA (NVIDIA)
Preinstalled CUDA 12.1+

### ROCm (AMD)
Set environment variable:
```bash
export PYTORCH_HIP_ALLOC_CONF=":256:8"
```

### MPS (Apple Silicon)
Automatic detection and use

### CPU
Works but slow; set device to CPU in Settings

## Troubleshooting Installation

### Module not found errors
```bash
# Reinstall ACE-Step dependencies
cd ..  # Go to main ACE-Step dir
pip install -e .
```

### Streamlit port already in use
```bash
streamlit run main.py --server.port 8502
```

### Clear cache and restart
```bash
streamlit cache clear
streamlit run main.py
```

## Docker Deployment (Optional)

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

Build and run:
```bash
docker build -t ace-studio .
docker run -p 8501:8501 -v $(pwd)/projects:/app/projects ace-studio
```

## Environment Variables

Optional `.env` file:

```env
# GPU Configuration
DEVICE=cuda
OFFLOAD_CPU=1
FLASHATTN=1

# Model Configuration
DIT_MODEL=acestep-v15-turbo
LLM_MODEL=1.7B

# UI Configuration
MAX_BATCH_SIZE=4
DEFAULT_DURATION=120
DEFAULT_BPM=120

# Storage
PROJECTS_DIR=./projects
CACHE_DIR=./.cache
```

## Next Steps

1. Go to **Dashboard** for quick start
2. Try **Generate** to create first song
3. Explore **Edit** features
4. Check **Settings** for optimal configuration

## Getting Help

- 📖 See README.md for usage guide
- 🐛 Report issues on GitHub
- 💬 Ask in Discord community
- 📚 Check ACE-Step documentation
