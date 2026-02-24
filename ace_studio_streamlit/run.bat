@echo off
REM Quick start script for ACE Studio Streamlit UI (Windows)

setlocal enabledelayedexpansion

echo 🎹 ACE Studio - Quick Start
echo ==================================

REM Check Python
echo Checking Python...
python --version

REM Check if venv exists
if not exist "..\\.venv" (
    echo Creating virtual environment...
    python -m venv ..\\.venv
)

REM Activate venv
echo Activating virtual environment...
call ..\\.venv\\Scripts\\activate.bat

REM Install dependencies
echo Installing Streamlit dependencies...
pip install -q -r requirements.txt

REM Run the app
echo.
echo ==================================
echo ✅ Setup complete!
echo 🚀 Starting ACE Studio...
echo 📱 Open: http://localhost:8501
echo ==================================
echo.

streamlit run main.py

endlocal
