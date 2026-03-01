# ACE-Step 1.5 - Intel XPU Setup Guide

Quick start guide for running ACE-Step on Intel Arc GPUs and integrated graphics.

## 🎯 What You Need

- **Intel Arc GPU**: A770, A750, A580, A380, or Intel integrated graphics
- **Python 3.11**: Download from [python.org](https://www.python.org/downloads/release/python-3119/)
- **Latest Intel GPU drivers**: Install from Intel's website
- **Internet connection**: For first-time setup
- **Disk space**: ~5-10 GB for dependencies

## 🚀 Quick Start

### Option 1: Automatic Setup (Recommended)

1. **Run the setup script**:
   ```bat
   setup_xpu.bat
   ```

2. **Wait for installation** (takes a few minutes on first run)

3. **Launch the Gradio UI**:
   ```bat
   start_gradio_ui_xpu.bat
   ```

4. **Open your browser**: http://127.0.0.1:7860

### Option 2: Manual Setup

1. **Create virtual environment**:
   ```bat
   python -m venv venv_xpu
   ```

2. **Activate it**:
   ```bat
   call venv_xpu\Scripts\activate
   ```

3. **Upgrade pip**:
   ```bat
   python -m pip install --upgrade pip
   ```

4. **Install XPU dependencies**:
   ```bat
   pip install -r requirements-xpu.txt
   ```

5. **Launch**:
   ```bat
   start_gradio_ui_xpu.bat
   ```

## 📁 Model Configuration

Models should be placed in the `checkpoints` folder. If you already have models from a previous installation, they will be automatically detected.

### Default Models
- **DiT Model**: `acestep-v15-turbo` (fast generation)
- **LM Model**: `acestep-5Hz-lm-4B` (best quality, uses CPU offload)

### Launch Options

1. **Automatic** (uses defaults):
   ```bat
   start_gradio_ui_xpu.bat
   ```

2. **Manual** (choose models interactively):
   ```bat
   start_gradio_ui_xpu_manual.bat
   ```

3. **API Server** (REST API access):
   ```bat
   start_api_server_xpu.bat
   ```

## ⚙️ XPU Environment Variables

The bat files automatically set these performance optimizations:

```bat
set SYCL_CACHE_PERSISTENT=1
set SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1
set PYTORCH_DEVICE=xpu
set TORCH_COMPILE_BACKEND=eager
```

These settings improve XPU performance and are based on verified working configurations.

## 🔧 Configuration (.env file)

Create a `.env` file in the root directory to customize settings:

```env
# Gradio UI Settings
PORT=7860
SERVER_NAME=127.0.0.1
LANGUAGE=en

# Model Settings
ACESTEP_CONFIG_PATH=acestep-v15-turbo
ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-4B
ACESTEP_OFFLOAD_TO_CPU=true

# API Settings
ACESTEP_API_KEY=your-secret-key
```

## 🛠️ Troubleshooting

### "venv_xpu not found"
Run `setup_xpu.bat` to create the virtual environment.

### "Intel XPU not detected"
1. Check that your GPU drivers are up to date
2. Verify PyTorch XPU installation:
   ```bat
   call venv_xpu\Scripts\activate
   python -c "import torch; print(torch.xpu.is_available())"
   ```

### "torch.xpu.is_available() returns False"
Reinstall PyTorch XPU:
```bat
call venv_xpu\Scripts\activate
pip uninstall torch torchaudio torchvision
pip install --pre torch torchaudio torchvision --index-url https://download.pytorch.org/whl/nightly/xpu
```

### Out of memory errors
1. Use a smaller LM model (0.6B or 1.7B instead of 4B)
2. Enable CPU offload in the UI
3. Close other GPU-intensive applications

### Audio loading issues
- MP3/Opus/AAC files use torchaudio with ffmpeg backend (bundled)
- FLAC/WAV files use soundfile (fastest)
- If issues occur, try converting to WAV format

## 📊 Launch Scripts

| Script | Description |
|--------|-------------|
| `setup_xpu.bat` | One-command environment setup |
| `start_gradio_ui_xpu.bat` | Launch Gradio web UI (automatic) |
| `start_gradio_ui_xpu_manual.bat` | Launch Gradio UI with model selection |
| `start_api_server_xpu.bat` | Launch REST API server |

## 🎵 Audio Support

- ✅ **WAV/FLAC**: Native support via soundfile (fastest)
- ✅ **MP3**: Supported via torchaudio with ffmpeg backend
- ✅ **Opus/AAC**: Supported via torchaudio

No additional codec installation needed!

## 📝 Notes

1. **First launch** takes longer as models are initialized
2. **CPU offload** is recommended for 4B LM on GPUs with <=16GB VRAM
3. **torch.compile** is disabled (not fully supported on XPU yet)
4. **Python 3.11** is recommended for best compatibility

## 🆘 Need Help?

- Check the main documentation: `README.md`
- Verify XPU installation: Run verification commands above
- Update check: Bat files automatically check for updates on startup

## 🎉 You're Ready!

Once setup is complete, simply run:
```bat
start_gradio_ui_xpu.bat
```

And start creating music with ACE-Step on your Intel GPU!
