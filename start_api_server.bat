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
REM set ACESTEP_INIT_LLM=auto
REM set ACESTEP_INIT_LLM=true
REM set ACESTEP_INIT_LLM=false

REM LM model path (optional, only used when LLM is enabled)
REM Available models: acestep-5Hz-lm-0.6B, acestep-5Hz-lm-1.7B, acestep-5Hz-lm-4B
REM set LM_MODEL_PATH=--lm-model-path acestep-5Hz-lm-0.6B

REM Update check settings (for portable package users with PortableGit)
REM Check for updates from GitHub before starting
set CHECK_UPDATE=false
REM set CHECK_UPDATE=true

REM ==================== Launch ====================

REM Check for updates if enabled
if /i "%CHECK_UPDATE%"=="true" (
    echo Checking for updates...
    echo.

    if exist "%~dp0check_update.bat" (
        if exist "%~dp0PortableGit\bin\git.exe" (
            call "%~dp0check_update.bat"
            set UPDATE_CHECK_RESULT=!ERRORLEVEL!

            if !UPDATE_CHECK_RESULT! EQU 1 (
                echo.
                echo [Error] Update check failed.
                echo Continuing with startup...
                echo.
            ) else if !UPDATE_CHECK_RESULT! EQU 2 (
                echo.
                echo [Info] Update check skipped (network timeout^).
                echo Continuing with startup...
                echo.
            )

            REM Wait a moment before starting
            timeout /t 2 /nobreak >nul
        ) else (
            echo [Info] PortableGit not found, skipping update check.
            echo To enable update checks, install PortableGit in the PortableGit folder.
            echo.
        )
    ) else (
        echo [Info] check_update.bat not found, skipping update check.
        echo.
    )
)

echo Starting ACE-Step REST API Server...
echo API will be available at: http://%HOST%:%PORT%
echo API Documentation: http://%HOST%:%PORT%/docs
echo.

REM Auto-detect Python environment
if exist "%~dp0python_embeded\python.exe" (
    echo [Environment] Using embedded Python...

    REM Build command with optional parameters
    set "PYTHON_EXE=%~dp0python_embeded\python.exe"
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
        echo   1. python_embeded directory ^(portable package^)
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
            echo ========================================
            echo [Error] Failed to setup environment
            echo ========================================
            echo.
            echo Please check the error messages above.
            echo You may need to:
            echo   1. Check your internet connection
            echo   2. Ensure you have enough disk space
            echo   3. Try running: uv sync manually
            echo.
            pause
            exit /b 1
        )

        echo.
        echo ========================================
        echo Environment setup completed!
        echo ========================================
        echo.
    )

    echo Starting ACE-Step API Server...
    echo.

    REM Build command with optional parameters
    set "CMD=uv run acestep-api --host %HOST% --port %PORT%"
    if not "%API_KEY%"=="" set "CMD=!CMD! %API_KEY%"
    if not "%DOWNLOAD_SOURCE%"=="" set "CMD=!CMD! %DOWNLOAD_SOURCE%"
    if not "%LM_MODEL_PATH%"=="" set "CMD=!CMD! %LM_MODEL_PATH%"

    !CMD!
)

pause
endlocal
