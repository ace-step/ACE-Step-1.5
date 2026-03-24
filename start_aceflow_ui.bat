@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM AceFlow Launcher Wizard
REM ============================================================

REM ===== venv =====
if exist "%~dp0.venv\Scripts\activate.bat" (
    call "%~dp0.venv\Scripts\activate.bat" 2>nul
) else if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat" 2>nul
)
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

set "PYTHONNOUSERSITE=1"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTORCH_ALLOC_CONF=expandable_segments:True"
set "CUDA_MODULE_LOADING=LAZY"
if exist "%~dp0.venv\Lib\site-packages\torch\lib" (
    set "TORCH_LIB=%~dp0.venv\Lib\site-packages\torch\lib"
    set "PATH=%TORCH_LIB%;%~dp0.venv\Scripts;%PATH%"
) else (
    set "TORCH_LIB=%~dp0venv\Lib\site-packages\torch\lib"
    set "PATH=%TORCH_LIB%;%~dp0venv\Scripts;%PATH%"
)
set "CUDA_BIN=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin"
if exist "%CUDA_BIN%" set "PATH=%CUDA_BIN%;%PATH%"

set "CFG_FILE=%~dp0.aceflow_last"
if exist "%CFG_FILE%" call "%CFG_FILE%"

if not defined PORT set "PORT=7861"
if not defined SERVER_NAME set "SERVER_NAME=0.0.0.0"
if not defined ACESTEP_REMOTE_CONFIG_PATH set "ACESTEP_REMOTE_CONFIG_PATH=acestep-v15-turbo"
if not defined ACESTEP_REMOTE_LM_MODEL_PATH set "ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-0.6B"
if not defined ACESTEP_REMOTE_DEVICE set "ACESTEP_REMOTE_DEVICE=auto"
if not defined ACESTEP_REMOTE_LM_BACKEND set "ACESTEP_REMOTE_LM_BACKEND=pt"
if not defined ACESTEP_REMOTE_RESULTS_DIR set "ACESTEP_REMOTE_RESULTS_DIR=%~dp0aceflow_outputs"
if not defined ACESTEP_REMOTE_INIT_LLM set "ACESTEP_REMOTE_INIT_LLM=1"
if not defined ACEFLOW_AUTH_ENABLED set "ACEFLOW_AUTH_ENABLED=0"
if not defined ACEFLOW_SESSION_SECURE set "ACEFLOW_SESSION_SECURE=0"
if not defined ACEFLOW_BYPASS_CORE_TURBO_STEP_CLAMP set "ACEFLOW_BYPASS_CORE_TURBO_STEP_CLAMP=1"
if not defined ACEFLOW_CLEANUP_TTL_SECONDS set "ACEFLOW_CLEANUP_TTL_SECONDS=3600"

echo.
echo ============================================
echo AceFlow Launcher Wizard
echo ============================================
echo.
if exist "%CFG_FILE%" (
    echo Configurazione salvata trovata:
    echo   Model:  %ACESTEP_REMOTE_CONFIG_PATH%
    echo   LM:     %ACESTEP_REMOTE_LM_MODEL_PATH%
    echo   Device: %ACESTEP_REMOTE_DEVICE%
    echo   Porta:  %PORT%
    echo.
    set /p "USE_LAST=Usare l'ultima configurazione? [Y/n]: "
    if /i "!USE_LAST!"=="" goto run
    if /i "!USE_LAST!"=="y" goto run
    if /i "!USE_LAST!"=="yes" goto run
)

echo Preset:
echo   1 = 8 GB   ^(offload + int8, LM 0.6B^) [default]
echo   2 = 12-16 GB ^(mix bilanciato, LM 1.7B^)
echo   3 = 24 GB+ ^(no offload, LM 4B^)
echo   C = custom
set /p "PRESET=Scelta [1]: "
if /i "%PRESET%"=="" set "PRESET=1"

if /i "%PRESET%"=="1" (
    set "ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-0.6B"
    set "ACESTEP_REMOTE_OFFLOAD_TO_CPU=1"
    set "ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=1"
    set "ACESTEP_REMOTE_INT8_QUANTIZATION=1"
    set "ACESTEP_REMOTE_COMPILE_MODEL=1"
    set "ACESTEP_REMOTE_USE_FLASH_ATTENTION=1"
    set "ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=1"
    goto ask_common
)
if /i "%PRESET%"=="2" (
    set "ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-1.7B"
    set "ACESTEP_REMOTE_OFFLOAD_TO_CPU=0"
    set "ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=0"
    set "ACESTEP_REMOTE_INT8_QUANTIZATION=0"
    set "ACESTEP_REMOTE_COMPILE_MODEL=0"
    set "ACESTEP_REMOTE_USE_FLASH_ATTENTION=1"
    set "ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=0"
    goto ask_common
)
if /i "%PRESET%"=="3" (
    set "ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-4B"
    set "ACESTEP_REMOTE_OFFLOAD_TO_CPU=0"
    set "ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=0"
    set "ACESTEP_REMOTE_INT8_QUANTIZATION=0"
    set "ACESTEP_REMOTE_COMPILE_MODEL=0"
    set "ACESTEP_REMOTE_USE_FLASH_ATTENTION=1"
    set "ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=0"
    goto ask_common
)

