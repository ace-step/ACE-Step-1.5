@echo off
setlocal enabledelayedexpansion
REM ACE-Step REST API Server Launcher - AMD ROCm 7.2
REM For AMD RX 7000/6000 series GPUs on Windows 11
REM IMPORTANT: Requires Python 3.12 (AMD ROCm 7.2 only provides Python 3.12 wheels)
REM Requires: ROCm PyTorch from repo.radeon.com

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
REM set LM_MODEL_PATH=--lm-model-path acestep-5Hz-lm-0.6B

REM Update check on startup (set to false to disable)
set CHECK_UPDATE=true
REM set CHECK_UPDATE=false

REM Skip model loading at startup (models will be lazy-loaded on first request)
REM Set to true to start server quickly without loading models
REM set ACESTEP_NO_INIT=false
REM set ACESTEP_NO_INIT=true

REM ==================== Venv Configuration ====================
REM Path to the ROCm virtual environment (relative to this script)
set VENV_DIR=%~dp0venv_rocm

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
echo   ACE-Step 1.5 API - AMD ROCm 7.2 Edition
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
