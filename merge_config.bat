@echo off
REM Config Merge Helper
REM This script helps merge backed up files with new version

setlocal enabledelayedexpansion

echo ========================================
echo ACE-Step Backup Merge Helper
echo ========================================
echo.

REM Check for backup directories
set FOUND_BACKUPS=0
echo Searching for backup directories...
echo.

for /d %%d in ("%~dp0.update_backup_*") do (
    set FOUND_BACKUPS=1
    set "CURRENT_BACKUP_DIR=%%d"
    echo Found backup: %%~nxd
    echo   Location: %%d
    echo   Files:
    for /f "delims=" %%f in ('dir /b /s "%%d\*.*" 2^>nul') do (
        set "FILEPATH=%%f"
        REM Use call to safely handle the string replacement
        call set "FILEPATH=%%FILEPATH:!CURRENT_BACKUP_DIR!\=%%"
        echo     - !FILEPATH!
    )
    echo.
)

if %FOUND_BACKUPS% EQU 0 (
    echo No backup directories found.
    echo.
    echo Backups are created when updates conflict with your local changes.
    pause
    exit /b 0
)

echo ========================================
echo Merge Options
echo ========================================
echo.
echo 1. Compare backup with current files (opens Notepad)
echo 2. Restore a file from backup (overwrites current)
echo 3. List all backed up files
echo 4. Delete old backups
echo 5. Exit
echo.

set /p CHOICE="Select option (1-5): "

if "%CHOICE%"=="1" goto :Compare
if "%CHOICE%"=="2" goto :Restore
if "%CHOICE%"=="3" goto :ListFiles
if "%CHOICE%"=="4" goto :DeleteBackups
if "%CHOICE%"=="5" exit /b 0

echo Invalid choice.
pause
exit /b 1

:Compare
echo.
echo ========================================
echo Compare Files
echo ========================================
echo.
echo Available backup directories:
set INDEX=0
for /d %%d in ("%~dp0.update_backup_*") do (
    set /a INDEX+=1
    set BACKUP_!INDEX!=%%d
    echo !INDEX!. %%~nxd
)

if %INDEX% EQU 0 (
    echo No backups found.
    pause
    exit /b 0
)

echo.
set /p BACKUP_CHOICE="Select backup number: "

set SELECTED_BACKUP=!BACKUP_%BACKUP_CHOICE%!
if not defined SELECTED_BACKUP (
    echo Invalid selection.
    pause
    exit /b 1
)

echo.
echo Files in backup:
set "SELECTED_BACKUP_DISPLAY=!SELECTED_BACKUP!"
for /f "delims=" %%f in ('dir /b /s "!SELECTED_BACKUP!\*.*" 2^>nul') do (
    set "FILEPATH=%%f"
    REM Use call to safely handle the string replacement
    call set "FILEPATH=%%FILEPATH:!SELECTED_BACKUP_DISPLAY!\=%%"
    echo   - !FILEPATH!
)

echo.
set /p FILE_NAME="Enter filename to compare (e.g., start_gradio_ui.bat or acestep\handler.py): "

set BACKUP_FILE=%SELECTED_BACKUP%\%FILE_NAME%
set CURRENT_FILE=%~dp0%FILE_NAME%

if not exist "%BACKUP_FILE%" (
    echo Backup file not found: %BACKUP_FILE%
    pause
    exit /b 1
)

if not exist "%CURRENT_FILE%" (
    echo Current file not found: %CURRENT_FILE%
    pause
    exit /b 1
)

echo.
echo Opening files for comparison...
echo.
echo Backup version (LEFT):  %BACKUP_FILE%
echo Current version (RIGHT): %CURRENT_FILE%
echo.

REM Open both files side by side
start "" notepad "%BACKUP_FILE%"
timeout /t 1 /nobreak >nul
start "" notepad "%CURRENT_FILE%"

echo.
echo Files opened in Notepad.
echo Compare the files and manually apply your configuration changes.
echo.
pause
exit /b 0

:Restore
echo.
echo ========================================
echo Restore File from Backup
echo ========================================
echo.
echo [Warning] This will OVERWRITE the current file!
echo.
echo Available backup directories:
set INDEX=0
for /d %%d in ("%~dp0.update_backup_*") do (
    set /a INDEX+=1
    set BACKUP_!INDEX!=%%d
    echo !INDEX!. %%~nxd
)

if %INDEX% EQU 0 (
    echo No backups found.
    pause
    exit /b 0
)

echo.
set /p BACKUP_CHOICE="Select backup number: "

set SELECTED_BACKUP=!BACKUP_%BACKUP_CHOICE%!
if not defined SELECTED_BACKUP (
    echo Invalid selection.
    pause
    exit /b 1
)

echo.
echo Files in backup:
set "SELECTED_BACKUP_DISPLAY=!SELECTED_BACKUP!"
for /f "delims=" %%f in ('dir /b /s "!SELECTED_BACKUP!\*.*" 2^>nul') do (
    set "FILEPATH=%%f"
    REM Use call to safely handle the string replacement
    call set "FILEPATH=%%FILEPATH:!SELECTED_BACKUP_DISPLAY!\=%%"
    echo   - !FILEPATH!
)

echo.
set /p FILE_NAME="Enter filename to restore (e.g., start_gradio_ui.bat or acestep\handler.py): "

set BACKUP_FILE=%SELECTED_BACKUP%\%FILE_NAME%
set CURRENT_FILE=%~dp0%FILE_NAME%

if not exist "%BACKUP_FILE%" (
    echo Backup file not found: %BACKUP_FILE%
    pause
    exit /b 1
)

echo.
echo About to restore:
echo   From: %BACKUP_FILE%
echo   To:   %CURRENT_FILE%
echo.
set /p CONFIRM="Are you sure? This will overwrite the current file. (Y/N): "

if /i "%CONFIRM%"=="Y" (
    copy /y "%BACKUP_FILE%" "%CURRENT_FILE%" >nul
    if !ERRORLEVEL! EQU 0 (
        echo.
        echo [Success] File restored successfully.
    ) else (
        echo.
        echo [Error] Failed to restore file.
    )
) else (
    echo.
    echo Restore cancelled.
)

echo.
pause
exit /b 0

:ListFiles
echo.
echo ========================================
echo All Backed Up Files
echo ========================================
echo.

for /d %%d in ("%~dp0.update_backup_*") do (
    set "CURRENT_BACKUP_DIR=%%d"
    echo Backup: %%~nxd
    echo Location: %%d
    echo Files:
    for /f "delims=" %%f in ('dir /b /s "%%d" 2^>nul') do (
        set "FILEPATH=%%f"
        REM Use call to safely handle the string replacement
        call set "FILEPATH=%%FILEPATH:!CURRENT_BACKUP_DIR!\=%%"
        echo   - !FILEPATH!
    )
    echo.
)

pause
exit /b 0

:DeleteBackups
echo.
echo ========================================
echo Delete Old Backups
echo ========================================
echo.
echo [Warning] This will permanently delete backup directories!
echo.
echo Available backups:
for /d %%d in ("%~dp0.update_backup_*") do (
    echo   - %%~nxd
)

echo.
set /p DELETE_CONFIRM="Delete all backups? (Y/N): "

if /i "%DELETE_CONFIRM%"=="Y" (
    echo.
    echo Deleting backups...
    for /d %%d in ("%~dp0.update_backup_*") do (
        echo   Deleting: %%~nxd
        rmdir /s /q "%%d" 2>nul
    )
    echo.
    echo [Done] Backups deleted.
) else (
    echo.
    echo Deletion cancelled.
)

echo.
pause
exit /b 0
