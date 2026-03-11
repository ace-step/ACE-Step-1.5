@echo off
setlocal enabledelayedexpansion
REM ACE-Step REST API Server Launcher - Intel XPU
REM For Intel Arc GPUs (A770, A750, A580, A380) and integrated graphics
REM Requires: Python 3.11, PyTorch XPU nightly from download.pytorch.org/whl/xpu
REM IMPORTANT: Uses torch.xpu backend with SYCL/Level Zero acceleration

REM ==================== XPU Configuration ====================
REM XPU performance optimization (from verified working setup)
set SYCL_CACHE_PERSISTENT=1
set SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1
set PYTORCH_DEVICE=xpu

REM Disable torch.compile (not fully supported on XPU yet)
set TORCH_COMPILE_BACKEND=eager

REM HuggingFace tokenizer parallelism
set TOKENIZERS_PARALLELISM=false

REM Force torchaudio to use ffmpeg backend (torchcodec not available on XPU)
set TORCHAUDIO_USE_BACKEND=ffmpeg

REM ==================== Server Configuration ====================
set HOST=127.0.0.1
REM set HOST=0.0.0.0
set PORT=8001

REM ==================== Model Configuration ====================
REM API key for authentication (optional)
REM set API_KEY=--api-key sk-your-secret-key

REM Download source: auto, huggingface, modelscope
set DOWNLOAD_SOURCE=

REM LLM (Language Model) initialization settings
REM By default, LLM is auto-enabled/disabled based on GPU VRAM:
REM   - <=6GB VRAM: LLM disabled (DiT-only mode)
REM   - >6GB VRAM: LLM enabled
REM Values: auto (default), true (force enable), false (force disable)
set ACESTEP_INIT_LLM=auto
REM set ACESTEP_INIT_LLM=true
REM set ACESTEP_INIT_LLM=false

REM LM model path (optional, only used when LLM is enabled)
REM Available models: acestep-5Hz-lm-0.6B, acestep-5Hz-lm-1.7B, acestep-5Hz-lm-4B
REM set LM_MODEL_PATH=--lm-model-path acestep-5Hz-lm-4B

REM Update check on startup (set to false to disable)
set CHECK_UPDATE=true
REM set CHECK_UPDATE=false

REM Skip model loading at startup (models will be lazy-loaded on first request)
REM Set to true to start server quickly without loading models
REM set ACESTEP_NO_INIT=false
REM set ACESTEP_NO_INIT=true

REM ==================== Venv Configuration ====================
REM Path to the XPU virtual environment (relative to this script)
set VENV_DIR=%~dp0venv_xpu

REM ==================== Launch ====================

REM ==================== Startup Update Check ====================
if /i not "%CHECK_UPDATE%"=="true" goto :SkipUpdateCheck

REM Find git: try PortableGit first, then system git
set "UPDATE_GIT_CMD="
if exist "%~dp0PortableGit\bin\git.exe" (
    set "UPDATE_GIT_CMD=%~dp0PortableGit\bin\git.exe"
) else (
    where git >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        for /f "tokens=*" %%i in ('where git 2^>nul') do (
            if not defined UPDATE_GIT_CMD set "UPDATE_GIT_CMD=%%i"
        )
    )
)
if not defined UPDATE_GIT_CMD goto :SkipUpdateCheck

cd /d "%~dp0"
"!UPDATE_GIT_CMD!" rev-parse --git-dir >nul 2>&1
if !ERRORLEVEL! NEQ 0 goto :SkipUpdateCheck

echo [Update] Checking for updates...

for /f "tokens=*" %%i in ('"!UPDATE_GIT_CMD!" rev-parse --abbrev-ref HEAD 2^>nul') do set UPDATE_BRANCH=%%i
if "!UPDATE_BRANCH!"=="" set UPDATE_BRANCH=main
for /f "tokens=*" %%i in ('"!UPDATE_GIT_CMD!" rev-parse --short HEAD 2^>nul') do set UPDATE_LOCAL=%%i

