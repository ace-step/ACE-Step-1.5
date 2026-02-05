@echo off
REM Install uv Package Manager
REM This script installs uv using PowerShell

echo ========================================
echo Install uv Package Manager
echo ========================================
echo.
echo This script will install uv, a fast Python package manager.
echo Installation location: %USERPROFILE%\.local\bin\
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause >nul
echo.

REM Check if uv is already installed
where uv >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo uv is already installed!
    echo Current version:
    uv --version
    echo.
    echo Installation location:
    where uv
    echo.

    set /p REINSTALL="Reinstall uv? (Y/N): "
    if /i not "%REINSTALL%"=="Y" (
        echo.
        echo Installation cancelled.
        pause
        exit /b 0
    )
    echo.
)

echo Installing uv...
echo.

REM Try winget first (Windows 10 1809+ / Windows 11)
where winget >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [Method 1] Using winget (Windows Package Manager)...
    echo.
    winget install --id=astral-sh.uv -e

    if %ERRORLEVEL% EQU 0 (
        echo.
        echo ========================================
        echo uv installed successfully via winget!
        echo ========================================
        goto :VerifyInstallation
    ) else (
        echo.
        echo winget installation failed, trying PowerShell...
        echo.
    )
) else (
    echo [Info] winget not available, using PowerShell...
    echo.
)

REM Fallback to PowerShell
echo [Method 2] Using PowerShell...
echo This may take a few moments...
echo.

REM Check if PowerShell is available
powershell -Command "Write-Host 'PowerShell is available'" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ========================================
    echo ERROR: PowerShell not found!
    echo ========================================
    echo.
    echo Neither winget nor PowerShell is available.
    echo Please install uv manually from: https://astral.sh/uv
    echo.
    pause
    exit /b 1
)

REM Install uv using PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& {Write-Host 'Downloading uv installer...' -ForegroundColor Cyan; try { $ProgressPreference = 'SilentlyContinue'; Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression; Write-Host ''; Write-Host '========================================' -ForegroundColor Green; Write-Host 'uv installed successfully!' -ForegroundColor Green; Write-Host '========================================' -ForegroundColor Green } catch { Write-Host ''; Write-Host '========================================' -ForegroundColor Red; Write-Host 'Installation failed!' -ForegroundColor Red; Write-Host '========================================' -ForegroundColor Red; Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }}"

:VerifyInstallation

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Verifying installation...

    REM Check if uv is in PATH
    where uv >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo ========================================
        echo Installation successful!
        echo ========================================
        echo.
        echo uv version:
        uv --version
        echo.
        echo Installation location:
        where uv
        echo.
        echo You can now use ACE-Step by running:
        echo   start_gradio_ui.bat
        echo   start_api_server.bat
        echo.
    ) else (
        REM Check in the default installation location
        if exist "%USERPROFILE%\.local\bin\uv.exe" (
            echo.
            echo ========================================
            echo Installation successful!
            echo ========================================
            echo.
            echo Installation location: %USERPROFILE%\.local\bin\uv.exe
            echo.
            echo NOTE: uv is not in your PATH yet.
            echo Please restart your terminal, or manually add to PATH:
            echo   setx PATH "%%PATH%%;%USERPROFILE%\.local\bin"
            echo.
            echo For now, you can use the full path:
            echo   %USERPROFILE%\.local\bin\uv.exe --version
            echo.
        ) else (
            echo.
            echo ========================================
            echo Installation completed but uv not found!
            echo ========================================
            echo.
            echo Please check the installation manually or try again.
            echo.
        )
    )
    pause
    exit /b 0
) else (
    echo.
    echo ========================================
    echo Installation failed!
    echo ========================================
    echo.
    echo Please try one of the following:
    echo.
    echo 1. Manual installation via PowerShell:
    echo    Open PowerShell and run:
    echo    irm https://astral.sh/uv/install.ps1 ^| iex
    echo.
    echo 2. Use the portable package instead:
    echo    Download: https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z
    echo    Extract and run: start_gradio_ui.bat
    echo.
    echo 3. Check your internet connection and try again
    echo.
    pause
    exit /b 1
)
