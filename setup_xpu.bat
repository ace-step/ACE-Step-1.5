@echo off
setlocal enabledelayedexpansion
REM ACE-Step XPU Environment Setup Script
REM This script creates the venv_xpu virtual environment and installs all dependencies
REM For Intel Arc GPUs (A770, A750, A580, A380) and integrated graphics

echo ======================================================
echo     ACE-Step 1.5 - Intel XPU Environment Setup
echo ======================================================
echo.
echo This script will:
echo   1. Create venv_xpu virtual environment ^(Python 3.11^)
echo   2. Install PyTorch XPU nightly build
echo   3. Install all ACE-Step dependencies
echo.
echo Requirements:
echo   - Python 3.11 installed and in PATH
echo   - Intel Arc GPU with latest drivers
echo   - Internet connection for first-time installation
echo   - ~5-10 GB disk space
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause >nul
echo.

REM Check Python version
python --version >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo ========================================
    echo  ERROR: Python not found!
    echo ========================================
    echo.
    echo Please install Python 3.11 from:
    echo   https://www.python.org/downloads/release/python-3119/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

python --version | find "3.11" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo WARNING: Python 3.11 recommended, but found:
    python --version
    echo.
    set /p CONTINUE="Continue anyway? (Y/N): "
    if /i not "!CONTINUE!"=="Y" (
        echo.
        echo Please install Python 3.11 for best compatibility.
        pause
        exit /b 1
    )
    echo.
)

REM Check if venv_xpu already exists
if exist "venv_xpu\Scripts\activate.bat" (
    echo ========================================
    echo  venv_xpu already exists!
    echo ========================================
    echo.
    echo Location: %~dp0venv_xpu
    echo.
    set /p RECREATE="Recreate virtual environment? (Y/N): "
    if /i "!RECREATE!"=="Y" (
        echo.
        echo Removing old venv_xpu...
        rmdir /s /q venv_xpu
        echo.
    ) else (
        echo.
        echo Existing environment will be updated.
        echo.
    )
)

REM Create virtual environment
echo ========================================
echo Step 1: Creating virtual environment
echo ========================================
echo.

if exist "venv_xpu" (
    echo Cleaning existing venv_xpu...
    rmdir /s /q venv_xpu
)

echo Running: python -m venv venv_xpu
echo.
python -m venv venv_xpu

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ========================================
    echo  ERROR: Failed to create virtual environment!
    echo ========================================
    echo.
    echo Please check:
    echo   1. Python is installed correctly
    echo   2. You have write permissions in this directory
    echo   3. No antivirus is blocking venv creation
    echo.
    pause
    exit /b 1
)

echo Virtual environment created successfully!
echo.

REM Activate virtual environment
echo ========================================
echo Step 2: Activating virtual environment
echo ========================================
echo.

call venv_xpu\Scripts\activate.bat

REM Upgrade pip
echo ========================================
echo Step 3: Upgrading pip
echo ========================================
echo.

echo Running: python -m pip install --upgrade pip
python -m pip install --upgrade pip -q

echo pip upgraded successfully!
echo.

REM Check requirements-xpu.txt exists
if not exist "requirements-xpu.txt" (
    echo ========================================
    echo  ERROR: requirements-xpu.txt not found!
    echo ========================================
    echo.
    echo Please make sure you are running this script
    echo from the ACE-Step-1.5 root directory.
    echo.
    pause
    exit /b 1
)

REM Install dependencies
echo ========================================
echo Step 4: Installing XPU dependencies
echo ========================================
echo.
echo This will take a few minutes on first run...
echo.
echo Running: pip install -r requirements-xpu.txt
echo.

pip install -r requirements-xpu.txt

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ========================================
    echo  WARNING: Some packages may have failed to install
    echo ========================================
    echo.
    echo This can happen due to:
    echo   - Network issues
    echo   - Incompatible package versions
    echo.
    echo Trying to continue with available packages...
    echo.
    timeout /t 5 /nobreak >nul
)

echo.
echo ========================================
echo Step 5: Verifying Installation
echo ========================================
echo.

REM Verify PyTorch XPU installation
echo Checking PyTorch XPU installation...
python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'XPU available: {torch.xpu.is_available()}')" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo WARNING: PyTorch XPU verification failed!
    echo The installation may be incomplete.
    echo.
    echo Try running manually:
    echo   call venv_xpu\Scripts\activate
    echo   pip install -r requirements-xpu.txt
    echo.
) else (
    echo PyTorch XPU installed successfully!
)
echo.

REM Display summary
echo ======================================================
echo     Installation Complete!
echo ======================================================
echo.
echo Your ACE-Step XPU environment is ready to use!
echo.
echo Next steps:
echo   1. Download ACE-Step models to the 'checkpoints' folder
echo      ^(if not already present^)
echo.
echo   2. Launch the Gradio UI:
echo      start_gradio_ui_xpu.bat
echo.
echo   3. Or launch with manual model selection:
echo      start_gradio_ui_xpu_manual.bat
echo.
echo   4. Or launch the API server:
echo      start_api_server_xpu.bat
echo.
echo To activate the environment manually:
echo   call venv_xpu\Scripts\activate
echo.
echo ======================================================
echo.
pause

endlocal
