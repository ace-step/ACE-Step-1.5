@echo off
setlocal enabledelayedexpansion
REM Test Environment Auto-Detection
REM This script tests the environment detection logic

echo ========================================
echo ACE-Step Environment Detection Test
echo ========================================
echo.

REM Test 1: Check if python_embedded exists
echo [Test 1] Checking for python_embedded...
if exist "%~dp0python_embedded\python.exe" (
    echo [PASS] python_embedded detected
    echo Location: %~dp0python_embedded\python.exe

    REM Get Python version
    "%~dp0python_embedded\python.exe" --version
) else (
    echo [INFO] python_embedded not found
)
echo.

REM Test 2: Check if uv is available
echo [Test 2] Checking for uv command...
where uv >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [PASS] uv detected

    REM Get uv version
    uv --version
) else (
    echo [INFO] uv not found in PATH
    echo To install uv, run: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
)
echo.

REM Test 3: Check project.scripts in pyproject.toml
echo [Test 3] Checking project scripts...
if exist "%~dp0pyproject.toml" (
    echo [PASS] pyproject.toml found
    echo.
    echo Available scripts:
    findstr /C:"acestep = " "%~dp0pyproject.toml"
    findstr /C:"acestep-api = " "%~dp0pyproject.toml"
    findstr /C:"acestep-download = " "%~dp0pyproject.toml"
) else (
    echo [FAIL] pyproject.toml not found
)
echo.

REM Test 4: Determine which environment will be used
echo [Test 4] Environment selection logic...
if exist "%~dp0python_embedded\python.exe" (
    echo [RESULT] Will use: Embedded Python ^(python_embedded^)
    echo Command: python_embedded\python.exe acestep\acestep_v15_pipeline.py
) else (
    where uv >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo [RESULT] Will use: uv package manager
        echo Command: uv run acestep
    ) else (
        echo [ERROR] Neither python_embedded nor uv found!
        echo Please install uv or extract the portable package.
    )
)
echo.

echo ========================================
echo Test Complete
echo ========================================
pause
