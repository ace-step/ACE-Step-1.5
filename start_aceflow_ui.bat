@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Minimal AceFlow UI launcher for standard ACE-Step uv workflow
REM Optional overrides before launch:
REM   set PORT=7861
REM   set SERVER_NAME=127.0.0.1
REM   set ACEFLOW_CONFIG_PATH=acestep-v15-turbo
REM   set ACEFLOW_LM_MODEL_PATH=acestep-5Hz-lm-4B
REM   set ACEFLOW_DEVICE=auto
REM   set ACEFLOW_RESULTS_DIR=%CD%\aceflow_outputs

if not defined PORT set PORT=7861
if not defined SERVER_NAME set SERVER_NAME=127.0.0.1
if not defined ACEFLOW_CONFIG_PATH set ACEFLOW_CONFIG_PATH=acestep-v15-turbo
if not defined ACEFLOW_LM_MODEL_PATH set ACEFLOW_LM_MODEL_PATH=acestep-5Hz-lm-4B
if not defined ACEFLOW_DEVICE set ACEFLOW_DEVICE=auto
if not defined ACEFLOW_RESULTS_DIR set ACEFLOW_RESULTS_DIR=%~dp0aceflow_outputs

echo Starting AceFlow UI...
echo Server will be available at: http://%SERVER_NAME%:%PORT%
echo.

where uv >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ========================================
    echo uv package manager not found!
    echo ========================================
    echo.
    echo ACE-Step requires the uv package manager.
    echo.
    pause
    exit /b 1
)

echo [Environment] Using uv package manager...
echo.

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

set "ACESTEP_ARGS=python -m acestep.ui.aceflow.run --host %SERVER_NAME% --port %PORT%"

echo [AceFlow] CFG=%ACEFLOW_CONFIG_PATH% ^| LM=%ACEFLOW_LM_MODEL_PATH% ^| DEVICE=%ACEFLOW_DEVICE%
echo.

set "ACESTEP_REMOTE_CONFIG_PATH=%ACEFLOW_CONFIG_PATH%"
set "ACESTEP_REMOTE_LM_MODEL_PATH=%ACEFLOW_LM_MODEL_PATH%"
set "ACESTEP_REMOTE_DEVICE=%ACEFLOW_DEVICE%"
set "ACESTEP_REMOTE_RESULTS_DIR=%ACEFLOW_RESULTS_DIR%"

uv run %ACESTEP_ARGS%
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo [Retry] Online dependency resolution failed, retrying in offline mode...
    echo.
    uv run --offline %ACESTEP_ARGS%
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo ========================================
        echo [Error] Failed to start AceFlow UI
        echo ========================================
        echo.
        pause
        exit /b 1
    )
)

pause
endlocal