"!UPDATE_GIT_CMD!" fetch origin --quiet 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [Update] Network unreachable, skipping.
    echo.
    goto :SkipUpdateCheck
)

for /f "tokens=*" %%i in ('"!UPDATE_GIT_CMD!" rev-parse --short origin/!UPDATE_BRANCH! 2^>nul') do set UPDATE_REMOTE=%%i

if "!UPDATE_REMOTE!"=="" goto :SkipUpdateCheck
if "!UPDATE_LOCAL!"=="!UPDATE_REMOTE!" (
    echo [Update] Already up to date ^(!UPDATE_LOCAL!^).
    echo.
    goto :SkipUpdateCheck
)

echo.
echo ========================================
echo   Update available!
echo ========================================
echo   Current: !UPDATE_LOCAL!  -^>  Latest: !UPDATE_REMOTE!
echo.
echo   Recent changes:
"!UPDATE_GIT_CMD!" --no-pager log --oneline HEAD..origin/!UPDATE_BRANCH! 2>nul
echo.

set /p UPDATE_NOW="Update now before starting? (Y/N): "
if /i "!UPDATE_NOW!"=="Y" (
    if exist "%~dp0check_update.bat" (
        call "%~dp0check_update.bat"
    ) else (
        echo Pulling latest changes...
        "!UPDATE_GIT_CMD!" pull --ff-only origin !UPDATE_BRANCH! 2>nul
        if !ERRORLEVEL! NEQ 0 (
            echo [Update] Update failed. Please update manually.
        )
    )
) else (
    echo [Update] Skipped. Run check_update.bat to update later.
)
echo.

:SkipUpdateCheck

echo ============================================
echo   ACE-Step 1.5 API - Intel XPU Edition
echo ============================================
echo.

REM Activate venv if it exists
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Activating XPU virtual environment: %VENV_DIR%
    call "%VENV_DIR%\Scripts\activate.bat"
) else (
    echo ========================================
    echo  ERROR: venv_xpu not found!
    echo ========================================
    echo.
    echo Please create the XPU virtual environment first:
    echo.
    echo   1. Run: python -m venv venv_xpu
    echo   2. Run: venv_xpu\Scripts\activate
    echo   3. Run: pip install -r requirements-xpu.txt
    echo.
    echo Or use the setup script ^(if available^)
    echo   setup_xpu.bat
    echo.
    pause
    exit /b 1
)
echo.

REM Verify XPU PyTorch is installed
python -c "import torch; assert hasattr(torch, 'xpu') and torch.xpu.is_available(), 'Intel XPU not detected'; print(f'XPU: Intel Arc GPU detected'); print(f'PyTorch XPU version: {torch.__version__}')" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ========================================
    echo  ERROR: Intel XPU PyTorch not detected!
    echo ========================================
    echo.
    echo Please install PyTorch with XPU support. See requirements-xpu.txt for instructions.
    echo.
    echo Quick setup:
    echo   1. Activate venv: venv_xpu\Scripts\activate
    echo   2. Install: pip install --upgrade pip
    echo   3. Install XPyTorch: pip install -r requirements-xpu.txt
    echo.
    pause
    exit /b 1
)
echo.

echo Starting ACE-Step REST API Server...
echo API will be available at: http://%HOST%:%PORT%
echo API Documentation: http://%HOST%:%PORT%/docs
echo.

REM Build command with optional parameters
set "CMD=--host %HOST% --port %PORT%"
if not "%API_KEY%"=="" set "CMD=!CMD! %API_KEY%"
if not "%DOWNLOAD_SOURCE%"=="" set "CMD=!CMD! %DOWNLOAD_SOURCE%"
if not "%LM_MODEL_PATH%"=="" set "CMD=!CMD! %LM_MODEL_PATH%"

python -u acestep\api_server.py !CMD!

pause
endlocal
