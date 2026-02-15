# ACE-Step 1.5 安装指南

**Language / 语言 / 言語:** [English](../en/INSTALL.md) | [中文](INSTALL.md) | [日本語](../ja/INSTALL.md)

---

## 目录

- [环境要求](#环境要求)
- [快速开始（全平台）](#快速开始全平台)
- [启动脚本](#-启动脚本)
- [Windows 便携包](#-windows-便携包)
- [AMD / ROCm 显卡](#amd--rocm-显卡)
- [Intel 显卡](#intel-显卡)
- [仅 CPU 模式](#仅-cpu-模式)
- [Linux 注意事项](#linux-注意事项)
- [环境变量 (.env)](#环境变量-env)
- [命令行参数](#命令行参数)
- [模型下载](#-模型下载)
- [如何选择模型？](#-如何选择模型)
- [开发](#开发)

---

## 环境要求

| 项目 | 要求 |
|------|------|
| Python | 3.11-3.12（正式版，非预发布版）<br>**注意：** Windows 上的 ROCm 需要 Python 3.12 |
| GPU | 推荐 CUDA GPU；也支持 MPS / ROCm / Intel XPU / CPU |
| 显存 | 仅 DiT 模式 ≥4GB；LLM+DiT ≥6GB |
| 磁盘 | 核心模型约 10GB |

---

## 快速开始（全平台）

### 1. 安装 uv（包管理器）

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. 克隆 & 安装

```bash
git clone https://github.com/ACE-Step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync
```

### 3. 启动

**Gradio 网页界面（推荐）：**

```bash
uv run acestep
```

**REST API 服务器：**

```bash
uv run acestep-api
```

**直接使用 Python**（Conda / venv / 系统 Python）：

```bash
# 先激活你的环境，然后：
python acestep/acestep_v15_pipeline.py          # Gradio UI
python acestep/api_server.py                     # REST API
```

> 首次运行时模型会自动下载。打开 http://localhost:7860（Gradio）或 http://localhost:8001（API）。

---

## 🚀 启动脚本

为所有平台提供开箱即用的启动脚本。这些脚本会自动处理环境检测、依赖安装和应用启动。所有脚本默认在启动时检查更新（可配置）。

### 可用脚本

| 平台 | 脚本 | 说明 |
|------|------|------|
| **Windows** | `start_gradio_ui.bat` | 启动 Gradio 网页界面（CUDA） |
| **Windows** | `start_api_server.bat` | 启动 REST API 服务器（CUDA） |
| **Windows** | `start_gradio_ui_rocm.bat` | 启动 Gradio 网页界面（AMD ROCm） |
| **Windows** | `start_api_server_rocm.bat` | 启动 REST API 服务器（AMD ROCm） |
| **Linux** | `start_gradio_ui.sh` | 启动 Gradio 网页界面（CUDA） |
| **Linux** | `start_api_server.sh` | 启动 REST API 服务器（CUDA） |
| **macOS** | `start_gradio_ui_macos.sh` | 启动 Gradio 网页界面（MLX） |
| **macOS** | `start_api_server_macos.sh` | 启动 REST API 服务器（MLX） |

### Windows

```bash
# 启动 Gradio 网页界面（NVIDIA CUDA）
start_gradio_ui.bat

# 启动 REST API 服务器（NVIDIA CUDA）
start_api_server.bat

# 启动 Gradio 网页界面（AMD ROCm）
start_gradio_ui_rocm.bat

# 启动 REST API 服务器（AMD ROCm）
start_api_server_rocm.bat
```

> **ROCm 用户：** ROCm 脚本（`start_gradio_ui_rocm.bat`、`start_api_server_rocm.bat`）会自动设置 `HSA_OVERRIDE_GFX_VERSION`、`ACESTEP_LM_BACKEND=pt`、`MIOPEN_FIND_MODE=FAST` 及其他 ROCm 相关环境变量。这些脚本使用独立的 `venv_rocm` 虚拟环境，以避免 CUDA/ROCm wheel 冲突。

### Linux

```bash
# 首次使用需添加执行权限
chmod +x start_gradio_ui.sh start_api_server.sh

# 启动 Gradio 网页界面
./start_gradio_ui.sh

# 启动 REST API 服务器
./start_api_server.sh
```

> **注意：** 需要通过系统包管理器安装 Git（`sudo apt install git`、`sudo yum install git`、`sudo pacman -S git`）。

### macOS（Apple Silicon / MLX）

macOS 脚本使用 **MLX 后端**，提供原生 Apple Silicon 加速（M1/M2/M3/M4）。

```bash
# 首次使用需添加执行权限
chmod +x start_gradio_ui_macos.sh start_api_server_macos.sh

# 启动 Gradio 网页界面（MLX 后端）
./start_gradio_ui_macos.sh

# 启动 REST API 服务器（MLX 后端）
./start_api_server_macos.sh
```

macOS 脚本会自动设置 `ACESTEP_LM_BACKEND=mlx` 和 `--backend mlx` 以启用原生 Apple Silicon 加速，在非 arm64 机器上则回退到 PyTorch 后端。

> **注意：** 通过 `xcode-select --install` 或 `brew install git` 安装 Git。

### 脚本功能

- 启动时自动检查更新（默认启用，可配置）
- 自动环境检测（便携 Python 或 uv）
- 自动安装 `uv`（如需要）
- 可配置下载源（HuggingFace/ModelScope）
- 可自定义模型和参数

### 如何修改配置

所有可配置选项均定义为每个脚本顶部的变量。如需自定义，请用文本编辑器打开脚本并修改变量值。

**示例：将界面语言改为中文并使用 1.7B LM 模型**

<table>
<tr><th>Windows (.bat)</th><th>Linux / macOS (.sh)</th></tr>
<tr><td>

在 `start_gradio_ui.bat` 中找到以下行：
```batch
set LANGUAGE=en
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
```
修改为：
```batch
set LANGUAGE=zh
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
```

</td><td>

在 `start_gradio_ui.sh` 中找到以下行：
```bash
LANGUAGE="en"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-0.6B"
```
修改为：
```bash
LANGUAGE="zh"
LM_MODEL_PATH="--lm_model_path acestep-5Hz-lm-1.7B"
```

</td></tr>
</table>

**示例：禁用启动时更新检查**

<table>
<tr><th>Windows (.bat)</th><th>Linux / macOS (.sh)</th></tr>
<tr><td>

```batch
REM set CHECK_UPDATE=true
set CHECK_UPDATE=false
```

</td><td>

```bash
# CHECK_UPDATE="true"
CHECK_UPDATE="false"
```

</td></tr>
</table>

**示例：启用已注释的选项** —— 删除注释前缀（.bat 用 `REM`，.sh 用 `#`）：

<table>
<tr><th>Windows (.bat)</th><th>Linux / macOS (.sh)</th></tr>
<tr><td>

修改前：
```batch
REM set SHARE=--share
```
修改后：
```batch
set SHARE=--share
```

</td><td>

修改前：
```bash
# SHARE="--share"
```
修改后：
```bash
SHARE="--share"
```

</td></tr>
</table>

**常用可配置选项：**

| 选项 | Gradio UI | API 服务器 | 说明 |
|------|:---------:|:----------:|------|
| `LANGUAGE` | ✅ | — | 界面语言：`en`、`zh`、`he`、`ja` |
| `PORT` | ✅ | ✅ | 服务端口（默认：7860 / 8001） |
| `SERVER_NAME` / `HOST` | ✅ | ✅ | 绑定地址（`127.0.0.1` 或 `0.0.0.0`） |
| `CHECK_UPDATE` | ✅ | ✅ | 启动时更新检查（`true` / `false`） |
| `CONFIG_PATH` | ✅ | — | DiT 模型（`acestep-v15-turbo` 等） |
| `LM_MODEL_PATH` | ✅ | ✅ | LM 模型（`acestep-5Hz-lm-0.6B` / `1.7B` / `4B`） |
| `DOWNLOAD_SOURCE` | ✅ | ✅ | 下载源（`huggingface` / `modelscope`） |
| `SHARE` | ✅ | — | 创建公开 Gradio 链接 |
| `INIT_LLM` | ✅ | — | 强制启用/禁用 LLM（`true` / `false` / `auto`） |
| `OFFLOAD_TO_CPU` | ✅ | — | 低显存 GPU 的 CPU 卸载 |

### 更新与维护工具

| 脚本（Windows） | 脚本（Linux/macOS） | 用途 |
|------------------|----------------------|------|
| `check_update.bat` | `check_update.sh` | 从 GitHub 检查并更新 |
| `merge_config.bat` | `merge_config.sh` | 更新后合并备份的配置 |
| `install_uv.bat` | `install_uv.sh` | 安装 uv 包管理器 |
| `quick_test.bat` | `quick_test.sh` | 测试环境配置 |

**更新工作流：**

```bash
# Windows                          # Linux / macOS
check_update.bat                    ./check_update.sh
merge_config.bat                    ./merge_config.sh
```

---

## 🪟 Windows 便携包

为 Windows 用户提供了预装依赖的便携包：

1. 下载并解压：[ACE-Step-1.5.7z](https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z)
2. 包含 `python_embeded`，所有依赖已预装
3. **要求：** CUDA 12.8

### 快速启动脚本

| 脚本 | 说明 |
|------|------|
| `start_gradio_ui.bat` | 启动 Gradio 网页界面 |
| `start_api_server.bat` | 启动 REST API 服务器 |

两个脚本均支持自动环境检测、自动安装 `uv`、可配置下载源、可选 Git 更新检查、可自定义模型和参数。

### 配置

**`start_gradio_ui.bat`：**

```batch
REM 界面语言 (en, zh, he, ja)
set LANGUAGE=zh

REM 下载源 (auto, huggingface, modelscope)
set DOWNLOAD_SOURCE=--download-source modelscope

REM Git 更新检查 (true/false)
set CHECK_UPDATE=true

REM 模型配置
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
```

### 更新与维护

| 脚本 | 用途 |
|------|------|
| `check_update.bat` | 从 GitHub 检查并更新 |
| `merge_config.bat` | 更新后合并备份的配置 |
| `install_uv.bat` | 安装 uv 包管理器 |
| `quick_test.bat` | 测试环境配置 |

---

## AMD / ROCm 显卡

> ⚠️ `uv run acestep` 会安装 CUDA PyTorch wheels，可能覆盖已有的 ROCm 环境。

### 推荐工作流

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate

# 2. 安装 ROCm 兼容的 PyTorch
pip install torch --index-url https://download.pytorch.org/whl/rocm6.0

# 3. 安装 ACE-Step
pip install -e .

# 4. 启动服务
python -m acestep.acestep_v15_pipeline --port 7680
```

### GPU 检测问题排查

如果显示 "No GPU detected, running on CPU"：

1. 运行诊断工具：`python scripts/check_gpu.py`
2. RDNA3 GPU 设置 `HSA_OVERRIDE_GFX_VERSION`：

| GPU | 值 |
|-----|---|
| RX 7900 XT/XTX, RX 9070 XT | `export HSA_OVERRIDE_GFX_VERSION=11.0.0` |
| RX 7800 XT, RX 7700 XT | `export HSA_OVERRIDE_GFX_VERSION=11.0.1` |
| RX 7600 | `export HSA_OVERRIDE_GFX_VERSION=11.0.2` |

3. Windows 上使用 `start_gradio_ui_rocm.bat` / `start_api_server_rocm.bat`
4. 验证 ROCm 安装：`rocm-smi`

### Linux（cachy-os / RDNA4）

详见 [ACE-Step1.5-Rocm-Manual-Linux.md](../en/ACE-Step1.5-Rocm-Manual-Linux.md)

---

## Intel 显卡

| 项目 | 详情 |
|------|------|
| 测试设备 | Windows 笔记本，Ultra 9 285H 集成显卡 |
| 卸载 | 默认禁用 |
| 编译与量化 | 默认启用 |
| LLM 推理 | 支持（已测试 `acestep-5Hz-lm-0.6B`） |
| nanovllm 加速 | Intel GPU 暂不支持 |
| 测试环境 | PyTorch 2.8.0（[Intel Extension for PyTorch](https://pytorch-extension.intel.com/?request=platform)） |

> 注意：生成超过 2 分钟的音频时，LLM 推理速度可能下降。Intel 独立显卡预计可用但尚未测试。

---

## 仅 CPU 模式

ACE-Step 可以在 CPU 上运行**仅推理**，但速度会显著变慢。

- 不推荐在 CPU 上训练（包括 LoRA）。
- 低显存系统可使用 DiT-only 模式（禁用 LLM）。

如果没有 GPU，建议：
- 使用云 GPU 服务
- 仅运行推理工作流
- 使用 `ACESTEP_INIT_LLM=false` 启用 DiT-only 模式

---

## Linux 注意事项

### Python 3.11 预发布版问题

部分 Linux 发行版（包括 Ubuntu）自带 Python 3.11.0rc1 预发布版，可能导致 vLLM 后端出现段错误。

**建议：** 使用稳定版 Python（≥ 3.11.12）。Ubuntu 上可通过 deadsnakes PPA 安装。

如无法升级 Python，使用 PyTorch 后端：

```bash
uv run acestep --backend pt
```

---

## 环境变量 (.env)

```bash
cp .env.example .env   # 复制并编辑
```

### 关键变量

| 变量 | 取值 | 说明 |
|------|------|------|
| `ACESTEP_INIT_LLM` | `auto` / `true` / `false` | LLM 初始化模式 |
| `ACESTEP_CONFIG_PATH` | 模型名称 | DiT 模型路径 |
| `ACESTEP_LM_MODEL_PATH` | 模型名称 | LM 模型路径 |
| `ACESTEP_DOWNLOAD_SOURCE` | `auto` / `huggingface` / `modelscope` | 下载源 |
| `ACESTEP_API_KEY` | 字符串 | API 认证密钥 |

### LLM 初始化 (`ACESTEP_INIT_LLM`)

处理流程：`GPU 检测 → ACESTEP_INIT_LLM 覆盖 → 模型加载`

| 值 | 行为 |
|----|------|
| `auto`（或空） | 使用 GPU 自动检测结果（推荐） |
| `true` / `1` / `yes` | 强制启用 LLM（可能导致 OOM） |
| `false` / `0` / `no` | 强制禁用，纯 DiT 模式 |

**示例 `.env`：**

```bash
# 自动模式（推荐）
ACESTEP_INIT_LLM=auto

# 低显存 GPU 强制启用
ACESTEP_INIT_LLM=true
ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B

# 禁用 LLM 加速生成
ACESTEP_INIT_LLM=false
```

---

## 命令行参数

### Gradio UI (`acestep`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--port` | 7860 | 服务端口 |
| `--server-name` | 127.0.0.1 | 服务地址（使用 `0.0.0.0` 开放网络访问） |
| `--share` | false | 创建公开 Gradio 链接 |
| `--language` | en | 界面语言：`en`、`zh`、`he`、`ja` |
| `--init_service` | false | 启动时自动初始化模型 |
| `--init_llm` | auto | LLM 初始化：`true` / `false` / 省略为自动 |
| `--config_path` | auto | DiT 模型（如 `acestep-v15-turbo`） |
| `--lm_model_path` | auto | LM 模型（如 `acestep-5Hz-lm-1.7B`） |
| `--offload_to_cpu` | auto | CPU 卸载（显存 < 20GB 时自动启用） |
| `--download-source` | auto | 模型源：`auto` / `huggingface` / `modelscope` |
| `--enable-api` | false | 同时启用 REST API 端点 |

**示例：**

```bash
# 公开访问 + 中文界面
uv run acestep --server-name 0.0.0.0 --share --language zh

# 启动时预初始化模型
uv run acestep --init_service true --config_path acestep-v15-turbo

# 使用 ModelScope 下载
uv run acestep --download-source modelscope
```

---

## 📥 模型下载

首次运行时模型会从 [HuggingFace](https://huggingface.co/ACE-Step/Ace-Step1.5) 或 [ModelScope](https://modelscope.cn/organization/ACE-Step) 自动下载。

### CLI 下载

```bash
uv run acestep-download                              # 下载主模型
uv run acestep-download --all                         # 下载所有模型
uv run acestep-download --download-source modelscope  # 从 ModelScope 下载
uv run acestep-download --model acestep-v15-sft       # 指定模型
uv run acestep-download --list                        # 列出所有可用模型
```

### 手动下载 (huggingface-cli)

```bash
# 主模型
huggingface-cli download ACE-Step/Ace-Step1.5 --local-dir ./checkpoints

# 可选模型
huggingface-cli download ACE-Step/acestep-5Hz-lm-0.6B --local-dir ./checkpoints/acestep-5Hz-lm-0.6B
huggingface-cli download ACE-Step/acestep-5Hz-lm-4B --local-dir ./checkpoints/acestep-5Hz-lm-4B
```

### 可用模型

| 模型 | 说明 | HuggingFace |
|------|------|-------------|
| **Ace-Step1.5**（主模型） | 核心：vae, Qwen3-Embedding-0.6B, acestep-v15-turbo, acestep-5Hz-lm-1.7B | [链接](https://huggingface.co/ACE-Step/Ace-Step1.5) |
| acestep-5Hz-lm-0.6B | 轻量 LM（0.6B 参数） | [链接](https://huggingface.co/ACE-Step/acestep-5Hz-lm-0.6B) |
| acestep-5Hz-lm-4B | 大型 LM（4B 参数） | [链接](https://huggingface.co/ACE-Step/acestep-5Hz-lm-4B) |
| acestep-v15-base | 基础 DiT 模型 | [链接](https://huggingface.co/ACE-Step/acestep-v15-base) |
| acestep-v15-sft | SFT DiT 模型 | [链接](https://huggingface.co/ACE-Step/acestep-v15-sft) |
| acestep-v15-turbo-shift1 | Turbo DiT（shift1） | [链接](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift1) |
| acestep-v15-turbo-shift3 | Turbo DiT（shift3） | [链接](https://huggingface.co/ACE-Step/acestep-v15-turbo-shift3) |
| acestep-v15-turbo-continuous | Turbo DiT（continuous shift 1-5） | [链接](https://huggingface.co/ACE-Step/acestep-v15-turbo-continuous) |

---

## 💡 如何选择模型？

ACE-Step 会自动适配你的 GPU 显存。UI 会根据检测到的 GPU 等级预配置所有设置（LM 模型、后端、卸载、量化）：

| GPU 显存 | 推荐 LM 模型 | 后端 | 说明 |
|----------|--------------|------|------|
| **≤6GB** | 无（仅 DiT） | — | 默认禁用 LM；INT8 量化 + 完全 CPU 卸载 |
| **6-8GB** | `acestep-5Hz-lm-0.6B` | `pt` | 轻量 LM，PyTorch 后端 |
| **8-16GB** | `0.6B` / `1.7B` | `vllm` | 8-12GB 用 0.6B，12-16GB 用 1.7B |
| **16-24GB** | `acestep-5Hz-lm-1.7B` | `vllm` | 20GB+ 可用 4B；20GB+ 无需卸载 |
| **≥24GB** | `acestep-5Hz-lm-4B` | `vllm` | 最佳质量，所有模型无需卸载 |

> 📖 详细 GPU 兼容性信息（等级表、时长限制、批量大小、自适应 UI 默认设置、显存优化），请参阅 [GPU 兼容性指南](GPU_COMPATIBILITY.md)。

---

## 开发

```bash
# 添加依赖
uv add package-name
uv add --dev package-name

# 更新所有依赖
uv sync --upgrade
```
