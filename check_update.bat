@echo off
REM Git Update Check Utility
REM This script checks for updates from GitHub and optionally updates the repository

setlocal enabledelayedexpansion

REM Configuration
set TIMEOUT_SECONDS=10
set GIT_PORTABLE_PATH=%~dp0PortableGit\bin\git.exe
set REPO_PATH=%~dp0
set PROXY_CONFIG_FILE=%~dp0proxy_config.txt

echo ========================================
echo ACE-Step Update Check
echo ========================================
echo.

REM Check if PortableGit exists
if not exist "%GIT_PORTABLE_PATH%" (
    echo [Error] PortableGit not found at: %GIT_PORTABLE_PATH%
    echo Please ensure PortableGit is installed in the PortableGit folder.
    echo.
    echo ========================================
    echo Press any key to close...
    echo ========================================
    pause >nul
    exit /b 1
)

REM Check if this is a git repository
cd /d "%REPO_PATH%"
"%GIT_PORTABLE_PATH%" rev-parse --git-dir >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [Error] Not a git repository.
    echo This folder does not appear to be a git repository.
    echo.
    echo ========================================
    echo Press any key to close...
    echo ========================================
    pause >nul
    exit /b 1
)

REM Load proxy configuration if exists
set PROXY_ENABLED=0
set PROXY_URL=
if exist "%PROXY_CONFIG_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%PROXY_CONFIG_FILE%") do (
        if /i "%%a"=="PROXY_ENABLED" set PROXY_ENABLED=%%b
        if /i "%%a"=="PROXY_URL" set PROXY_URL=%%b
    )

    if "!PROXY_ENABLED!"=="1" (
        if not "!PROXY_URL!"=="" (
            echo [Proxy] Using proxy server: !PROXY_URL!
            "%GIT_PORTABLE_PATH%" config --local http.proxy "!PROXY_URL!"
            "%GIT_PORTABLE_PATH%" config --local https.proxy "!PROXY_URL!"
            echo.
        )
    )
)

echo [1/4] Checking current version...
REM Get current branch
for /f "tokens=*" %%i in ('"%GIT_PORTABLE_PATH%" rev-parse --abbrev-ref HEAD 2^>nul') do set CURRENT_BRANCH=%%i
if "%CURRENT_BRANCH%"=="" set CURRENT_BRANCH=main

REM Get current commit
for /f "tokens=*" %%i in ('"%GIT_PORTABLE_PATH%" rev-parse --short HEAD 2^>nul') do set CURRENT_COMMIT=%%i

echo   Branch: %CURRENT_BRANCH%
echo   Commit: %CURRENT_COMMIT%
echo.

echo [2/4] Checking for updates (timeout: %TIMEOUT_SECONDS%s)...
echo   Connecting to GitHub...

:FetchRetry
REM Fetch remote with timeout
REM Use START /B to run in background and check timeout
set FETCH_SUCCESS=0
"%GIT_PORTABLE_PATH%" fetch origin --quiet 2>nul
if %ERRORLEVEL% EQU 0 (
    set FETCH_SUCCESS=1
) else (
    REM Try with timeout using a temp marker file
    set TEMP_MARKER=%TEMP%\acestep_git_fetch_%RANDOM%.tmp

    REM Start fetch in background
    start /b "" cmd /c ""%GIT_PORTABLE_PATH%" fetch origin --quiet >nul 2>&1 && echo SUCCESS > "!TEMP_MARKER!""

    REM Wait with timeout
    set /a COUNTER=0
    :WaitLoop
    if exist "!TEMP_MARKER!" (
        set FETCH_SUCCESS=1
        del "!TEMP_MARKER!" >nul 2>&1
        goto :FetchDone
    )

    timeout /t 1 /nobreak >nul
    set /a COUNTER+=1
    if !COUNTER! LSS %TIMEOUT_SECONDS% goto :WaitLoop

    REM Timeout reached
    echo   [Timeout] Could not connect to GitHub within %TIMEOUT_SECONDS% seconds.
)

