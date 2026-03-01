@echo off
setlocal enabledelayedexpansion
REM ACE-Step Gradio Web UI Launcher - Intel XPU (Manual Mode)
REM For Intel Arc GPUs (A770, A750, A580, A380) and integrated graphics
REM Requires: Python 3.11, PyTorch XPU nightly from download.pytorch.org/whl/xpu
REM IMPORTANT: Uses torch.xpu backend with SYCL/Level Zero acceleration

REM ==================== Manual Startup Configuration ====================
REM Run interactive prompts for manual settings
call :LoadManual

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
REM Default values

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
REM Values set by LoadManual function
REM CONFIG_PATH and LM_MODEL_PATH are set based on user input

REM CPU offload: set by user in manual mode
REM set OFFLOAD_TO_CPU=--offload_to_cpu true

REM LLM initialization: set by user in manual mode
REM set INIT_LLM=--init_llm auto

REM Download source: auto, huggingface, modelscope
if not defined DOWNLOAD_SOURCE set DOWNLOAD_SOURCE=

REM Auto-initialize models on startup
if not defined INIT_SERVICE set INIT_SERVICE=--init_service true

REM API settings
REM set ENABLE_API=--enable-api
REM set API_KEY=--api-key sk-your-secret-key

REM Authentication
REM set AUTH_USERNAME=--auth-username admin
REM set AUTH_PASSWORD=--auth-password password

REM Update check on startup
set CHECK_UPDATE=true
REM set CHECK_UPDATE=false

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
echo   ACE-Step 1.5 - Intel XPU Edition
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
    pause
    exit /b 1
)
echo.

echo Starting ACE-Step Gradio Web UI...
echo Server will be available at: http://%SERVER_NAME%:%PORT%
if defined CONFIG_PATH_DISPLAY echo DiT Model: %CONFIG_PATH_DISPLAY%
if defined LM_MODEL_PATH_DISPLAY echo LM Model: %LM_MODEL_PATH_DISPLAY%
if defined OFFLOAD_DISPLAY echo CPU Offload: %OFFLOAD_DISPLAY%
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
if not "%ENABLE_API%"=="" set "CMD=!CMD! %ENABLE_API%"
if not "%API_KEY%"=="" set "CMD=!CMD! %API_KEY%"
if not "%AUTH_USERNAME%"=="" set "CMD=!CMD! %AUTH_USERNAME%"
if not "%AUTH_PASSWORD%"=="" set "CMD=!CMD! %AUTH_PASSWORD%"

python -u acestep\acestep_v15_pipeline.py !CMD!

pause
endlocal
goto :eof

REM ==================== Helper Functions ====================

:LoadManual
REM Interactive prompts for manual configuration
color 0B
echo.
echo ======================================================
echo             ACE-Step XPU Manual Launch Mode
echo ======================================================
echo.

REM Check if venv exists first
if not exist "%~dp0venv_xpu\Scripts\activate.bat" (
    echo WARNING: venv_xpu not found!
    echo.
    echo Please create the XPU environment first:
    echo   1. Run: python -m venv venv_xpu
    echo   2. Run: venv_xpu\Scripts\activate
    echo   3. Run: pip install -r requirements-xpu.txt
    echo.
    pause
    exit /b 1
)

:manual_choice_ask
    set /p MANUAL_CHOICE="Continue with manual configuration? (Y/N): "
    if /i "%MANUAL_CHOICE%"=="Y" (
        goto manual_choice_done
    )
    if /i "%MANUAL_CHOICE%"=="N" (
        echo.
        echo Use automatic configuration instead.
        echo Please run: start_gradio_ui_xpu.bat
        echo.
        color 07
        pause
        exit /b 0
    )
    echo Invalid input. Please enter Y or N.
    goto manual_choice_ask
:manual_choice_done

echo.
echo -------------------- Update Settings --------------------
:update_choice_ask
    set /p UPDATE_CHOICE="Check for updates before launch? (Y/N): "
    if /i "%UPDATE_CHOICE%"=="Y" (
        set CHECK_UPDATE=true
        goto update_choice_done
    )
    if /i "%UPDATE_CHOICE%"=="N" (
        set CHECK_UPDATE=false
        goto update_choice_done
    )
    echo Invalid input. Please enter Y or N.
    goto update_choice_ask
:update_choice_done

echo.
echo -------------------- Select DiT Model --------------------
echo Scanning available models...
echo.

REM Scan checkpoints directory for available DiT models
set MODEL_COUNT=0
if exist "%~dp0checkpoints" (
    for /d %%D in ("%~dp0checkpoints\acestep-v15-*") do (
        set /a MODEL_COUNT+=1
    )
)

