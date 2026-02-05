@echo off
setlocal enabledelayedexpansion
REM ACE-Step Gradio Web UI Launcher
REM This script launches the Gradio web interface for ACE-Step

REM ==================== Configuration ====================
REM Uncomment and modify the parameters below as needed

REM Server settings
set PORT=7860
set SERVER_NAME=127.0.0.1
REM set SERVER_NAME=0.0.0.0
REM set SHARE=--share

REM UI language: en, zh, ja
set LANGUAGE=en

REM Model settings
set CONFIG_PATH=--config_path acestep-v15-turbo
set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
REM set OFFLOAD_TO_CPU=--offload_to_cpu true

REM Download source settings
REM Preferred download source: auto (default), huggingface, or modelscope
REM set DOWNLOAD_SOURCE=--download-source modelscope
REM set DOWNLOAD_SOURCE=--download-source huggingface
set DOWNLOAD_SOURCE=

REM Update check settings (for portable package users with PortableGit)
REM Check for updates from GitHub before starting
set CHECK_UPDATE=false
REM set CHECK_UPDATE=true

REM Auto-initialize models on startup
set INIT_SERVICE=--init_service true

REM API settings (enable REST API alongside Gradio)
REM set ENABLE_API=--enable-api
REM set API_KEY=--api-key sk-your-secret-key

REM Authentication settings
REM set AUTH_USERNAME=--auth-username admin
REM set AUTH_PASSWORD=--auth-password password

REM ==================== Launch ====================

REM Check for updates if enabled
if /i "%CHECK_UPDATE%"=="true" (
    echo Checking for updates...
    echo.

    if exist "%~dp0check_update.bat" (
        if exist "%~dp0PortableGit\bin\git.exe" (
            call "%~dp0check_update.bat"
            set UPDATE_CHECK_RESULT=%ERRORLEVEL%

            if !UPDATE_CHECK_RESULT! EQU 1 (
                echo.
                echo [Error] Update check failed.
                echo Continuing with startup...
                echo.
            ) else if !UPDATE_CHECK_RESULT! EQU 2 (
                echo.
                echo [Info] Update check skipped (network timeout).
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

echo Starting ACE-Step Gradio Web UI...
echo Server will be available at: http://%SERVER_NAME%:%PORT%
echo.

REM Auto-detect Python environment
if exist "%~dp0python_embeded\python.exe" (
    echo [Environment] Using embedded Python...
    "%~dp0python_embeded\python.exe" "%~dp0acestep\acestep_v15_pipeline.py" ^
        --port %PORT% ^
        --server-name %SERVER_NAME% ^
        --language %LANGUAGE% ^
        %SHARE% ^
        %CONFIG_PATH% ^
        %LM_MODEL_PATH% ^
        %OFFLOAD_TO_CPU% ^
        %DOWNLOAD_SOURCE% ^
        %INIT_SERVICE% ^
        %ENABLE_API% ^
        %API_KEY% ^
        %AUTH_USERNAME% ^
        %AUTH_PASSWORD%
) else (
    echo [Environment] Embedded Python not found, checking for uv...

    REM Check if uv is installed
    where uv >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ========================================
        echo uv package manager not found!
        echo ========================================
        echo.
        echo ACE-Step requires either:
        echo   1. python_embeded directory (portable package)
        echo   2. uv package manager
        echo.
        echo Would you like to install uv now? (Recommended)
        echo.
        set /p INSTALL_UV="Install uv? (Y/N): "

        if /i "%INSTALL_UV%"=="Y" (
            echo.
            echo Installing uv...
            echo.

            REM Try winget first (Windows 10 1809+ / Windows 11)
            where winget >nul 2>&1
            if %ERRORLEVEL% EQU 0 (
                echo [Method 1] Using winget (Windows Package Manager)...
                echo.
                winget install --id=astral-sh.uv -e --silent

                if %ERRORLEVEL% EQU 0 (
                    echo.
                    echo ========================================
                    echo uv installed successfully via winget!
                    echo ========================================
                    goto :CheckUvInstallation
                ) else (
                    echo.
                    echo winget installation failed, trying PowerShell...
                )
            ) else (
                echo [Info] winget not available, using PowerShell...
            )

            REM Fallback to PowerShell
            echo [Method 2] Using PowerShell...
            echo This may take a few moments...
            echo.

            powershell -NoProfile -ExecutionPolicy Bypass -Command "& {try { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression; Write-Host 'uv installed successfully!' -ForegroundColor Green } catch { Write-Host 'Installation failed. Please install manually.' -ForegroundColor Red; exit 1 }}"

            if %ERRORLEVEL% NEQ 0 (
                echo.
                echo ========================================
                echo Installation failed!
                echo ========================================
                echo.
                echo Please install uv manually:
                echo   1. Using winget: winget install --id=astral-sh.uv -e
                echo   2. Using PowerShell: irm https://astral.sh/uv/install.ps1 ^| iex
                echo   3. Download portable package: https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z
                echo.
                pause
                exit /b 1
            )

            :CheckUvInstallation
            echo.
            echo ========================================
            echo uv installed successfully!
            echo ========================================
            echo.
            echo Refreshing environment...

            REM Refresh PATH to include uv
            REM Check common installation locations
            if exist "%USERPROFILE%\.local\bin\uv.exe" (
                set "PATH=%USERPROFILE%\.local\bin;%PATH%"
            )
            if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" (
                set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
            )

            REM Verify uv is now available
            where uv >nul 2>&1
            if %ERRORLEVEL% EQU 0 (
                echo uv is now available!
                uv --version
                echo.
                goto :RunWithUv
            ) else (
                REM Try direct paths
                if exist "%USERPROFILE%\.local\bin\uv.exe" (
                    "%USERPROFILE%\.local\bin\uv.exe" --version >nul 2>&1
                    if %ERRORLEVEL% EQU 0 (
                        set "PATH=%USERPROFILE%\.local\bin;%PATH%"
                        echo uv is now available!
                        echo.
                        goto :RunWithUv
                    )
                )
                if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" (
                    "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" --version >nul 2>&1
                    if %ERRORLEVEL% EQU 0 (
                        set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
                        echo uv is now available!
                        echo.
                        goto :RunWithUv
                    )
                )

                echo.
                echo uv installed but not in PATH yet.
                echo Please restart your terminal or run:
                echo   %USERPROFILE%\.local\bin\uv.exe run acestep
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

        if %ERRORLEVEL% NEQ 0 (
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

    echo Starting ACE-Step Gradio UI...
    echo.
    uv run acestep ^
        --port %PORT% ^
        --server-name %SERVER_NAME% ^
        --language %LANGUAGE% ^
        %SHARE% ^
        %CONFIG_PATH% ^
        %LM_MODEL_PATH% ^
        %OFFLOAD_TO_CPU% ^
        %DOWNLOAD_SOURCE% ^
        %INIT_SERVICE% ^
        %ENABLE_API% ^
        %API_KEY% ^
        %AUTH_USERNAME% ^
        %AUTH_PASSWORD%
)

pause