:FetchDone
if %FETCH_SUCCESS% EQU 0 (
    echo   [Failed] Could not fetch from GitHub.
    echo   Please check your internet connection.
    echo.

    REM Ask if user wants to configure proxy
    set /p PROXY_CHOICE="Do you want to configure a proxy server to retry? (Y/N): "
    if /i "!PROXY_CHOICE!"=="Y" (
        call :ConfigureProxy
        if !ERRORLEVEL! EQU 0 (
            echo.
            echo [Proxy] Retrying with proxy configuration...
            echo.
            goto :FetchRetry
        )
    )

    echo.
    echo ========================================
    echo Press any key to close...
    echo ========================================
    pause >nul
    exit /b 2
)

echo   [Success] Fetched latest information from GitHub.
echo.

echo [3/4] Comparing versions...
REM Get remote commit
for /f "tokens=*" %%i in ('"%GIT_PORTABLE_PATH%" rev-parse --short origin/%CURRENT_BRANCH% 2^>nul') do set REMOTE_COMMIT=%%i

if "%REMOTE_COMMIT%"=="" (
    echo   [Warning] Remote branch 'origin/%CURRENT_BRANCH%' not found.
    echo.
    echo   Your current branch '%CURRENT_BRANCH%' does not exist on the remote repository.
    echo   This might be a local development branch.
    echo.

    REM Try to get main branch instead
    set FALLBACK_BRANCH=main
    echo   Checking main branch instead...
    for /f "tokens=*" %%i in ('"%GIT_PORTABLE_PATH%" rev-parse --short origin/!FALLBACK_BRANCH! 2^>nul') do set REMOTE_COMMIT=%%i

    if "!REMOTE_COMMIT!"=="" (
        echo   [Error] Could not find remote main branch either.
        echo   Please ensure you are connected to the correct repository.
        echo.
        echo ========================================
        echo Press any key to close...
        echo ========================================
        pause >nul
        exit /b 1
    )

    echo   Found main branch: !REMOTE_COMMIT!
    echo.
    echo   Recommendation: Switch to main branch to check for official updates.
    echo   Command: git checkout main
    echo.

    set /p SWITCH_BRANCH="Do you want to switch to main branch now? (Y/N): "
    if /i "!SWITCH_BRANCH!"=="Y" (
        echo.
        echo   Switching to main branch...
        "%GIT_PORTABLE_PATH%" checkout main

        if !ERRORLEVEL! EQU 0 (
            echo   [Success] Switched to main branch.
            echo.
            echo   Please run this script again to check for updates.
            echo.
            echo ========================================
            echo Press any key to close...
            echo ========================================
            pause >nul
            exit /b 0
        ) else (
            echo   [Error] Failed to switch branch.
            echo.
            echo ========================================
            echo Press any key to close...
            echo ========================================
            pause >nul
            exit /b 1
        )
    ) else (
        echo.
        echo   Continuing with current branch comparison...
        echo   Note: This comparison may not reflect official updates.
        echo.
        set CURRENT_BRANCH=!FALLBACK_BRANCH!
    )
)

echo   Local:  %CURRENT_COMMIT%
echo   Remote: %REMOTE_COMMIT%
echo.