if %MODEL_COUNT% EQU 0 (
    echo No acestep-v15 models found in checkpoints folder.
    echo Using default: acestep-v15-turbo
    set CONFIG_PATH=--config_path acestep-v15-turbo
    set CONFIG_PATH_DISPLAY=acestep-v15-turbo ^(default^)
) else (
    echo Available DiT models:
    echo 1^) acestep-v15-turbo  (Recommended - Fast generation^)
    echo 2^) acestep-v15-base    (Base model^)
    echo 3^) acestep-v15-sft     (Supervised fine-tuned^)
    echo 4^) acestep-v15-turbo-rl  (RL optimized^)
    echo.
    :dit_choice_ask
        set /p DIT_CHOICE="Enter selection (1-4): "
        if "%DIT_CHOICE%"=="1" (
            set CONFIG_PATH=--config_path acestep-v15-turbo
            set CONFIG_PATH_DISPLAY=acestep-v15-turbo
            goto dit_choice_done
        )
        if "%DIT_CHOICE%"=="2" (
            set CONFIG_PATH=--config_path acestep-v15-base
            set CONFIG_PATH_DISPLAY=acestep-v15-base
            goto dit_choice_done
        )
        if "%DIT_CHOICE%"=="3" (
            set CONFIG_PATH=--config_path acestep-v15-sft
            set CONFIG_PATH_DISPLAY=acestep-v15-sft
            goto dit_choice_done
        )
        if "%DIT_CHOICE%"=="4" (
            set CONFIG_PATH=--config_path acestep-v15-turbo-rl
            set CONFIG_PATH_DISPLAY=acestep-v15-turbo-rl
            goto dit_choice_done
        )
        echo Invalid input. Please enter a number between 1 and 4.
        goto dit_choice_ask
    :dit_choice_done
)

echo.
echo -------------------- Select LM Model --------------------
echo 1^) acestep-5Hz-lm-0.6B  (Recommended - Fast, low VRAM^)
echo 2^) acestep-5Hz-lm-1.7B  (Balanced^)
echo 3^) acestep-5Hz-lm-4B    (Best quality - requires CPU offload^)
echo 4^) Launch without LM Model ^(DiT-only mode^)
echo.
:lm_choice_ask
    set /p LM_CHOICE="Enter selection (1-4): "
    if "%LM_CHOICE%"=="1" (
        set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
        set LM_MODEL_PATH_DISPLAY=acestep-5Hz-lm-0.6B
        set INIT_LLM=--init_llm true
        goto lm_choice_done
    )
    if "%LM_CHOICE%"=="2" (
        set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-1.7B
        set LM_MODEL_PATH_DISPLAY=acestep-5Hz-lm-1.7B
        set INIT_LLM=--init_llm true
        goto lm_choice_done
    )
    if "%LM_CHOICE%"=="3" (
        set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-4B
        set LM_MODEL_PATH_DISPLAY=acestep-5Hz-lm-4B
        set INIT_LLM=--init_llm true
        goto lm_choice_done
    )
    if "%LM_CHOICE%"=="4" (
        set LM_MODEL_PATH=
        set LM_MODEL_PATH_DISPLAY=None ^(DiT-only mode^)
        set INIT_LLM=--init_llm false
        goto lm_choice_done
    )
    echo Invalid input. Please enter a number between 1 and 4.
    goto lm_choice_ask
:lm_choice_done

echo.
echo -------------------- CPU Offload Option --------------------
if "%LM_CHOICE%"=="3" (
    echo NOTE: 4B LM model requires CPU offload on most GPUs
    set OFFLOAD_TO_CPU=--offload_to_cpu true
    set OFFLOAD_DISPLAY=Enabled ^(required for 4B LM^)
    goto offload_choice_skip
)

:offload_choice_ask
    set /p OFFLOAD_CHOICE="Enable CPU Offload? (Y/N): "
    if /i "%OFFLOAD_CHOICE%"=="Y" (
        set OFFLOAD_TO_CPU=--offload_to_cpu true
        set OFFLOAD_DISPLAY=Enabled
        goto offload_choice_done
    )
    if /i "%OFFLOAD_CHOICE%"=="N" (
        set OFFLOAD_TO_CPU=--offload_to_cpu false
        set OFFLOAD_DISPLAY=Disabled
        goto offload_choice_done
    )
    echo Invalid input. Please enter Y or N.
    goto offload_choice_ask
:offload_choice_done
:offload_choice_skip

color 07
echo.
echo ======================================================
echo Configuration Summary
echo ======================================================
echo DiT Model:    %CONFIG_PATH_DISPLAY%
echo LM Model:     %LM_MODEL_PATH_DISPLAY%
echo CPU Offload:  %OFFLOAD_DISPLAY%
echo Update Check: %CHECK_UPDATE%
echo.
echo Starting ACE-Step with these settings...
echo.
exit /b 0
