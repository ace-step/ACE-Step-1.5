@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM AceFlow official launcher - 8 GB VRAM preset ACTIVE
REM ============================================================
REM In AceFlow the service is initialized by the launcher, not by
REM the web UI. So the options below matter before opening the page.
REM
REM This launcher is meant as the safer default for users with about
REM 8 GB VRAM. Advanced users can override values manually.
REM ============================================================

REM ===== venv =====
call "%~dp0venv\Scripts\activate.bat"

REM Always use the venv python explicitly (avoids accidentally using system Python)
set "PY=%~dp0venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

REM ===== environment sane =====
set "PYTHONNOUSERSITE=1"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTORCH_ALLOC_CONF=expandable_segments:True"
set "CUDA_MODULE_LOADING=LAZY"

set "TORCH_LIB=%~dp0venv\Lib\site-packages\torch\lib"
set "PATH=%TORCH_LIB%;%~dp0venv\Scripts;%PATH%"

set "CUDA_BIN=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin"
if exist "%CUDA_BIN%" set "PATH=%CUDA_BIN%;%PATH%"

REM ===== Remote UI config =====
set PORT=7861
set SERVER_NAME=0.0.0.0

REM Main ACE-Step config / DiT preset
set "ACESTEP_REMOTE_CONFIG_PATH=acestep-v15-turbo"

REM LM model path:
REM - 4B = heavier, best for high VRAM
REM - 1.7B = balanced
REM - 0.6B = safer on low VRAM
set "ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-0.6B"

REM Compute device: auto / cuda / cpu
set "ACESTEP_REMOTE_DEVICE=auto"

REM Output directory (optional)
set "ACESTEP_REMOTE_RESULTS_DIR=%~dp0aceflow_outputs"

REM ===== 8 GB VRAM preset ACTIVE =====
REM Initialize the 5Hz LM service at startup
set "ACESTEP_REMOTE_INIT_LLM=1"

REM Try Flash Attention when supported by the environment
set "ACESTEP_REMOTE_USE_FLASH_ATTENTION=1"

REM Offload general model parts to CPU to reduce VRAM pressure
set "ACESTEP_REMOTE_OFFLOAD_TO_CPU=1"

REM Offload DiT to CPU too; slower but safer on limited VRAM
set "ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=1"

REM Enable torch compile / graph optimizations if supported
set "ACESTEP_REMOTE_COMPILE_MODEL=1"

REM Enable INT8 quantization where supported by ACE-Step runtime
set "ACESTEP_REMOTE_INT8_QUANTIZATION=1"

REM Optional LM backend selection (normally leave commented if auto is fine)
set "ACESTEP_REMOTE_LM_BACKEND=pt"

REM Extra safety: offload LM to CPU too
set "ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=1"

REM MLX DiT is for Apple/MLX-oriented setups; keep disabled on Windows/NVIDIA
REM set "ACESTEP_REMOTE_USE_MLX_DIT=0"

REM ===== Alternate presets (examples only) =====
REM ----- Balanced 12-16 GB example -----
REM set "ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-1.7B"
REM set "ACESTEP_REMOTE_OFFLOAD_TO_CPU=0"
REM set "ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=0"
REM set "ACESTEP_REMOTE_INT8_QUANTIZATION=0"
REM set "ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=0"

REM ----- High VRAM / 5090-style example -----
REM set "ACESTEP_REMOTE_LM_MODEL_PATH=acestep-5Hz-lm-4B"
REM set "ACESTEP_REMOTE_USE_FLASH_ATTENTION=1"
REM set "ACESTEP_REMOTE_OFFLOAD_TO_CPU=0"
REM set "ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU=0"
REM set "ACESTEP_REMOTE_COMPILE_MODEL=0"
REM set "ACESTEP_REMOTE_INT8_QUANTIZATION=0"
REM set "ACESTEP_REMOTE_LM_OFFLOAD_TO_CPU=0"

REM ===== AceFlow =====
set "ACEFLOW_AUTH_ENABLED=0"
REM set "ACEFLOW_ADMIN_EMAIL=you@example.com"
REM set "ACEFLOW_ADMIN_PASSWORD=change_me"
set "ACEFLOW_SESSION_SECURE=0"
set "ACEFLOW_BYPASS_CORE_TURBO_STEP_CLAMP=1"
set "ACEFLOW_CLEANUP_TTL_SECONDS=3600"

echo Starting ACE-Step Remote UI...
echo http://%SERVER_NAME%:%PORT%
echo [ACE] PY=%PY% ^| CFG=%ACESTEP_REMOTE_CONFIG_PATH% ^| LM=%ACESTEP_REMOTE_LM_MODEL_PATH%
echo [ACE] INIT_LLM=%ACESTEP_REMOTE_INIT_LLM% ^| OFFLOAD=%ACESTEP_REMOTE_OFFLOAD_TO_CPU% ^| DIT_OFFLOAD=%ACESTEP_REMOTE_OFFLOAD_DIT_TO_CPU% ^| INT8=%ACESTEP_REMOTE_INT8_QUANTIZATION%
echo.

"%PY%" -m acestep.ui.aceflow.run --host %SERVER_NAME% --port %PORT%

pause
endlocal