REM Compare commits
if "%CURRENT_COMMIT%"=="%REMOTE_COMMIT%" (
    echo [4/4] Result: Already up to date!
    echo   You have the latest version.
    echo.
    echo ========================================
    echo Press any key to close...
    echo ========================================
    pause >nul
    exit /b 0
) else (
    echo [4/4] Result: Update available!

    REM Check if local is behind remote
    "%GIT_PORTABLE_PATH%" merge-base --is-ancestor HEAD origin/%CURRENT_BRANCH% 2>nul
    if %ERRORLEVEL% EQU 0 (
        echo   A new version is available on GitHub.
        echo.

        REM Show commits behind
        echo   New commits:
        "%GIT_PORTABLE_PATH%" log --oneline --graph --decorate HEAD..origin/%CURRENT_BRANCH% 2>nul
        echo.

        REM Ask if user wants to update
        set /p UPDATE_CHOICE="Do you want to update now? (Y/N): "
        if /i "!UPDATE_CHOICE!"=="Y" (
            echo.
            echo Updating...

            REM Check for uncommitted changes
            "%GIT_PORTABLE_PATH%" diff-index --quiet HEAD -- 2>nul
            if %ERRORLEVEL% NEQ 0 (
                echo.
                echo [Info] Checking for potential conflicts...

                REM Get list of locally modified files
                set TEMP_LOCAL_CHANGES=%TEMP%\acestep_local_changes_%RANDOM%.txt
                "%GIT_PORTABLE_PATH%" diff --name-only HEAD 2>nul > "!TEMP_LOCAL_CHANGES!"

                REM Get list of files changed in remote
                set TEMP_REMOTE_CHANGES=%TEMP%\acestep_remote_changes_%RANDOM%.txt
                "%GIT_PORTABLE_PATH%" diff --name-only HEAD..origin/%CURRENT_BRANCH% 2>nul > "!TEMP_REMOTE_CHANGES!"

                REM Check for conflicts
                set HAS_CONFLICTS=0
                set BACKUP_DIR=%~dp0.update_backup_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
                set BACKUP_DIR=!BACKUP_DIR: =0!

                REM Find conflicting files
                for /f "usebackq delims=" %%a in ("!TEMP_LOCAL_CHANGES!") do (
                    findstr /x /c:"%%a" "!TEMP_REMOTE_CHANGES!" >nul 2>&1
                    if !ERRORLEVEL! EQU 0 (
                        REM Found a conflict
                        set HAS_CONFLICTS=1

                        REM Create backup directory if not exists
                        if not exist "!BACKUP_DIR!" (
                            mkdir "!BACKUP_DIR!"
                            echo.
                            echo [Backup] Creating backup directory: !BACKUP_DIR!
                        )

                        REM Backup the file
                        echo [Backup] Backing up: %%a
                        set FILE_PATH=%%a
                        set FILE_DIR=
                        for %%i in ("!FILE_PATH!") do set FILE_DIR=%%~dpi

                        REM Create subdirectories in backup if needed
                        if not "!FILE_DIR!"=="" (
                            if not "!FILE_DIR!"=="." (
                                if not exist "!BACKUP_DIR!\!FILE_DIR!" (
                                    mkdir "!BACKUP_DIR!\!FILE_DIR!" 2>nul
                                )
                            )
                        )

                        REM Copy file to backup
                        copy "%%a" "!BACKUP_DIR!\%%a" >nul 2>&1
                    )
                )

                REM Clean up temp files
                del "!TEMP_LOCAL_CHANGES!" >nul 2>&1
                del "!TEMP_REMOTE_CHANGES!" >nul 2>&1

                if !HAS_CONFLICTS! EQU 1 (
                    echo.
                    echo ========================================
                    echo [Warning] Potential conflicts detected!
                    echo ========================================
                    echo.
                    echo Your modified files may conflict with remote updates.
                    echo Your changes have been backed up to:
                    echo   !BACKUP_DIR!
                    echo.
                    echo Update will restore these files to the remote version.
                    echo You can manually merge your changes later.
                    echo.
                    set /p CONFLICT_CHOICE="Continue with update? (Y/N): "

                    if /i "!CONFLICT_CHOICE!"=="Y" (
                        echo.
                        echo [Restore] Restoring conflicting files to remote version...

                        REM Restore files to HEAD (discard local changes)
                        "%GIT_PORTABLE_PATH%" reset --hard HEAD >nul 2>&1

                        echo [Restore] Files restored. Proceeding with update...
                    ) else (
                        echo.
                        echo Update cancelled.
                        echo Your backup remains at: !BACKUP_DIR!
                        echo.
                        echo ========================================
                        echo Press any key to close...
                        echo ========================================
                        pause >nul
                        exit /b 0
                    )
                ) else (
                    echo.
                    echo [Info] No conflicts detected. Safe to stash and update.
                    echo.
                    set /p STASH_CHOICE="Stash your changes and continue? (Y/N): "
                    if /i "!STASH_CHOICE!"=="Y" (
                        echo Stashing changes...
                        "%GIT_PORTABLE_PATH%" stash push -m "Auto-stash before update - %date% %time%"
                    ) else (
                        echo.
                        echo Update cancelled.
                        echo.
                        echo ========================================
                        echo Press any key to close...
                        echo ========================================
                        pause >nul
                        exit /b 0
                    )
                )
            )

            REM Pull changes
            echo Pulling latest changes...
            "%GIT_PORTABLE_PATH%" pull origin %CURRENT_BRANCH%

            if %ERRORLEVEL% EQU 0 (
                echo.
                echo ========================================
                echo Update completed successfully!
                echo ========================================
                echo.

                REM Check if backup was created
                if defined BACKUP_DIR (
                    if exist "!BACKUP_DIR!" (
                        echo [Important] Your modified files were backed up to:
                        echo   !BACKUP_DIR!
                        echo.
                        echo To restore your changes:
                        echo   1. Run merge_config.bat to compare and merge files
                        echo   2. Or manually compare backup with new version
                        echo.
                        echo Backed up files:
                        for /f "delims=" %%f in ('dir /b /s "!BACKUP_DIR!\*.*" 2^>nul') do (
                            set FILEPATH=%%f
                            set FILEPATH=!FILEPATH:!BACKUP_DIR!\=!
                            echo   - !FILEPATH!
                        )
                        echo.
                    )
                )

                echo Please restart the application to use the new version.
                echo.
                echo ========================================
                echo Press any key to close...
                echo ========================================
                pause >nul
                exit /b 0
            ) else (
                echo.
                echo [Error] Update failed.
                echo Please check the error messages above.

                REM If backup exists, mention it
                if defined BACKUP_DIR (
                    if exist "!BACKUP_DIR!" (
                        echo.
                        echo Your backup is still available at: !BACKUP_DIR!
                    )
                )

                echo.
                echo ========================================
                echo Press any key to close...
                echo ========================================
                pause >nul
                exit /b 1
            )
        ) else (
            echo.
            echo Update skipped.
            echo.
            echo ========================================
            echo Press any key to close...
            echo ========================================
            pause >nul
            exit /b 0
        )
    ) else (
        echo   [Warning] Local version has diverged from remote.
        echo   This might be because you have local commits.
        echo   Please update manually or consult the documentation.
        echo.
        echo ========================================
        echo Press any key to close...
        echo ========================================
        pause >nul
        exit /b 0
    )
)

