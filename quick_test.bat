@echo off
setlocal enabledelayedexpansion

REM Quick test for PowerShell and uv installation

echo ========================================
echo Quick Environment Test
echo ========================================
echo.

REM Test 1: Check PowerShell
echo [Test 1] Checking PowerShell...
powershell -Command "Write-Host 'PowerShell is available' -ForegroundColor Green; Write-Host 'Version:'; $PSVersionTable.PSVersion" 2>nul
if !ERRORLEVEL! EQU 0 (
    echo [PASS] PowerShell is working
) else (
    echo [FAIL] PowerShell not available
)
echo.

REM Test 2: Check winget
echo [Test 2] Checking winget...
where winget >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [PASS] winget found
    winget --version
) else (
    echo [INFO] winget not found
    echo Note: winget is available on Windows 10 1809+ and Windows 11
)
echo.

REM Test 3: Check python_embeded
echo [Test 3] Checking python_embeded...
if exist "%~dp0python_embeded\python.exe" (
    echo [PASS] python_embeded found
    "%~dp0python_embeded\python.exe" --version
) else (
    echo [INFO] python_embeded not found
)
echo.

REM Test 4: Check uv
echo [Test 4] Checking uv...
where uv >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [PASS] uv found in PATH
    uv --version
) else (
    echo [INFO] uv not found in PATH
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        echo [INFO] But uv.exe exists at: %USERPROFILE%\.local\bin\uv.exe
        "%USERPROFILE%\.local\bin\uv.exe" --version
    ) else (
        if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" (
            echo [INFO] But uv.exe exists at: %LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe
            "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" --version
        ) else (
            echo [INFO] uv not installed
        )
    )
)
echo.

REM Test 5: Test internet connectivity
echo [Test 5] Testing internet connectivity...
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'https://astral.sh' -UseBasicParsing -TimeoutSec 5; Write-Host '[PASS] Can access astral.sh' -ForegroundColor Green } catch { Write-Host '[FAIL] Cannot access astral.sh' -ForegroundColor Red; Write-Host 'Error:' $_.Exception.Message }"
echo.

REM Summary
echo ========================================
echo Summary
echo ========================================
echo.

REM Determine which environment will be used
set ENV_FOUND=0

if exist "%~dp0python_embeded\python.exe" (
    echo [RESULT] Will use: python_embeded
    echo No additional setup needed!
    set ENV_FOUND=1
)

if !ENV_FOUND! EQU 0 (
    where uv >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo [RESULT] Will use: uv ^(from PATH^)
        echo No additional setup needed!
        set ENV_FOUND=1
    )
)

if !ENV_FOUND! EQU 0 (
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        echo [RESULT] Will use: uv ^(not in PATH^)
        echo Action: Add to PATH or restart terminal
        set ENV_FOUND=1
    )
)

if !ENV_FOUND! EQU 0 (
    if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" (
        echo [RESULT] Will use: uv ^(not in PATH^)
        echo Action: Add to PATH or restart terminal
        set ENV_FOUND=1
    )
)

if !ENV_FOUND! EQU 0 (
    echo [RESULT] No environment found
    echo Action: Run start_gradio_ui.bat to install uv
    echo Or: Download portable package
)

echo.
echo ========================================
echo Press any key to close...
echo ========================================
pause >nul

endlocal