set /p "ACESTEP_REMOTE_CONFIG_PATH=Config DiT [acestep-v15-turbo]: "
if "%ACESTEP_REMOTE_CONFIG_PATH%"=="" set "ACESTEP_REMOTE_CONFIG_PATH=acestep-v15-turbo"
set /p "ACESTEP_REMOTE_LM_MODEL_PATH=LM model [acestep-5Hz-lm-1.7B]: "
if "%ACESTEP_REMOTE_LM_MODEL_PATH%"=="" set "ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-1.7B"
set /p "ACESTEP_REMOTE_DEVICE=Device [auto]: "
if "%ACESTEP_REMOTE_DEVICE%"=="" set "ACESTEP_REMOTE_DEVICE=auto"
set /p "ACESTEP_REMOTE_OFFLOAD_TO_CPU=Offload CPU (0/1) [0]: "
if "%ACESTEP_REMOTE_OFFLOAD_TO_CPU%"=="" set "ACESTEP_REMOTE_OFFLOAD_TO_CPU=0"
set /p "ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=Offload DiT CPU (0/1) [0]: "
if "%ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU%"=="" set "ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=0"
set /p "ACESTEP_REMOTE_INT8_QUANTIZATION=INT8 (0/1) [0]: "
if "%ACESTEP_REMOTE_INT8_QUANTIZATION%"=="" set "ACESTEP_REMOTE_INT8_QUANTIZATION=0"
set /p "ACESTEP_REMOTE_COMPILE_MODEL=Compile model (0/1) [0]: "
if "%ACESTEP_REMOTE_COMPILE_MODEL%"=="" set "ACESTEP_REMOTE_COMPILE_MODEL=0"
set /p "ACESTEP_REMOTE_USE_FLASH_ATTENTION=Flash attention (0/1) [1]: "
if "%ACESTEP_REMOTE_USE_FLASH_ATTENTION%"=="" set "ACESTEP_REMOTE_USE_FLASH_ATTENTION=1"
set /p "ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=LM offload CPU (0/1) [0]: "
if "%ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU%"=="" set "ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=0"

:ask_common
set /p "ACESTEP_REMOTE_DEVICE=Device [auto]: "
if "%ACESTEP_REMOTE_DEVICE%"=="" set "ACESTEP_REMOTE_DEVICE=auto"
set /p "PORT=Porta [7861]: "
if "%PORT%"=="" set "PORT=7861"
set /p "SERVER_NAME=Bind address [0.0.0.0]: "
if "%SERVER_NAME%"=="" set "SERVER_NAME=0.0.0.0"
set /p "ACESTEP_REMOTE_LORA_ROOT=LoRA root opzionale [invio per auto]: "
if "%ACESTEP_REMOTE_LORA_ROOT%"=="" set "ACESTEP_REMOTE_LORA_ROOT="

> "%CFG_FILE%" (
  echo @echo off
  echo set "PORT=%PORT%"
  echo set "SERVER_NAME=%SERVER_NAME%"
  echo set "ACESTEP_REMOTE_CONFIG_PATH=%ACESTEP_REMOTE_CONFIG_PATH%"
  echo set "ACESTEP_REMOTE_LM_MODEL_PATH=%ACESTEP_REMOTE_LM_MODEL_PATH%"
  echo set "ACESTEP_REMOTE_DEVICE=%ACESTEP_REMOTE_DEVICE%"
  echo set "ACESTEP_REMOTE_LM_BACKEND=%ACESTEP_REMOTE_LM_BACKEND%"
  echo set "ACESTEP_REMOTE_RESULTS_DIR=%ACESTEP_REMOTE_RESULTS_DIR%"
  echo set "ACESTEP_REMOTE_INIT_LLM=%ACESTEP_REMOTE_INIT_LLM%"
  echo set "ACESTEP_REMOTE_OFFLOAD_TO_CPU=%ACESTEP_REMOTE_OFFLOAD_TO_CPU%"
  echo set "ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=%ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU%"
  echo set "ACESTEP_REMOTE_INT8_QUANTIZATION=%ACESTEP_REMOTE_INT8_QUANTIZATION%"
  echo set "ACESTEP_REMOTE_COMPILE_MODEL=%ACESTEP_REMOTE_COMPILE_MODEL%"
  echo set "ACESTEP_REMOTE_USE_FLASH_ATTENTION=%ACESTEP_REMOTE_USE_FLASH_ATTENTION%"
  echo set "ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=%ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU%"
  echo set "ACESTEP_REMOTE_LORA_ROOT=%ACESTEP_REMOTE_LORA_ROOT%"
  echo set "ACEFLOW_AUTH_ENABLED=%ACEFLOW_AUTH_ENABLED%"
  echo set "ACEFLOW_SESSION_SECURE=%ACEFLOW_SESSION_SECURE%"
  echo set "ACEFLOW_BYPASS_CORE_TURBO_STEP_CLAMP=%ACEFLOW_BYPASS_CORE_TURBO_STEP_CLAMP%"
  echo set "ACEFLOW_CLEANUP_TTL_SECONDS=%ACEFLOW_CLEANUP_TTL_SECONDS%"
)

:run
echo.
echo Starting ACE-Step Remote UI...
echo http://%SERVER_NAME%:%PORT%/
"%PY%" -m uvicorn acestep.ui.aceflow.app:create_app --factory --host %SERVER_NAME% --port %PORT%