REM ========================================
REM Function: ConfigureProxy
REM Configure proxy server for git
REM ========================================
:ConfigureProxy
echo.
echo ========================================
echo Proxy Server Configuration
echo ========================================
echo.
echo Please enter your proxy server URL.
echo.
echo Examples:
echo   - HTTP proxy:  http://127.0.0.1:7890
echo   - HTTPS proxy: https://proxy.example.com:8080
echo   - SOCKS5:      socks5://127.0.0.1:1080
echo.
echo Leave empty to disable proxy.
echo.
set /p NEW_PROXY_URL="Proxy URL: "

if "!NEW_PROXY_URL!"=="" (
    echo.
    echo [Proxy] Disabling proxy...

    REM Remove proxy configuration
    "%GIT_PORTABLE_PATH%" config --local --unset http.proxy 2>nul
    "%GIT_PORTABLE_PATH%" config --local --unset https.proxy 2>nul

    REM Update config file
    (
        echo PROXY_ENABLED=0
        echo PROXY_URL=
    ) > "%PROXY_CONFIG_FILE%"

    echo [Proxy] Proxy disabled.
    exit /b 0
) else (
    echo.
    echo [Proxy] Configuring proxy: !NEW_PROXY_URL!

    REM Apply proxy to git
    "%GIT_PORTABLE_PATH%" config --local http.proxy "!NEW_PROXY_URL!"
    "%GIT_PORTABLE_PATH%" config --local https.proxy "!NEW_PROXY_URL!"

    REM Save to config file
    (
        echo PROXY_ENABLED=1
        echo PROXY_URL=!NEW_PROXY_URL!
    ) > "%PROXY_CONFIG_FILE%"

    echo [Proxy] Proxy configured successfully.
    echo [Proxy] Configuration saved to: %PROXY_CONFIG_FILE%
    exit /b 0
)

endlocal
