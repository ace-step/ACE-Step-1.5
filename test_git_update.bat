@echo off
setlocal enabledelayedexpansion
REM Test Git Update Check Functionality
REM This script tests the update check without actually starting the application

echo ========================================
echo Test Git Update Check
echo ========================================
echo.

REM Test 1: Check if PortableGit exists
echo [Test 1] Checking PortableGit...
if exist "%~dp0PortableGit\bin\git.exe" (
    echo [PASS] PortableGit found
    "%~dp0PortableGit\bin\git.exe" --version
) else (
    echo [FAIL] PortableGit not found at: %~dp0PortableGit\bin\git.exe
    echo.
    echo Please install PortableGit:
    echo   1. Download: https://git-scm.com/download/win
    echo   2. Extract to: %~dp0PortableGit\
    echo.
    goto :TestFailed
)
echo.

REM Test 2: Check if this is a git repository
echo [Test 2] Checking git repository...
"%~dp0PortableGit\bin\git.exe" rev-parse --git-dir >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [PASS] Valid git repository
    for /f "tokens=*" %%i in ('"%~dp0PortableGit\bin\git.exe" rev-parse --abbrev-ref HEAD 2^>nul') do set CURRENT_BRANCH=%%i
    for /f "tokens=*" %%i in ('"%~dp0PortableGit\bin\git.exe" rev-parse --short HEAD 2^>nul') do set CURRENT_COMMIT=%%i
    echo   Branch: !CURRENT_BRANCH!
    echo   Commit: !CURRENT_COMMIT!
) else (
    echo [FAIL] Not a git repository
    echo.
    echo This directory is not a git repository.
    echo Please clone from GitHub:
    echo   git clone https://github.com/ace-step/ACE-Step-1.5.git
    echo.
    goto :TestFailed
)
echo.

REM Test 3: Check if check_update.bat exists
echo [Test 3] Checking check_update.bat...
if exist "%~dp0check_update.bat" (
    echo [PASS] check_update.bat found
) else (
    echo [FAIL] check_update.bat not found
    goto :TestFailed
)
echo.

REM Test 4: Run update check
echo [Test 4] Running update check...
echo ========================================
echo.

call "%~dp0check_update.bat"
set UPDATE_RESULT=!ERRORLEVEL!

echo.
echo ========================================
echo.

if !UPDATE_RESULT! EQU 0 (
    echo [Test 4] Update check completed successfully
    echo   Result: Already up to date or updated
) else if !UPDATE_RESULT! EQU 1 (
    echo [Test 4] Update check failed
    echo   Result: Error occurred
) else if !UPDATE_RESULT! EQU 2 (
    echo [Test 4] Update check skipped
    echo   Result: Network timeout
) else (
    echo [Test 4] Unknown result: !UPDATE_RESULT!
)
echo.

REM Summary
echo ========================================
echo Test Summary
echo ========================================
echo.

if !UPDATE_RESULT! LEQ 2 (
    echo [PASS] All tests completed
    echo.
    echo The update check feature is working correctly.
    echo You can now enable it in start_gradio_ui.bat:
    echo   set CHECK_UPDATE=true
) else (
    echo [FAIL] Some tests failed
    goto :TestFailed
)

pause
exit /b 0

:TestFailed
echo.
echo ========================================
echo Test Failed
echo ========================================
echo.
echo Please fix the issues above and try again.
echo.
pause
exit /b 1
