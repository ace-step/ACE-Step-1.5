@echo off
setlocal enabledelayedexpansion
REM ACE-Step Gradio Web UI Launcher
REM This script launches the Gradio web interface for ACE-Step

REM ==================== Load .env Configuration ====================
REM Load settings from .env file if it exists
call :LoadEnvFile

REM ==================== Configuration ====================
REM Default values (used if not set in .env file)
REM You can override these by uncommenting and modifying the lines below
REM or by creating a .env file (recommended to survive updates)

REM Server settings
if not defined PORT set PORT=7860
if not defined SERVER_NAME set SERVER_NAME=127.0.0.1
REM set SERVER_NAME=0.0.0.0
REM set SHARE=--share

REM UI language: en, zh, he, ja
if not defined LANGUAGE set LANGUAGE=en

REM Model settings
if not defined CONFIG_PATH set CONFIG_PATH=--config_path acestep-v15-turbo
if not defined LM_MODEL_PATH set LM_MODEL_PATH=--lm_model_path acestep-5Hz-lm-0.6B
REM set OFFLOAD_TO_CPU=--offload_to_cpu true

REM LLM (Language Model) initialization settings
REM By default, LLM is auto-enabled/disabled based on GPU VRAM:
REM   - <=6GB VRAM: LLM disabled (DiT-only mode)
REM   - >6GB VRAM: LLM enabled
REM Values: auto (default), true (force enable), false (force disable)
REM set INIT_LLM=--init_llm auto
REM set INIT_LLM=--init_llm true
REM set INIT_LLM=--init_llm false

REM Download source settings
REM Preferred download source: auto (default), huggingface, or modelscope
REM set DOWNLOAD_SOURCE=--download-source modelscope
REM set DOWNLOAD_SOURCE=--download-source huggingface
if not defined DOWNLOAD_SOURCE set DOWNLOAD_SOURCE=

REM Update check on startup (set to false to disable)
if not defined CHECK_UPDATE set CHECK_UPDATE=true
REM set CHECK_UPDATE=false

REM Auto-initialize models on startup
if not defined INIT_SERVICE set INIT_SERVICE=--init_service true

REM API settings (enable REST API alongside Gradio)
REM set ENABLE_API=--enable-api
REM set API_KEY=--api-key sk-your-secret-key

REM Authentication settings
REM set AUTH_USERNAME=--auth-username admin
REM set AUTH_PASSWORD=--auth-password password

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

echo Starting ACE-Step Gradio Web UI...
echo Server will be available at: http://%SERVER_NAME%:%PORT%
echo.

REM Auto-detect Python environment
if exist "%~dp0python_embeded\python.exe" (
    echo [Environment] Using embedded Python...

    REM Build command with optional parameters
    set "PYTHON_EXE=%~dp0python_embeded\python.exe"
    set "SCRIPT_PATH=%~dp0acestep\acestep_v15_pipeline.py"
    set "CMD=--port %PORT% --server-name %SERVER_NAME% --language %LANGUAGE%"
    if not "%SHARE%"=="" set "CMD=!CMD! %SHARE%"
    if not "%CONFIG_PATH%"=="" set "CMD=!CMD! %CONFIG_PATH%"
    if not "%LM_MODEL_PATH%"=="" set "CMD=!CMD! %LM_MODEL_PATH%"
    if not "%OFFLOAD_TO_CPU%"=="" set "CMD=!CMD! %OFFLOAD_TO_CPU%"
    if not "%INIT_LLM%"=="" set "CMD=!CMD! %INIT_LLM%"
    if not "%DOWNLOAD_SOURCE%"=="" set "CMD=!CMD! %DOWNLOAD_SOURCE%"
    if not "%INIT_SERVICE%"=="" set "CMD=!CMD! %INIT_SERVICE%"
    if not "%ENABLE_API%"=="" set "CMD=!CMD! %ENABLE_API%"
    if not "%API_KEY%"=="" set "CMD=!CMD! %API_KEY%"
    if not "%AUTH_USERNAME%"=="" set "CMD=!CMD! %AUTH_USERNAME%"
    if not "%AUTH_PASSWORD%"=="" set "CMD=!CMD! %AUTH_PASSWORD%"

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
                    echo   %USERPROFILE%\.local\bin\uv.exe run acestep
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

    echo Starting ACE-Step Gradio UI...
    echo.

    REM Build command with optional parameters
    set "CMD=uv run acestep --port %PORT% --server-name %SERVER_NAME% --language %LANGUAGE%"
    if not "%SHARE%"=="" set "CMD=!CMD! %SHARE%"
    if not "%CONFIG_PATH%"=="" set "CMD=!CMD! %CONFIG_PATH%"
    if not "%LM_MODEL_PATH%"=="" set "CMD=!CMD! %LM_MODEL_PATH%"
    if not "%OFFLOAD_TO_CPU%"=="" set "CMD=!CMD! %OFFLOAD_TO_CPU%"
    if not "%INIT_LLM%"=="" set "CMD=!CMD! %INIT_LLM%"
    if not "%DOWNLOAD_SOURCE%"=="" set "CMD=!CMD! %DOWNLOAD_SOURCE%"
    if not "%INIT_SERVICE%"=="" set "CMD=!CMD! %INIT_SERVICE%"
    if not "%ENABLE_API%"=="" set "CMD=!CMD! %ENABLE_API%"
    if not "%API_KEY%"=="" set "CMD=!CMD! %API_KEY%"
    if not "%AUTH_USERNAME%"=="" set "CMD=!CMD! %AUTH_USERNAME%"
    if not "%AUTH_PASSWORD%"=="" set "CMD=!CMD! %AUTH_PASSWORD%"

    !CMD!
)

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
        )
    )
)
echo [Config] Configuration loaded from .env
exit /b 0
