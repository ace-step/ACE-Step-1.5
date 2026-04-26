@echo off
setlocal enabledelayedexpansion
REM ACE-Step Gradio Web UI Launcher - AMD ROCm 7.2
REM For AMD RX 7000/6000 series GPUs on Windows 11
REM IMPORTANT: Requires Python 3.12 (AMD ROCm 7.2 only provides Python 3.12 wheels)
REM Requires: ROCm PyTorch from repo.radeon.com

REM ==================== Load .env Configuration ====================
REM Load settings from .env file if it exists
call :LoadEnvFile

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
REM Default values (used if not set in .env file)
REM You can override these by uncommenting and modifying the lines below
REM or by creating a .env file (recommended to survive updates)

if not defined PORT set PORT=7860
if not defined SERVER_NAME set SERVER_NAME=127.0.0.1
REM set SERVER_NAME=0.0.0.0
REM set SHARE=--share

REM UI language: en, zh, ja
if not defined LANGUAGE set LANGUAGE=en

REM Batch size: default batch size for generation (1 to GPU-dependent max)
REM When not specified, defaults to min(2, GPU_max)
REM set BATCH_SIZE=--batch_size 4

REM ==================== Model Configuration ====================
if not defined CONFIG_PATH set CONFIG_PATH=--config_path acestep-v15-turbo
if not defined LM_MODEL_PATH set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-4B

REM CPU offload: required for 4B LM on GPUs with <=20GB VRAM
REM Models shuttle between CPU/GPU as needed (DiT stays on GPU, LM/VAE/text_encoder move on demand)
REM Adds ~8-10s overhead per generation but prevents VRAM oversubscription
REM Disable if using 1.7B/0.6B LM or if your GPU has >=24GB VRAM
if not defined OFFLOAD_TO_CPU set OFFLOAD_TO_CPU=--offload_to_cpu true

REM LLM initialization: auto (default), true, false
REM set INIT_LLM=--init_llm auto

REM Download source: auto, huggingface, modelscope
if not defined DOWNLOAD_SOURCE set DOWNLOAD_SOURCE=

REM Auto-initialize models on startup
if not defined INIT_SERVICE set INIT_SERVICE=--init_service true

REM LM backend: pt (PyTorch) recommended for ROCm
set BACKEND=--backend pt

REM API settings
REM set ENABLE_API=--enable-api
REM set API_KEY=--api-key sk-your-secret-key

REM Authentication
REM set AUTH_USERNAME=--auth-username admin
REM set AUTH_PASSWORD=--auth-password password

REM Update check on startup (set to false to disable)
set CHECK_UPDATE=true
REM set CHECK_UPDATE=false

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
if not "%BATCH_SIZE%"=="" set "CMD=!CMD! %BATCH_SIZE%"
if not "%BACKEND%"=="" set "CMD=!CMD! %BACKEND%"
if not "%ENABLE_API%"=="" set "CMD=!CMD! %ENABLE_API%"
if not "%API_KEY%"=="" set "CMD=!CMD! %API_KEY%"
if not "%AUTH_USERNAME%"=="" set "CMD=!CMD! %AUTH_USERNAME%"
if not "%AUTH_PASSWORD%"=="" set "CMD=!CMD! %AUTH_PASSWORD%"

python -u acestep\acestep_v15_pipeline.py !CMD!

pause
endlocal
goto :eof

REM ==================== Helper Functions ====================

:LoadEnvFile
REM Load environment variables from .env file if it exists
set "ENV_FILE=%~dp0.env"
if not exist "%ENV_FILE%" (
    exit /b 0
)

echo [Config] Loading configuration from .env file...
for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    set "line=%%a"
    set "value=%%b"
    
    REM Skip empty lines and comments
    if not "!line!"=="" (
        set "first_char=!line:~0,1!"
        if not "!first_char!"=="#" (
            REM Remove leading/trailing spaces from key
            for /f "tokens=* delims= " %%x in ("!line!") do set "key=%%x"
            
            REM Map .env variable names to batch script variables
            if /i "!key!"=="ACESTEP_CONFIG_PATH" (
                if not "!value!"=="" set "CONFIG_PATH=--config_path !value!"
            )
            if /i "!key!"=="ACESTEP_LM_MODEL_PATH" (
                if not "!value!"=="" set "LM_MODEL_PATH=--lm_model_path !value!"
            )
            if /i "!key!"=="ACESTEP_INIT_LLM" (
                if not "!value!"=="" (
                    if not "!value!"=="auto" set "INIT_LLM=--init_llm !value!"
                )
            )
            if /i "!key!"=="ACESTEP_DOWNLOAD_SOURCE" (
                if not "!value!"=="" (
                    if not "!value!"=="auto" set "DOWNLOAD_SOURCE=--download-source !value!"
                )
            )
            if /i "!key!"=="ACESTEP_API_KEY" (
                if not "!value!"=="" set "API_KEY=--api-key !value!"
            )
            if /i "!key!"=="PORT" (
                if not "!value!"=="" set "PORT=!value!"
            )
            if /i "!key!"=="SERVER_NAME" (
                if not "!value!"=="" set "SERVER_NAME=!value!"
            )
            if /i "!key!"=="LANGUAGE" (
                if not "!value!"=="" set "LANGUAGE=!value!"
            )
            if /i "!key!"=="ACESTEP_BATCH_SIZE" (
                if not "!value!"=="" set "BATCH_SIZE=--batch_size !value!"
            )
        )
    )
)
echo [Config] Configuration loaded from .env
exit /b 0
