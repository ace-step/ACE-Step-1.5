@echo off
setlocal enabledelayedexpansion
REM Install uv Package Manager
REM This script installs uv using PowerShell or winget
REM
REM Usage:
REM   install_uv.bat           - Interactive mode (default)
REM   install_uv.bat --silent  - Silent mode for script calls
REM
REM Exit codes:
REM   0 - Success (uv installed and available)
REM   1 - Installation failed
REM   2 - User cancelled (interactive mode only)

REM Check for silent mode
set SILENT_MODE=0
if /i "%~1"=="--silent" set SILENT_MODE=1
if /i "%~1"=="-s" set SILENT_MODE=1

if %SILENT_MODE% EQU 0 (
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
)

REM Check if uv is already installed
where uv >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    if %SILENT_MODE% EQU 1 (
        REM In silent mode, uv already installed is success
        endlocal & exit /b 0
    )

    echo uv is already installed!
    echo Current version:
    uv --version
    echo.
    echo Installation location:
    where uv
    echo.

    set /p REINSTALL="Reinstall uv? (Y/N): "
    if /i not "!REINSTALL!"=="Y" (
        echo.
        echo Installation cancelled.
        pause
        endlocal & exit /b 2
    )
    echo.
)

if %SILENT_MODE% EQU 0 (
    echo Installing uv...
    echo.
)

REM Try PowerShell first (preferred method)
if %SILENT_MODE% EQU 0 (
    echo [Method 1] Using PowerShell...
    echo This may take a few moments...
    echo.
)

REM Check if PowerShell is available
powershell -Command "Write-Host 'PowerShell is available'" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    REM Install uv using PowerShell
    if %SILENT_MODE% EQU 1 (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression" >nul 2>&1
    ) else (
        echo Downloading uv installer...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression"
    )

    if !ERRORLEVEL! EQU 0 (
        goto :VerifyInstallation
    ) else (
        if %SILENT_MODE% EQU 0 (
            echo.
            echo PowerShell installation failed, trying winget...
            echo.
        )
    )
) else (
    if %SILENT_MODE% EQU 0 (
        echo [Info] PowerShell not available, trying winget...
        echo.
    )
)

REM Fallback to winget (Windows 10 1809+ / Windows 11)
where winget >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    if %SILENT_MODE% EQU 0 (
        echo [Method 2] Using winget ^(Windows Package Manager^)...
        echo.
    )

    if %SILENT_MODE% EQU 1 (
        winget install --id=astral-sh.uv -e --silent >nul 2>&1
    ) else (
        winget install --id=astral-sh.uv -e
    )

    if !ERRORLEVEL! EQU 0 (
        if %SILENT_MODE% EQU 0 (
            echo.
            echo ========================================
            echo uv installed successfully via winget!
            echo ========================================
        )
        goto :VerifyInstallation
    ) else (
        if %SILENT_MODE% EQU 0 (
            echo.
            echo winget installation also failed.
            echo.
        )
    )
) else (
    if %SILENT_MODE% EQU 0 (
        echo [Info] winget not available.
        echo.
    )
)

REM Both methods failed
if %SILENT_MODE% EQU 0 (
    echo ========================================
    echo ERROR: All installation methods failed!
    echo ========================================
    echo.
    echo Please install uv manually:
    echo.
    echo 1. Open PowerShell and run:
    echo    irm https://astral.sh/uv/install.ps1 ^| iex
    echo.
    echo 2. Or use winget:
    echo    winget install --id=astral-sh.uv -e
    echo.
    echo 3. Or download portable package:
    echo    https://files.acemusic.ai/acemusic/win/ACE-Step-1.5.7z
    echo.
    pause
)
endlocal & exit /b 1

:VerifyInstallation

REM Check if uv is in PATH
where uv >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    if %SILENT_MODE% EQU 0 (
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
        pause
    )
    endlocal & exit /b 0
)

REM Check in the default installation location and update PATH
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    endlocal & set "PATH=%USERPROFILE%\.local\bin;%PATH%" & goto :PostEndlocal_UserProfile
)
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" (
    endlocal & set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%" & goto :PostEndlocal_WinGet
)

REM Not found anywhere
if %SILENT_MODE% EQU 0 (
    echo.
    echo ========================================
    echo Installation completed but uv not found!
    echo ========================================
    echo.
    echo Please restart your terminal and try again.
    echo.
    pause
)
endlocal & exit /b 1

:PostEndlocal_UserProfile
if "%SILENT_MODE%"=="0" (
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
    pause
)
exit /b 0

:PostEndlocal_WinGet
if "%SILENT_MODE%"=="0" (
    echo.
    echo ========================================
    echo Installation successful!
    echo ========================================
    echo.
    echo Installation location: %LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe
    echo.
    echo NOTE: uv is not in your PATH yet.
    echo Please restart your terminal.
    echo.
    pause
)
exit /b 0
