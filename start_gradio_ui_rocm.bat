@echo off
setlocal enabledelayedexpansion
REM ACE-Step Gradio Web UI Launcher - AMD ROCm 7.2
REM For AMD RX 7000/6000 series GPUs on Windows 11
REM Requires: Python 3.12, ROCm PyTorch from repo.radeon.com

REM ==================== ROCm Configuration ====================
REM Force PyTorch LM backend (bypasses nano-vllm flash_attn dependency)
set ACESTEP_LM_BACKEND=pt

REM RDNA3 GPU architecture override (RX 7900 XT/XTX, RX 7800 XT, etc.)
REM Change to 11.0.1 for gfx1101 (RX 7700 XT, RX 7800 XT)
REM Change to 11.0.2 for gfx1102 (RX 7600)
set HSA_OVERRIDE_GFX_VERSION=11.0.0

REM Disable torch.compile Triton backend (not available on ROCm Windows)
set TORCH_COMPILE_BACKEND=eager

REM MIOpen: use fast heuristic kernel selection instead of exhaustive benchmarking
REM Without this, first-run VAE decode hangs for minutes on each conv layer
set MIOPEN_FIND_MODE=FAST

REM HuggingFace tokenizer parallelism
set TOKENIZERS_PARALLELISM=false

REM ==================== Server Configuration ====================
set PORT=7860
set SERVER_NAME=127.0.0.1
REM set SERVER_NAME=0.0.0.0
REM set SHARE=--share

REM UI language: en, zh, ja
set LANGUAGE=en

REM ==================== Model Configuration ====================
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-4B

REM CPU offload: required for 4B LM on GPUs with <=20GB VRAM
REM Models shuttle between CPU/GPU as needed (DiT stays on GPU, LM/VAE/text_encoder move on demand)
REM Adds ~8-10s overhead per generation but prevents VRAM oversubscription
REM Disable if using 1.7B/0.6B LM or if your GPU has >=24GB VRAM
set OFFLOAD_TO_CPU=--offload_to_cpu true

REM LLM initialization: auto (default), true, false
REM set INIT_LLM=--init_llm auto

REM Download source: auto, huggingface, modelscope
set DOWNLOAD_SOURCE=

REM Auto-initialize models on startup
set INIT_SERVICE=--init_service true

REM LM backend: pt (PyTorch) recommended for ROCm
set BACKEND=--backend pt

REM API settings
REM set ENABLE_API=--enable-api
REM set API_KEY=--api-key sk-your-secret-key

REM Authentication
REM set AUTH_USERNAME=--auth-username admin
REM set AUTH_PASSWORD=--auth-password password

REM ==================== Venv Configuration ====================
REM Path to the ROCm virtual environment (relative to this script)
set VENV_DIR=%~dp0venv_rocm

REM ==================== Launch ====================

echo ============================================
echo   ACE-Step 1.5 - AMD ROCm 7.2 Edition
echo ============================================
echo.

REM Activate venv if it exists
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Activating virtual environment: %VENV_DIR%
    call "%VENV_DIR%\Scripts\activate.bat"
) else (
    echo WARNING: venv_rocm not found at %VENV_DIR%
    echo Using system Python. See requirements-rocm.txt for setup instructions.
)
echo.

REM Verify ROCm PyTorch is installed
python -c "import torch; assert torch.cuda.is_available(), 'No GPU detected'; print(f'GPU: {torch.cuda.get_device_name(0)}'); hip=getattr(torch.version,'hip',None); print(f'HIP: {hip}' if hip else 'WARNING: Not a ROCm build')" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ========================================
    echo  ERROR: ROCm PyTorch not detected!
    echo ========================================
    echo.
    echo Please install ROCm PyTorch first. See requirements-rocm.txt for instructions.
    echo.
    pause
    exit /b 1
)
echo.

echo Starting ACE-Step Gradio Web UI...
echo Server will be available at: http://%SERVER_NAME%:%PORT%
echo.

REM Build command with optional parameters
set "CMD=--port %PORT% --server-name %SERVER_NAME% --language %LANGUAGE%"
if not "%SHARE%"=="" set "CMD=!CMD! %SHARE%"
if not "%CONFIG_PATH%"=="" set "CMD=!CMD! %CONFIG_PATH%"
if not "%LM_MODEL_PATH%"=="" set "CMD=!CMD! %LM_MODEL_PATH%"
if not "%OFFLOAD_TO_CPU%"=="" set "CMD=!CMD! %OFFLOAD_TO_CPU%"
if not "%INIT_LLM%"=="" set "CMD=!CMD! %INIT_LLM%"
if not "%DOWNLOAD_SOURCE%"=="" set "CMD=!CMD! %DOWNLOAD_SOURCE%"
if not "%INIT_SERVICE%"=="" set "CMD=!CMD! %INIT_SERVICE%"
if not "%BACKEND%"=="" set "CMD=!CMD! %BACKEND%"
if not "%ENABLE_API%"=="" set "CMD=!CMD! %ENABLE_API%"
if not "%API_KEY%"=="" set "CMD=!CMD! %API_KEY%"
if not "%AUTH_USERNAME%"=="" set "CMD=!CMD! %AUTH_USERNAME%"
if not "%AUTH_PASSWORD%"=="" set "CMD=!CMD! %AUTH_PASSWORD%"

python -u acestep\acestep_v15_pipeline.py !CMD!

pause
endlocal
