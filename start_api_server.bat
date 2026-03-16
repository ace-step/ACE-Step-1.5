@echo off
setlocal enabledelayedexpansion
REM ACE-Step REST API Server Launcher
REM This script launches the REST API server for ACE-Step

REM ==================== Configuration ====================
REM Uncomment and modify the parameters below as needed

REM Server settings
set HOST=127.0.0.1
REM set HOST=0.0.0.0
set PORT=8001

REM API key for authentication (optional)
REM set API_KEY=--api-key sk-your-secret-key

REM Download source settings
REM Preferred download source: auto (default), huggingface, or modelscope
REM set DOWNLOAD_SOURCE=--download-source modelscope
REM set DOWNLOAD_SOURCE=--download-source huggingface
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

echo Starting ACE-Step REST API Server...
echo API will be available at: http://%HOST%:%PORT%
echo API Documentation: http://%HOST%:%PORT%/docs
echo.

REM Auto-detect Python environment
if exist "%~dp0python_embedded\python.exe" (
    echo [Environment] Using embedded Python...

    REM Build command with optional parameters
    set "PYTHON_EXE=%~dp0python_embedded\python.exe"
    set "SCRIPT_PATH=%~dp0acestep\api_server.py"
    set "CMD=--host %HOST% --port %PORT%"
    if not "%API_KEY%"=="" set "CMD=!CMD! %API_KEY%"
    if not "%DOWNLOAD_SOURCE%"=="" set "CMD=!CMD! %DOWNLOAD_SOURCE%"
    if not "%LM_MODEL_PATH%"=="" set "CMD=!CMD! %LM_MODEL_PATH%"

    "!PYTHON_EXE!" "!SCRIPT_PATH!" !CMD!
) else (
    echo [Environment] Embedded Python not found, checking for uv...

    REM Check if uv is installed
    where uv >nul 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo ========================================
        echo uv package manager not found!
        echo ========================================
        echo.
        echo ACE-Step requires either:
        echo   1. python_embedded directory ^(portable package^)
        echo   2. uv package manager
        echo.
        echo Would you like to install uv now? ^(Recommended^)
        echo.
        set /p INSTALL_UV="Install uv? (Y/N): "

        if /i "!INSTALL_UV!"=="Y" (
            echo.
            REM Call install_uv.bat in silent mode
            call "%~dp0install_uv.bat" --silent
            set INSTALL_RESULT=!ERRORLEVEL!

            if !INSTALL_RESULT! EQU 0 (
                echo.
                echo ========================================
                echo uv installed successfully!
                echo ========================================
                echo.

                REM Refresh PATH to include uv
                if exist "%USERPROFILE%\.local\bin\uv.exe" (
                    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
                )
                if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" (
                    set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
                )

                REM Verify uv is available
                where uv >nul 2>&1
                if !ERRORLEVEL! EQU 0 (
                    echo uv is now available!
                    uv --version
                    echo.
                    goto :RunWithUv
                ) else (
                    REM Try direct paths
                    if exist "%USERPROFILE%\.local\bin\uv.exe" (
                        set "PATH=%USERPROFILE%\.local\bin;%PATH%"
                        goto :RunWithUv
                    )
                    if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" (
                        set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
                        goto :RunWithUv
                    )

                    echo.
                    echo uv installed but not in PATH yet.
                    echo Please restart your terminal or run:
                    echo   %USERPROFILE%\.local\bin\uv.exe run acestep-api
                    echo.
                    pause
                    exit /b 1
                )
            ) else (
                echo.
                echo ========================================
                echo Installation failed!
                echo ========================================
                echo.
                echo Please install uv manually:
                echo   1. Using PowerShell: irm https://astral.sh/uv/install.ps1 ^| iex
                echo   2. Using winget: winget install --id=astral-sh.uv -e
                echo   3. Download portable package: https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z
                echo.
                pause
                exit /b 1
            )
        ) else (
            echo.
            echo Installation cancelled.
            echo.
            echo To use ACE-Step, please either:
            echo   1. Install uv: winget install --id=astral-sh.uv -e
            echo   2. Download portable package: https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z
            echo.
            pause
            exit /b 1
        )
    )

    :RunWithUv
    echo [Environment] Using uv package manager...
    echo.

    REM Check if virtual environment exists
    if not exist "%~dp0.venv" (
        echo [Setup] Virtual environment not found. Setting up environment...
        echo This will take a few minutes on first run.
        echo.
        echo Running: uv sync
        echo.

        uv sync

        if !ERRORLEVEL! NEQ 0 (
            echo.
            echo [Retry] Online sync failed, retrying in offline mode...
            echo.
            uv sync --offline

            if !ERRORLEVEL! NEQ 0 (
                echo.
                echo ========================================
                echo [Error] Failed to setup environment
                echo ========================================
                echo.
                echo Both online and offline modes failed.
                echo Please check:
                echo   1. Your internet connection ^(required for first-time setup^)
                echo   2. Ensure you have enough disk space
                echo   3. Try running: uv sync manually
                echo.
                pause
                exit /b 1
            )
        )

        echo.
        echo ========================================
        echo Environment setup completed!
        echo ========================================
        echo.
    )

    call :EnsureLegacyNvidiaTorchCompat
    if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!

    echo Starting ACE-Step API Server...
    echo.

    REM Build command with optional parameters
    set "ACESTEP_ARGS=acestep-api --host %HOST% --port %PORT%"
    if not "%API_KEY%"=="" set "ACESTEP_ARGS=!ACESTEP_ARGS! %API_KEY%"
    if not "%DOWNLOAD_SOURCE%"=="" set "ACESTEP_ARGS=!ACESTEP_ARGS! %DOWNLOAD_SOURCE%"
    if not "%LM_MODEL_PATH%"=="" set "ACESTEP_ARGS=!ACESTEP_ARGS! %LM_MODEL_PATH%"

    uv run --no-sync !ACESTEP_ARGS!
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo [Retry] Online dependency resolution failed, retrying in offline mode...
        echo.
        uv run --offline --no-sync !ACESTEP_ARGS!
        if !ERRORLEVEL! NEQ 0 (
            echo.
            echo ========================================
            echo [Error] Failed to start ACE-Step API Server
            echo ========================================
            echo.
            echo Both online and offline modes failed.
            echo Please check:
            echo   1. Your internet connection ^(for first-time setup^)
            echo   2. If dependencies were previously installed ^(offline mode requires a prior successful install^)
            echo   3. Try running: uv sync --offline
            echo.
            pause
            exit /b 1
        )
    )
)

