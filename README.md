<h1 align="center">ACE-Step 1.5</h1>
<h1 align="center">Pushing the Boundaries of Open-Source Music Generation</h1>
<p align="center">
    <a href="https://ace-step.github.io/ace-step-v1.5.github.io/">Project</a> |
    <a href="https://huggingface.co/ACE-Step/Ace-Step1.5">Hugging Face</a> |
    <a href="https://modelscope.cn/models/ACE-Step/Ace-Step1.5">ModelScope</a> |
    <a href="https://huggingface.co/spaces/ACE-Step/Ace-Step-v1.5">Space Demo</a> |
    <a href="https://discord.gg/PeWDxrkdj7">Discord</a> |
    <a href="https://arxiv.org/abs/2602.00744">Technical Report</a>
</p>

<p align="center">
    <img src="./assets/orgnization_logos.png" width="100%" alt="StepFun Logo">
</p>

## Table of Contents

- [✨ Features](#-features)
- [📦 Installation](#-installation)
- [📥 Model Download](#-model-download)
- [🚀 Usage](#-usage)
- [📖 Tutorial](#-tutorial)
- [🔨 Train](#-train)
- [🏗️ Architecture](#️-architecture)
- [🦁 Model Zoo](#-model-zoo)

## 📝 Abstract
🚀 We present ACE-Step v1.5, a highly efficient open-source music foundation model that brings commercial-grade generation to consumer hardware. On commonly used evaluation metrics, ACE-Step v1.5 achieves quality beyond most commercial music models while remaining extremely fast—under 2 seconds per full song on an A100 and under 10 seconds on an RTX 3090. The model runs locally with less than 4GB of VRAM, and supports lightweight personalization: users can train a LoRA from just a few songs to capture their own style.

🌉 At its core lies a novel hybrid architecture where the Language Model (LM) functions as an omni-capable planner: it transforms simple user queries into comprehensive song blueprints—scaling from short loops to 10-minute compositions—while synthesizing metadata, lyrics, and captions via Chain-of-Thought to guide the Diffusion Transformer (DiT). ⚡ Uniquely, this alignment is achieved through intrinsic reinforcement learning relying solely on the model's internal mechanisms, thereby eliminating the biases inherent in external reward models or human preferences. 🎚️

🔮 Beyond standard synthesis, ACE-Step v1.5 unifies precise stylistic control with versatile editing capabilities—such as cover generation, repainting, and vocal-to-BGM conversion—while maintaining strict adherence to prompts across 50+ languages. This paves the way for powerful tools that seamlessly integrate into the creative workflows of music artists, producers, and content creators. 🎸


## ✨ Features

<p align="center">
    <img src="./assets/application_map.png" width="100%" alt="ACE-Step Framework">
</p>

### ⚡ Performance
- ✅ **Ultra-Fast Generation** — Under 2s per full song on A100, under 10s on RTX 3090 (0.5s to 10s on A100 depending on think mode & diffusion steps)
- ✅ **Flexible Duration** — Supports 10 seconds to 10 minutes (600s) audio generation
- ✅ **Batch Generation** — Generate up to 8 songs simultaneously

### 🎵 Generation Quality
- ✅ **Commercial-Grade Output** — Quality beyond most commercial music models (between Suno v4.5 and Suno v5)
- ✅ **Rich Style Support** — 1000+ instruments and styles with fine-grained timbre description
- ✅ **Multi-Language Lyrics** — Supports 50+ languages with lyrics prompt for structure & style control

### 🎛️ Versatility & Control

| Feature | Description |
|---------|-------------|
| ✅ Reference Audio Input | Use reference audio to guide generation style |
| ✅ Cover Generation | Create covers from existing audio |
| ✅ Repaint & Edit | Selective local audio editing and regeneration |
| ✅ Track Separation | Separate audio into individual stems |
| ✅ Multi-Track Generation | Add layers like Suno Studio's "Add Layer" feature |
| ✅ Vocal2BGM | Auto-generate accompaniment for vocal tracks |
| ✅ Metadata Control | Control duration, BPM, key/scale, time signature |
| ✅ Simple Mode | Generate full songs from simple descriptions |
| ✅ Query Rewriting | Auto LM expansion of tags and lyrics |
| ✅ Audio Understanding | Extract BPM, key/scale, time signature & caption from audio |
| ✅ LRC Generation | Auto-generate lyric timestamps for generated music |
| ✅ LoRA Training | One-click annotation & training in Gradio. 8 songs, 1 hour on 3090 (12GB VRAM) |
| ✅ Quality Scoring | Automatic quality assessment for generated audio |

## Staying ahead
-----------------
Star ACE-Step on GitHub and be instantly notified of new releases
![](assets/star.gif)

## 📦 Installation

> **Requirements:** Python 3.11, CUDA GPU recommended (works on CPU/MPS but slower)

### 🪟 Windows Portable Package (Recommended for Windows)

For Windows users, we provide a portable package with pre-installed dependencies:

1. Download and extract: [ACE-Step-1.5.7z](https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z)
2. The package includes `python_embeded` with all dependencies pre-installed
3. **Requirements:** CUDA 12.8

**Launch:**

```bash
# Gradio Web UI
python_embeded\python acestep\acestep_v15_pipeline.py

# REST API Server
python_embeded\python acestep\api_server.py
```

---

### Standard Installation (All Platforms)

### 1. Install uv (Package Manager)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone & Install

```bash
git clone https://github.com/ACE-Step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync
```

### 3. Launch

#### 🖥️ Gradio Web UI (Recommended)

```bash
uv run acestep
```

Open http://localhost:7860 in your browser. Models will be downloaded automatically on first run.

#### 🌐 REST API Server

```bash
uv run acestep-api
```

API runs at http://localhost:8001. See [API Documentation](./docs/en/API.md) for endpoints.

### Command Line Options

**Gradio UI (`acestep`):**

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | 7860 | Server port |
| `--server-name` | 127.0.0.1 | Server address (use `0.0.0.0` for network access) |
| `--share` | false | Create public Gradio link |
| `--language` | en | UI language: `en`, `zh`, `ja` |
| `--init_service` | false | Auto-initialize models on startup |
| `--config_path` | auto | DiT model (e.g., `acestep-v15-turbo`, `acestep-v15-turbo-shift3`) |
| `--lm_model_path` | auto | LM model (e.g., `acestep-5Hz-lm-0.6B`, `acestep-5Hz-lm-1.7B`) |
| `--offload_to_cpu` | auto | CPU offload (auto-enabled if VRAM < 16GB) |
| `--enable-api` | false | Enable REST API endpoints alongside Gradio UI |
| `--api-key` | none | API key for API endpoints authentication |
| `--auth-username` | none | Username for Gradio authentication |
| `--auth-password` | none | Password for Gradio authentication |

**Examples:**

```bash
# Public access with Chinese UI
uv run acestep --server-name 0.0.0.0 --share --language zh

# Pre-initialize models on startup
uv run acestep --init_service true --config_path acestep-v15-turbo

# Enable API endpoints with authentication
uv run acestep --enable-api --api-key sk-your-secret-key --port 8001

# Enable both Gradio auth and API auth
uv run acestep --enable-api --api-key sk-123456 --auth-username admin --auth-password password
```

### Development

```bash
# Add dependencies
uv add package-name
uv add --dev package-name

# Update all dependencies
uv sync --upgrade
```

## � Other GPU Support

### Intel GPU
Currently, we support Intel GPUs.
- **Tested Device**: Windows laptop with Ultra 9 285H integrated graphics.
- **Settings**:
  - `offload` is disabled by default.
  - `compile` and `quantization` are enabled by default.
- **Capabilities**: LLM inference is supported (tested with `acestep-5Hz-lm-0.6B`).
  - *Note*: LLM inference speed might decrease when generating audio longer than 2 minutes.
  - *Note*: `nanovllm` acceleration for LLM inference is currently NOT supported on Intel GPUs.
- **Test Environment**: PyTorch 2.8.0 from [Intel Extension for PyTorch](https://pytorch-extension.intel.com/?request=platform).
- **Intel Discrete GPUs**: Expected to work, but not tested yet as the developer does not have available devices. Waiting for community feedback.

## �📥 Model Download

Models are automatically downloaded from [HuggingFace](https://huggingface.co/ACE-Step/Ace-Step1.5) or [ModelScope](https://modelscope.cn/organization/ACE-Step) on first run. You can also manually download models using the CLI or `huggingface-cli`.

### Automatic Download

When you run `acestep` or `acestep-api`, the system will:
1. Check if the required models exist in `./checkpoints`
2. If not found, automatically download them from HuggingFace

### Manual Download with CLI

```bash
# Download main model (includes everything needed to run)
uv run acestep-download

# Download all available models (including optional variants)
uv run acestep-download --all

# Download a specific model
uv run acestep-download --model acestep-v15-sft

# List all available models
uv run acestep-download --list

# Download to a custom directory
uv run acestep-download --dir /path/to/checkpoints
```

### Manual Download with huggingface-cli

You can also use `huggingface-cli` directly:

```bash
# Download main model (includes vae, Qwen3-Embedding-0.6B, acestep-v15-turbo, acestep-5Hz-lm-1.7B)
huggingface-cli download ACE-Step/Ace-Step1.5 --local-dir ./checkpoints

# Download optional LM models
huggingface-cli download ACE-Step/acestep-5Hz-lm-0.6B --local-dir ./checkpoints/acestep-5Hz-lm-0.6B
huggingface-cli download ACE-Step/acestep-5Hz-lm-4B --local-dir ./checkpoints/acestep-5Hz-lm-4B

# Download optional DiT models
huggingface-cli download ACE-Step/acestep-v15-base --local-dir ./checkpoints/acestep-v15-base
huggingface-cli download ACE-Step/acestep-v15-sft --local-dir ./checkpoints/acestep-v15-sft
huggingface-cli download ACE-Step/acestep-v15-turbo-shift1 --local-dir ./checkpoints/acestep-v15-turbo-shift1
huggingface-cli download ACE-Step/acestep-v15-turbo-shift3 --local-dir ./checkpoints/acestep-v15-turbo-shift3
huggingface-cli download ACE-Step/acestep-v15-turbo-continuous --local-dir ./checkpoints/acestep-v15-turbo-continuous
```

### Available Models

| Model | HuggingFace Repo | Description |
|-------|------------------|-------------|
| **Main** | [ACE-Step/Ace-Step1.5](https://huggingface.co/ACE-Step/Ace-Step1.5) | Core components: vae, Qwen3-Embedding-0.6B, acestep-v15-turbo, acestep-5Hz-lm-1.7B |
| acestep-5Hz-lm-0.6B | [ACE-Step/acestep-5Hz-lm-0.6B](https://huggingface.co/ACE-Step/acestep-5Hz-lm-0.6B) | Lightweight LM model (0.6B params) |
| acestep-5Hz-lm-4B | [ACE-Step/acestep-5Hz-lm-4B](https://huggingface.co/ACE-Step/acestep-5Hz-lm-4B) | Large LM model (4B params) |
| acestep-v15-base | [ACE-Step/acestep-v15-base](https://huggingface.co/ACE-Step/acestep-v15-base) | Base DiT model |
| acestep-v15-sft | [ACE-Step/acestep-v15-sft](https://huggingface.co/ACE-Step/acestep-v15-sft) | SFT DiT model |
| acestep-v15-turbo-shift1 | [ACE-Step/acestep-v15-turbo-shift1](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift1) | Turbo DiT with shift1 |
| acestep-v15-turbo-shift3 | [ACE-Step/acestep-v15-turbo-shift3](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift3) | Turbo DiT with shift3 |
| acestep-v15-turbo-continuous | [ACE-Step/acestep-v15-turbo-continuous](https://huggingface.co/ACE-Step/acestep-v15-turbo-continuous) | Turbo DiT with continuous shift (1-5) |

### 💡 Which Model Should I Choose?

ACE-Step automatically adapts to your GPU's VRAM. Here's a quick guide:

| Your GPU VRAM | Recommended LM Model | Notes |
|---------------|---------------------|-------|
| **≤6GB** | None (DiT only) | LM disabled by default to save memory |
| **6-12GB** | `acestep-5Hz-lm-0.6B` | Lightweight, good balance |
| **12-16GB** | `acestep-5Hz-lm-1.7B` | Better quality |
| **≥16GB** | `acestep-5Hz-lm-4B` | Best quality and audio understanding |

> 📖 **For detailed GPU compatibility information** (duration limits, batch sizes, memory optimization), see GPU Compatibility Guide: [English](./docs/en/GPU_COMPATIBILITY.md) | [中文](./docs/zh/GPU_COMPATIBILITY.md) | [日本語](./docs/ja/GPU_COMPATIBILITY.md)


## 🚀 Usage

We provide multiple ways to use ACE-Step:

| Method | Description | Documentation |
|--------|-------------|---------------|
| 🖥️ **Gradio Web UI** | Interactive web interface for music generation | [Gradio Guide](./docs/en/GRADIO_GUIDE.md) |
| 🐍 **Python API** | Programmatic access for integration | [Inference API](./docs/en/INFERENCE.md) |
| 🌐 **REST API** | HTTP-based async API for services | [REST API](./docs/en/API.md) |

**📚 Documentation available in:** [English](./docs/en/) | [中文](./docs/zh/) | [日本語](./docs/ja/)

## 📖 Tutorial

**🎯 Must Read:** Comprehensive guide to ACE-Step 1.5's design philosophy and usage methods.

| Language | Link |
|----------|------|
| 🇺🇸 English | [English Tutorial](./docs/en/Tutorial.md) |
| 🇨🇳 中文 | [中文教程](./docs/zh/Tutorial.md) |
| 🇯🇵 日本語 | [日本語チュートリアル](./docs/ja/Tutorial.md) |

This tutorial covers:
- Mental models and design philosophy
- Model architecture and selection
- Input control (text and audio)
- Inference hyperparameters
- Random factors and optimization strategies

## 🔨 Train

See the **LoRA Training** tab in Gradio UI for one-click training, or check [Gradio Guide - LoRA Training](./docs/en/GRADIO_GUIDE.md#lora-training) for details.

## 🏗️ Architecture

<p align="center">
    <img src="./assets/ACE-Step_framework.png" width="100%" alt="ACE-Step Framework">
</p>

## 🦁 Model Zoo

<p align="center">
    <img src="./assets/model_zoo.png" width="100%" alt="Model Zoo">
</p>

### DiT Models

| DiT Model | Pre-Training | SFT | RL | CFG | Step | Refer audio | Text2Music | Cover | Repaint | Extract | Lego | Complete | Quality | Diversity | Fine-Tunability | Hugging Face |
|-----------|:------------:|:---:|:--:|:---:|:----:|:-----------:|:----------:|:-----:|:-------:|:-------:|:----:|:--------:|:-------:|:---------:|:---------------:|--------------|
| `acestep-v15-base` | ✅ | ❌ | ❌ | ✅ | 50 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Medium | High | Easy | [Link](https://huggingface.co/ACE-Step/acestep-v15-base) |
| `acestep-v15-sft` | ✅ | ✅ | ❌ | ✅ | 50 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | High | Medium | Easy | [Link](https://huggingface.co/ACE-Step/acestep-v15-sft) |
| `acestep-v15-turbo` | ✅ | ✅ | ❌ | ❌ | 8 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | Very High | Medium | Medium | [Link](https://huggingface.co/ACE-Step/Ace-Step1.5) |
| `acestep-v15-turbo-rl` | ✅ | ✅ | ✅ | ❌ | 8 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | Very High | Medium | Medium | To be released |

### LM Models

| LM Model | Pretrain from | Pre-Training | SFT | RL | CoT metas | Query rewrite | Audio Understanding | Composition Capability | Copy Melody | Hugging Face |
|----------|---------------|:------------:|:---:|:--:|:---------:|:-------------:|:-------------------:|:----------------------:|:-----------:|--------------|
| `acestep-5Hz-lm-0.6B` | Qwen3-0.6B | ✅ | ✅ | ✅ | ✅ | ✅ | Medium | Medium | Weak | ✅ |
| `acestep-5Hz-lm-1.7B` | Qwen3-1.7B | ✅ | ✅ | ✅ | ✅ | ✅ | Medium | Medium | Medium | ✅ |
| `acestep-5Hz-lm-4B` | Qwen3-4B | ✅ | ✅ | ✅ | ✅ | ✅ | Strong | Strong | Strong | ✅ |

## 📜 License & Disclaimer

This project is licensed under [MIT](./LICENSE)

ACE-Step enables original music generation across diverse genres, with applications in creative production, education, and entertainment. While designed to support positive and artistic use cases, we acknowledge potential risks such as unintentional copyright infringement due to stylistic similarity, inappropriate blending of cultural elements, and misuse for generating harmful content. To ensure responsible use, we encourage users to verify the originality of generated works, clearly disclose AI involvement, and obtain appropriate permissions when adapting protected styles or materials. By using ACE-Step, you agree to uphold these principles and respect artistic integrity, cultural diversity, and legal compliance. The authors are not responsible for any misuse of the model, including but not limited to copyright violations, cultural insensitivity, or the generation of harmful content.

🔔 Important Notice  
The only official website for the ACE-Step project is our GitHub Pages site.    
 We do not operate any other websites.  
🚫 Fake domains include but are not limited to:
ac\*\*p.com, a\*\*p.org, a\*\*\*c.org  
⚠️ Please be cautious. Do not visit, trust, or make payments on any of those sites.

## 🙏 Acknowledgements

This project is co-led by ACE Studio and StepFun.


## 📖 Citation

If you find this project useful for your research, please consider citing:

```BibTeX
@misc{gong2026acestep,
	title={ACE-Step 1.5: Pushing the Boundaries of Open-Source Music Generation},
	author={Junmin Gong, Yulin Song, Wenxiao Zhao, Sen Wang, Shengyuan Xu, Jing Guo}, 
	howpublished={\url{https://github.com/ace-step/ACE-Step-1.5}},
	year={2026},
	note={GitHub repository}
}
```