pause
endlocal
goto :eof

REM ==================== Helper Functions ====================

:EnsureLegacyNvidiaTorchCompat
REM Auto-fix PyTorch for legacy NVIDIA GPUs (e.g., Pascal sm_61 on Quadro P1000)
if /i "%ACESTEP_SKIP_LEGACY_TORCH_FIX%"=="true" exit /b 0
if not exist "%~dp0.venv\Scripts\python.exe" exit /b 0

pushd "%~dp0"
".venv\Scripts\python.exe" -c "import os,sys; sys.path.insert(0, os.getcwd()); from acestep.launcher_compat import legacy_torch_fix_probe_exit_code; raise SystemExit(legacy_torch_fix_probe_exit_code())" >nul 2>&1
set "LEGACY_CHECK_EXIT=!ERRORLEVEL!"

if "!LEGACY_CHECK_EXIT!"=="0" (
    popd
    exit /b 0
)
if not "!LEGACY_CHECK_EXIT!"=="42" (
    echo [Compatibility] Error: legacy NVIDIA compatibility probe failed with exit code !LEGACY_CHECK_EXIT!.
    popd
    exit /b !LEGACY_CHECK_EXIT!
)

echo [Compatibility] Legacy NVIDIA GPU detected with unsupported torch arch.
echo [Compatibility] Installing CUDA 12.1 torch build with sm_61 support...
uv pip install --python .venv\Scripts\python.exe --force-reinstall --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121
if !ERRORLEVEL! EQU 0 (
    echo [Compatibility] Legacy torch install complete.
    REM Keep a legacy-compatible torchao so INT8 quantization remains available
    REM on low-VRAM Pascal/Quadro GPUs.
    uv pip install --python .venv\Scripts\python.exe --force-reinstall torchao==0.11.0 >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo [Compatibility] Installed torchao==0.11.0 (legacy-compatible).
    ) else (
        echo [Compatibility] Warning: failed to install torchao==0.11.0. Quantization may be unavailable.
        popd
        exit /b !ERRORLEVEL!
    )
) else (
    echo [Compatibility] Warning: automatic legacy torch install failed.
    echo [Compatibility] Run manually:
    echo   uv pip install --python .venv\Scripts\python.exe --force-reinstall --index-url https://download.pytorch.org/whl/cu121 torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121
    popd
    exit /b !ERRORLEVEL!
)
popd
exit /b 0
