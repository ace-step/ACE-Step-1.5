"""FastAPI server for ACE-Step V1.5.

Endpoints:
- POST /release_task          Create music generation task
- POST /query_result          Batch query task results
- POST /create_random_sample  Generate random music parameters via LLM
- POST /format_input          Format and enhance lyrics/caption via LLM
- GET  /v1/models             List available models
- GET  /v1/audio              Download audio file
- GET  /health                Health check

NOTE:
- In-memory queue and job store -> run uvicorn with workers=1.
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import sys
import time
import traceback
import urllib.parse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import partial
from threading import Lock
from typing import Any, Dict, List, Optional
import torch
from loguru import logger

try:
    from dotenv import load_dotenv
except ImportError:  # Optional dependency
    load_dotenv = None  # type: ignore

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import UploadFile as StarletteUploadFile
from acestep.api.train_api_service import (
    initialize_training_state,
    register_training_api_routes,
)
from acestep.api.jobs.store import _JobStore
from acestep.api.log_capture import install_log_capture
from acestep.api.server_utils import (
    env_bool as _env_bool,
    get_model_name as _get_model_name,
    is_instrumental as _is_instrumental,
    map_status as _map_status,
    parse_description_hints as _parse_description_hints,
    parse_timesteps as _parse_timesteps,
)
from acestep.api.http.auth import (
    set_api_key,
    verify_api_key,
    verify_token_from_request,
)
from acestep.api.http.lora_routes import register_lora_routes
from acestep.api.http.model_service_routes import register_model_service_routes
from acestep.api.http.reinitialize_route import register_reinitialize_route
from acestep.api.http.sample_format_routes import register_sample_format_routes
from acestep.api.http.audio_route import register_audio_route
from acestep.api.http.release_task_audio_paths import (
    save_upload_to_temp as _save_upload_to_temp,
    validate_audio_path as _validate_audio_path,
)
from acestep.api.http.release_task_models import GenerateMusicRequest
from acestep.api.http.release_task_param_parser import (
    RequestParser,
    _to_float as _request_to_float,
    _to_int as _request_to_int,
)
from acestep.api.http.query_result_route import register_query_result_route
from acestep.api.http.release_task_route import register_release_task_route
from acestep.api.jobs.local_cache_updates import (
    update_local_cache,
    update_local_cache_progress,
)
from acestep.api.jobs.worker_loops import (
    process_queue_item,
    run_job_store_cleanup_loop,
)
from acestep.api.runtime_helpers import (
    append_jsonl as _runtime_append_jsonl,
    atomic_write_json as _runtime_atomic_write_json,
    start_tensorboard as _runtime_start_tensorboard,
    stop_tensorboard as _runtime_stop_tensorboard,
    temporary_llm_model as _runtime_temporary_llm_model,
)
from acestep.api.model_download import (
    ensure_model_downloaded as _ensure_model_downloaded,
)

from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.constants import (
    DEFAULT_DIT_INSTRUCTION,
    TASK_INSTRUCTIONS,
)
from acestep.inference import (
    GenerationParams,
    GenerationConfig,
    generate_music,
    create_sample,
    format_sample,
)
from acestep.ui.gradio.events.results_handlers import _build_generation_info
from acestep.gpu_config import (
    get_gpu_config,
    set_global_gpu_config,
    get_recommended_lm_model,
    is_lm_model_supported,
    VRAM_AUTO_OFFLOAD_THRESHOLD_GB,
)

def _get_project_root() -> str:
    current_file = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(current_file))


# =============================================================================
# Constants
# =============================================================================

RESULT_KEY_PREFIX = "ace_step_v1.5_"
RESULT_EXPIRE_SECONDS = 7 * 24 * 60 * 60  # 7 days
TASK_TIMEOUT_SECONDS = 3600  # 1 hour
JOB_STORE_CLEANUP_INTERVAL = 300  # 5 minutes - interval for cleaning up old jobs
JOB_STORE_MAX_AGE_SECONDS = 86400  # 24 hours - completed jobs older than this will be cleaned

LM_DEFAULT_TEMPERATURE = 0.85
LM_DEFAULT_CFG_SCALE = 2.5
LM_DEFAULT_TOP_P = 0.9


def _wrap_response(data: Any, code: int = 200, error: Optional[str] = None) -> Dict[str, Any]:
    """Wrap response data in standard format."""
    return {
        "data": data,
        "code": code,
        "error": error,
        "timestamp": int(time.time() * 1000),
        "extra": None,
    }


# =============================================================================
# Example Data for Random Sample
# =============================================================================

SIMPLE_MODE_EXAMPLES_DIR = os.path.join(_get_project_root(), "examples", "simple_mode")
CUSTOM_MODE_EXAMPLES_DIR = os.path.join(_get_project_root(), "examples", "text2music")


def _load_all_examples(sample_mode: str = "simple_mode") -> List[Dict[str, Any]]:
    """Load all example data files from the examples directory."""
    examples = []
    examples_dir = SIMPLE_MODE_EXAMPLES_DIR if sample_mode == "simple_mode" else CUSTOM_MODE_EXAMPLES_DIR
    pattern = os.path.join(examples_dir, "example_*.json")

    for filepath in glob.glob(pattern):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                examples.append(data)
        except Exception as e:
            print(f"[API Server] Failed to load example file {filepath}: {e}")

    return examples


# Pre-load example data at module load time
SIMPLE_EXAMPLE_DATA: List[Dict[str, Any]] = _load_all_examples(sample_mode="simple_mode")
CUSTOM_EXAMPLE_DATA: List[Dict[str, Any]] = _load_all_examples(sample_mode="custom_mode")


_project_env_loaded = False


def _load_project_env() -> None:
    """Load .env at most once per process to avoid epoch-boundary stalls (e.g. Windows LoRA training)."""
    global _project_env_loaded
    if _project_env_loaded or load_dotenv is None:
        return
    try:
        project_root = _get_project_root()
        env_path = os.path.join(project_root, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)
        _project_env_loaded = True
    except Exception:
        # Optional best-effort: continue even if .env loading fails.
        pass


_load_project_env()


log_buffer, _stderr_proxy = install_log_capture(logger, sys.stderr)
sys.stderr = _stderr_proxy


def create_app() -> FastAPI:
    store = _JobStore()

    # API Key authentication (from environment variable)
    api_key = os.getenv("ACESTEP_API_KEY", None)
    set_api_key(api_key)

    QUEUE_MAXSIZE = int(os.getenv("ACESTEP_QUEUE_MAXSIZE", "200"))
    WORKER_COUNT = int(os.getenv("ACESTEP_QUEUE_WORKERS", "1"))  # Single GPU recommended

    INITIAL_AVG_JOB_SECONDS = float(os.getenv("ACESTEP_AVG_JOB_SECONDS", "5.0"))
    AVG_WINDOW = int(os.getenv("ACESTEP_AVG_WINDOW", "50"))

    def _path_to_audio_url(path: str) -> str:
        """Convert local file path to downloadable relative URL"""
        if not path:
            return path
        if path.startswith("http://") or path.startswith("https://"):
            return path
        encoded_path = urllib.parse.quote(path, safe="")
        return f"/v1/audio?path={encoded_path}"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Clear proxy env that may affect downstream libs
        for proxy_var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
            os.environ.pop(proxy_var, None)

        # Ensure compilation/temp caches do not fill up small default /tmp.
        # Triton/Inductor (and the system compiler) can create large temporary files.
        project_root = _get_project_root()
        cache_root = os.path.join(project_root, ".cache", "acestep")
        tmp_root = (os.getenv("ACESTEP_TMPDIR") or os.path.join(cache_root, "tmp")).strip()
        triton_cache_root = (os.getenv("TRITON_CACHE_DIR") or os.path.join(cache_root, "triton")).strip()
        inductor_cache_root = (os.getenv("TORCHINDUCTOR_CACHE_DIR") or os.path.join(cache_root, "torchinductor")).strip()

        for p in [cache_root, tmp_root, triton_cache_root, inductor_cache_root]:
            try:
                os.makedirs(p, exist_ok=True)
            except Exception:
                # Best-effort: do not block startup if directory creation fails.
                pass

        # Respect explicit user overrides; if ACESTEP_TMPDIR is set, it should win.
        if os.getenv("ACESTEP_TMPDIR"):
            os.environ["TMPDIR"] = tmp_root
            os.environ["TEMP"] = tmp_root
            os.environ["TMP"] = tmp_root
        else:
            os.environ.setdefault("TMPDIR", tmp_root)
            os.environ.setdefault("TEMP", tmp_root)
            os.environ.setdefault("TMP", tmp_root)

        os.environ.setdefault("TRITON_CACHE_DIR", triton_cache_root)
        os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", inductor_cache_root)

        handler = AceStepHandler()
        llm_handler = LLMHandler()
        init_lock = asyncio.Lock()
        app.state._initialized = False
        app.state._init_error = None
        app.state._init_lock = init_lock

        app.state.llm_handler = llm_handler
        app.state._llm_initialized = False
        app.state._llm_init_error = None
        app.state._llm_init_lock = Lock()
        app.state._llm_lazy_load_disabled = False  # Will be set to True if LLM skipped due to GPU config

        # Multi-model support: secondary DiT handlers
        handler2 = None
        handler3 = None
        config_path2 = os.getenv("ACESTEP_CONFIG_PATH2", "").strip()
        config_path3 = os.getenv("ACESTEP_CONFIG_PATH3", "").strip()

        if config_path2:
            handler2 = AceStepHandler()
        if config_path3:
            handler3 = AceStepHandler()

        app.state.handler2 = handler2
        app.state.handler3 = handler3
        app.state._initialized2 = False
        app.state._initialized3 = False
        app.state._config_path = os.getenv("ACESTEP_CONFIG_PATH", "acestep-v15-turbo")
        app.state._config_path2 = config_path2
        app.state._config_path3 = config_path3

        max_workers = int(os.getenv("ACESTEP_API_WORKERS", "1"))
        executor = ThreadPoolExecutor(max_workers=max_workers)

        # Queue & observability
        app.state.job_queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)  # (job_id, req)
        app.state.pending_ids = deque()  # queued job_ids
        app.state.pending_lock = asyncio.Lock()

        # temp files per job (from multipart uploads)
        app.state.job_temp_files = {}  # job_id -> list[path]
        app.state.job_temp_files_lock = asyncio.Lock()

        # stats
        app.state.stats_lock = asyncio.Lock()
        app.state.recent_durations = deque(maxlen=AVG_WINDOW)
        app.state.avg_job_seconds = INITIAL_AVG_JOB_SECONDS

        app.state.handler = handler
        app.state.executor = executor
        app.state.job_store = store
        app.state._python_executable = sys.executable
        initialize_training_state(app)

        # Temporary directory for saving generated audio files
        app.state.temp_audio_dir = os.path.join(tmp_root, "api_audio")
        os.makedirs(app.state.temp_audio_dir, exist_ok=True)

        # Initialize local cache
        try:
            from acestep.local_cache import get_local_cache
            local_cache_dir = os.path.join(cache_root, "local_redis")
            app.state.local_cache = get_local_cache(local_cache_dir)
        except ImportError:
            app.state.local_cache = None

        async def _ensure_initialized() -> None:
            """Check if models are initialized (they should be loaded at startup)."""
            if getattr(app.state, "_init_error", None):
                raise RuntimeError(app.state._init_error)
            if not getattr(app.state, "_initialized", False):
                raise RuntimeError("Model not initialized")

        async def _cleanup_job_temp_files(job_id: str) -> None:
            async with app.state.job_temp_files_lock:
                paths = app.state.job_temp_files.pop(job_id, [])
            for p in paths:
                try:
                    os.remove(p)
                except Exception:
                    pass

        def _update_local_cache(job_id: str, result: Optional[Dict], status: str) -> None:
            """Update local cache with terminal job state payload."""

            update_local_cache(
                local_cache=getattr(app.state, "local_cache", None),
                store=store,
                job_id=job_id,
                result=result,
                status=status,
                map_status=_map_status,
                result_key_prefix=RESULT_KEY_PREFIX,
                result_expire_seconds=RESULT_EXPIRE_SECONDS,
            )

        def _update_local_cache_progress(job_id: str, progress: float, stage: str) -> None:
            """Update local cache with queued/running progress payload."""

            update_local_cache_progress(
                local_cache=getattr(app.state, "local_cache", None),
                store=store,
                job_id=job_id,
                progress=progress,
                stage=stage,
                map_status=_map_status,
                result_key_prefix=RESULT_KEY_PREFIX,
                result_expire_seconds=RESULT_EXPIRE_SECONDS,
            )

        async def _run_one_job(job_id: str, req: GenerateMusicRequest) -> None:
            job_store: _JobStore = app.state.job_store
            llm: LLMHandler = app.state.llm_handler
            executor: ThreadPoolExecutor = app.state.executor

            await _ensure_initialized()
            job_store.mark_running(job_id)
            _update_local_cache_progress(job_id, 0.01, "running")

            # Select DiT handler based on user's model choice
            # Default: use primary handler
            selected_handler: AceStepHandler = app.state.handler
            selected_model_name = _get_model_name(app.state._config_path)

            if req.model:
                model_matched = False

                # Check if it matches the second model
                if app.state.handler2 and getattr(app.state, "_initialized2", False):
                    model2_name = _get_model_name(app.state._config_path2)
                    if req.model == model2_name:
                        selected_handler = app.state.handler2
                        selected_model_name = model2_name
                        model_matched = True
                        print(f"[API Server] Job {job_id}: Using second model: {model2_name}")

                # Check if it matches the third model
                if not model_matched and app.state.handler3 and getattr(app.state, "_initialized3", False):
                    model3_name = _get_model_name(app.state._config_path3)
                    if req.model == model3_name:
                        selected_handler = app.state.handler3
                        selected_model_name = model3_name
                        model_matched = True
                        print(f"[API Server] Job {job_id}: Using third model: {model3_name}")

                if not model_matched:
                    available_models = [_get_model_name(app.state._config_path)]
                    if app.state.handler2 and getattr(app.state, "_initialized2", False):
                        available_models.append(_get_model_name(app.state._config_path2))
                    if app.state.handler3 and getattr(app.state, "_initialized3", False):
                        available_models.append(_get_model_name(app.state._config_path3))
                    print(f"[API Server] Job {job_id}: Model '{req.model}' not found in {available_models}, using primary: {selected_model_name}")

            # Use selected handler for generation
            h: AceStepHandler = selected_handler

            def _blocking_generate() -> Dict[str, Any]:
                """Generate music using unified inference logic from acestep.inference"""

                def _ensure_llm_ready() -> None:
                    """Ensure LLM handler is initialized when needed"""
                    with app.state._llm_init_lock:
                        initialized = getattr(app.state, "_llm_initialized", False)
                        had_error = getattr(app.state, "_llm_init_error", None)
                        if initialized or had_error is not None:
                            return
                        print("[API Server] reloading.")

                        # Check if lazy loading is disabled (GPU memory insufficient)
                        if getattr(app.state, "_llm_lazy_load_disabled", False):
                            app.state._llm_init_error = (
                                "LLM not initialized at startup. To enable LLM, set ACESTEP_INIT_LLM=true "
                                "in .env or environment variables. For this request, optional LLM features "
                                "(use_cot_caption, use_cot_language) will be auto-disabled."
                            )
                            print("[API Server] LLM lazy load blocked: LLM was not initialized at startup")
                            return

                        # Respect ACESTEP_INIT_LLM=false even in lazy-load / --no-init mode
                        init_llm_env = os.getenv("ACESTEP_INIT_LLM", "").strip().lower()
                        if init_llm_env in {"0", "false", "no", "n", "off"}:
                            app.state._llm_lazy_load_disabled = True
                            app.state._llm_init_error = (
                                "LLM disabled via ACESTEP_INIT_LLM=false. "
                                "Optional LLM features (use_cot_caption, use_cot_language) will be auto-disabled."
                            )
                            print("[API Server] LLM lazy load blocked: ACESTEP_INIT_LLM=false")
                            return

                        project_root = _get_project_root()
                        checkpoint_dir = os.path.join(project_root, "checkpoints")
                        lm_model_path = (req.lm_model_path or os.getenv("ACESTEP_LM_MODEL_PATH") or "acestep-5Hz-lm-0.6B").strip()
                        backend = (req.lm_backend or os.getenv("ACESTEP_LM_BACKEND") or "vllm").strip().lower()
                        if backend not in {"vllm", "pt", "mlx"}:
                            backend = "vllm"

                        # Auto-download LM model if not present
                        lm_model_name = _get_model_name(lm_model_path)
                        if lm_model_name:
                            try:
                                _ensure_model_downloaded(lm_model_name, checkpoint_dir)
                            except Exception as e:
                                print(f"[API Server] Warning: Failed to download LM model {lm_model_name}: {e}")

                        lm_device = os.getenv("ACESTEP_LM_DEVICE", os.getenv("ACESTEP_DEVICE", "auto"))
                        lm_offload = _env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False)

                        status, ok = llm.initialize(
                            checkpoint_dir=checkpoint_dir,
                            lm_model_path=lm_model_path,
                            backend=backend,
                            device=lm_device,
                            offload_to_cpu=lm_offload,
                            dtype=None,
                        )
                        if not ok:
                            app.state._llm_init_error = status
                        else:
                            app.state._llm_initialized = True

                def _normalize_metas(meta: Dict[str, Any]) -> Dict[str, Any]:
                    """Ensure a stable `metas` dict (keys always present)."""
                    meta = meta or {}
                    out: Dict[str, Any] = dict(meta)

                    # Normalize key aliases
                    if "keyscale" not in out and "key_scale" in out:
                        out["keyscale"] = out.get("key_scale")
                    if "timesignature" not in out and "time_signature" in out:
                        out["timesignature"] = out.get("time_signature")

                    # Ensure required keys exist
                    for k in ["bpm", "duration", "genres", "keyscale", "timesignature"]:
                        if out.get(k) in (None, ""):
                            out[k] = "N/A"
                    return out

                # Normalize LM sampling parameters
                lm_top_k = req.lm_top_k if req.lm_top_k and req.lm_top_k > 0 else 0
                lm_top_p = req.lm_top_p if req.lm_top_p and req.lm_top_p < 1.0 else 0.9

                # Determine if LLM is needed
                thinking = bool(req.thinking)
                sample_mode = bool(req.sample_mode)
                has_sample_query = bool(req.sample_query and req.sample_query.strip())
                use_format = bool(req.use_format)
                use_cot_caption = bool(req.use_cot_caption)
                use_cot_language = bool(req.use_cot_language)

                full_analysis_only = bool(req.full_analysis_only)

                # Unload LM for cover tasks on MPS to reduce memory; reload lazily when needed.
                if req.task_type == "cover" and h.device == "mps":
                    if getattr(app.state, "_llm_initialized", False) and getattr(llm, "llm_initialized", False):
                        try:
                            print("[API Server] unloading.")
                            llm.unload()
                            app.state._llm_initialized = False
                            app.state._llm_init_error = None
                        except Exception as e:
                            print(f"[API Server] Failed to unload LM: {e}")

                # LLM is REQUIRED for these features (fail if unavailable):
                # - thinking mode (LM generates audio codes)
                # - sample_mode (LM generates random caption/lyrics/metas)
                # - sample_query/description (LM generates from description)
                # - use_format (LM enhances caption/lyrics)
                # - full_analysis_only (LM understands audio codes)
                require_llm = thinking or sample_mode or has_sample_query or use_format or full_analysis_only

                # LLM is OPTIONAL for these features (auto-disable if unavailable):
                # - use_cot_caption or use_cot_language (LM enhances metadata)
                want_llm = use_cot_caption or use_cot_language

                # Check if LLM is available
                llm_available = True
                if require_llm or want_llm:
                    _ensure_llm_ready()
                    if getattr(app.state, "_llm_init_error", None):
                        llm_available = False

                # Fail if LLM is required but unavailable
                if require_llm and not llm_available:
                    raise RuntimeError(f"5Hz LM init failed: {app.state._llm_init_error}")

                # Auto-disable optional LLM features if unavailable
                if want_llm and not llm_available:
                    if use_cot_caption or use_cot_language:
                        print(f"[API Server] LLM unavailable, auto-disabling: use_cot_caption={use_cot_caption}->False, use_cot_language={use_cot_language}->False")
                    use_cot_caption = False
                    use_cot_language = False

                # Handle sample mode or description: generate caption/lyrics/metas via LM
                caption = req.prompt
                lyrics = req.lyrics
                bpm = req.bpm
                key_scale = req.key_scale
                time_signature = req.time_signature
                audio_duration = req.audio_duration

                # Save original user input for metas
                original_prompt = req.prompt or ""
                original_lyrics = req.lyrics or ""

                if sample_mode or has_sample_query:
                    # Parse description hints from sample_query (if provided)
                    sample_query = req.sample_query if has_sample_query else "NO USER INPUT"
                    parsed_language, parsed_instrumental = _parse_description_hints(sample_query)

                    # Determine vocal_language with priority:
                    # 1. User-specified vocal_language (if not default "en")
                    # 2. Language parsed from description
                    # 3. None (no constraint)
                    if req.vocal_language and req.vocal_language not in ("en", "unknown", ""):
                        sample_language = req.vocal_language
                    else:
                        sample_language = parsed_language

                    sample_result = create_sample(
                        llm_handler=llm,
                        query=sample_query,
                        instrumental=parsed_instrumental,
                        vocal_language=sample_language,
                        temperature=req.lm_temperature,
                        top_k=lm_top_k if lm_top_k > 0 else None,
                        top_p=lm_top_p if lm_top_p < 1.0 else None,
                        use_constrained_decoding=True,
                    )

                    if not sample_result.success:
                        raise RuntimeError(f"create_sample failed: {sample_result.error or sample_result.status_message}")

                    # Use generated sample data
                    caption = sample_result.caption
                    lyrics = sample_result.lyrics
                    bpm = sample_result.bpm
                    key_scale = sample_result.keyscale
                    time_signature = sample_result.timesignature
                    audio_duration = sample_result.duration

                # Apply format_sample() if use_format is True and caption/lyrics are provided
                format_has_duration = False

                if req.use_format and (caption or lyrics):
                    _ensure_llm_ready()
                    if getattr(app.state, "_llm_init_error", None):
                        raise RuntimeError(f"5Hz LM init failed (needed for format): {app.state._llm_init_error}")

                    # Build user_metadata from request params (matching bot.py behavior)
                    user_metadata_for_format = {}
                    if bpm is not None:
                        user_metadata_for_format['bpm'] = bpm
                    if audio_duration is not None and float(audio_duration) > 0:
                        user_metadata_for_format['duration'] = float(audio_duration)
                    if key_scale:
                        user_metadata_for_format['keyscale'] = key_scale
                    if time_signature:
                        user_metadata_for_format['timesignature'] = time_signature
                    if req.vocal_language and req.vocal_language != "unknown":
                        user_metadata_for_format['language'] = req.vocal_language

                    format_result = format_sample(
                        llm_handler=llm,
                        caption=caption,
                        lyrics=lyrics,
                        user_metadata=user_metadata_for_format if user_metadata_for_format else None,
                        temperature=req.lm_temperature,
                        top_k=lm_top_k if lm_top_k > 0 else None,
                        top_p=lm_top_p if lm_top_p < 1.0 else None,
                        use_constrained_decoding=True,
                    )

                    if format_result.success:
                        # Extract all formatted data (matching bot.py behavior)
                        caption = format_result.caption or caption
                        lyrics = format_result.lyrics or lyrics
                        if format_result.duration:
                            audio_duration = format_result.duration
                            format_has_duration = True
                        if format_result.bpm:
                            bpm = format_result.bpm
                        if format_result.keyscale:
                            key_scale = format_result.keyscale
                        if format_result.timesignature:
                            time_signature = format_result.timesignature

                # Parse timesteps string to list of floats if provided
                parsed_timesteps = _parse_timesteps(req.timesteps)

                # Auto-select instruction based on task_type if user didn't provide custom instruction
                # This matches gradio behavior which uses TASK_INSTRUCTIONS for each task type
                instruction_to_use = req.instruction
                if instruction_to_use == DEFAULT_DIT_INSTRUCTION and req.task_type in TASK_INSTRUCTIONS:
                    raw_instruction = TASK_INSTRUCTIONS[req.task_type]

                    if req.task_type == "complete":
                         #  Use track_classes joined by pipes
                         if req.track_classes:
                             # Join list items: ["Drums", "Bass"] -> "DRUMS | BASS"
                             classes_str = " | ".join([str(t).upper() for t in req.track_classes])
                             # Use the raw instruction template from constants
                             # Format: "Complete the track with {TRACK_CLASSES}:"
                             instruction_to_use = raw_instruction.format(TRACK_CLASSES=classes_str)
                         else:
                             # Fallback if no classes provided
                             instruction_to_use = TASK_INSTRUCTIONS.get("complete_default", raw_instruction)

                    elif "{TRACK_NAME}" in raw_instruction and req.track_name:
                        # Logic for extract/lego
                        instruction_to_use = raw_instruction.format(TRACK_NAME=req.track_name.upper())
                    else:
                        instruction_to_use = raw_instruction

                # Build GenerationParams using unified interface
                # Note: thinking controls LM code generation, sample_mode only affects CoT metas
                params = GenerationParams(
                    task_type=req.task_type,
                    instruction=instruction_to_use,
                    reference_audio=req.reference_audio_path,
                    src_audio=req.src_audio_path,
                    audio_codes="",
                    caption=caption,
                    lyrics=lyrics,
                    instrumental=_is_instrumental(lyrics),
                    vocal_language=req.vocal_language,
                    bpm=bpm,
                    keyscale=key_scale,
                    timesignature=time_signature,
                    duration=audio_duration if audio_duration else -1.0,
                    inference_steps=req.inference_steps,
                    seed=req.seed,
                    guidance_scale=req.guidance_scale,
                    use_adg=req.use_adg,
                    cfg_interval_start=req.cfg_interval_start,
                    cfg_interval_end=req.cfg_interval_end,
                    shift=req.shift,
                    infer_method=req.infer_method,
                    timesteps=parsed_timesteps,
                    repainting_start=req.repainting_start,
                    repainting_end=req.repainting_end if req.repainting_end else -1,
                    audio_cover_strength=req.audio_cover_strength,
                    # LM parameters
                    thinking=thinking,  # Use LM for code generation when thinking=True
                    lm_temperature=req.lm_temperature,
                    lm_cfg_scale=req.lm_cfg_scale,
                    lm_top_k=lm_top_k,
                    lm_top_p=lm_top_p,
                    lm_negative_prompt=req.lm_negative_prompt,
                    # use_cot_metas logic:
                    # - sample_mode: metas already generated, skip Phase 1
                    # - format with duration: metas already generated, skip Phase 1
                    # - format without duration: need Phase 1 to generate duration
                    # - no format: need Phase 1 to generate all metas
                    use_cot_metas=not sample_mode and not format_has_duration,
                    use_cot_caption=use_cot_caption,  # Use local var (may be auto-disabled)
                    use_cot_language=use_cot_language,  # Use local var (may be auto-disabled)
                    use_constrained_decoding=True,
                )

                # Build GenerationConfig - default to 2 audios like gradio_ui
                batch_size = req.batch_size if req.batch_size is not None else 2

                # Resolve seed(s) from req.seed into List[int] for GenerationConfig.seeds
                resolved_seeds = None
                if not req.use_random_seed and req.seed is not None:
                    if isinstance(req.seed, int):
                        if req.seed >= 0:
                            resolved_seeds = [req.seed]
                    elif isinstance(req.seed, str):
                        resolved_seeds = []
                        for s in req.seed.split(","):
                            s = s.strip()
                            if s and s != "-1":
                                try:
                                    resolved_seeds.append(int(float(s)))
                                except (ValueError, TypeError):
                                    pass
                        if not resolved_seeds:
                            resolved_seeds = None

                config = GenerationConfig(
                    batch_size=batch_size,
                    allow_lm_batch=req.allow_lm_batch,
                    use_random_seed=req.use_random_seed,
                    seeds=resolved_seeds,
                    audio_format=req.audio_format,
                    constrained_decoding_debug=req.constrained_decoding_debug,
                )

                # Check LLM initialization status
                llm_is_initialized = getattr(app.state, "_llm_initialized", False)
                llm_to_pass = llm if llm_is_initialized else None

                # Progress callback for API polling
                last_progress = {"value": -1.0, "time": 0.0, "stage": ""}

                def _progress_cb(value: float, desc: str = "") -> None:
                    now = time.time()
                    try:
                        value_f = max(0.0, min(1.0, float(value)))
                    except Exception:
                        value_f = 0.0
                    stage = desc or last_progress["stage"] or "running"
                    # Throttle updates to avoid excessive cache writes
                    if (
                        value_f - last_progress["value"] >= 0.01
                        or stage != last_progress["stage"]
                        or (now - last_progress["time"]) >= 0.5
                    ):
                        last_progress["value"] = value_f
                        last_progress["time"] = now
                        last_progress["stage"] = stage
                        job_store.update_progress(job_id, value_f, stage=stage)
                        _update_local_cache_progress(job_id, value_f, stage)

                if req.full_analysis_only:
                    store.update_progress_text(job_id, "Starting Deep Analysis...")
                    # Step A: Convert source audio to semantic codes
                    # We use params.src_audio which is the server-side path
                    audio_codes = h.convert_src_audio_to_codes(params.src_audio)

                    if not audio_codes or audio_codes.startswith("❌"):
                        raise RuntimeError(f"Audio encoding failed: {audio_codes}")

                    # Step B: LLM Understanding of those specific codes
                    # This yields the deep metadata and lyrics transcription
                    metadata_dict, status_string = llm_to_pass.understand_audio_from_codes(
                        audio_codes=audio_codes,
                        temperature=0.3,
                        use_constrained_decoding=True,
                        constrained_decoding_debug=config.constrained_decoding_debug
                    )

                    if not metadata_dict:
                        raise RuntimeError(f"LLM Understanding failed: {status_string}")

                    return {
                        "status_message": "Full Hardware Analysis Success",
                        "bpm": metadata_dict.get("bpm"),
                        "keyscale": metadata_dict.get("keyscale"),
                        "timesignature": metadata_dict.get("timesignature"),
                        "duration": metadata_dict.get("duration"),
                        "genre": metadata_dict.get("genres") or metadata_dict.get("genre"),
                        "prompt": metadata_dict.get("caption", ""),
                        "lyrics": metadata_dict.get("lyrics", ""),
                        "language": metadata_dict.get("language", "unknown"),
                        "metas": metadata_dict,
                        "audio_paths": []
                    }

                if req.analysis_only:
                    lm_res = llm_to_pass.generate_with_stop_condition(
                        caption=params.caption,
                        lyrics=params.lyrics,
                        infer_type="dit",
                        temperature=req.lm_temperature,
                        top_p=req.lm_top_p,
                        use_cot_metas=True,
                        use_cot_caption=req.use_cot_caption,
                        use_cot_language=req.use_cot_language,
                        use_constrained_decoding=True
                    )

                    if not lm_res.get("success"):
                        raise RuntimeError(f"Analysis Failed: {lm_res.get('error')}")

                    metas_found = lm_res.get("metadata", {})
                    return {
                        "first_audio_path": None,
                        "audio_paths": [],
                        "raw_audio_paths": [],
                        "generation_info": "Analysis Only Mode Complete",
                        "status_message": "Success",
                        "metas": metas_found,
                        "bpm": metas_found.get("bpm"),
                        "keyscale": metas_found.get("keyscale"),
                        "duration": metas_found.get("duration"),
                        "prompt": metas_found.get("caption", params.caption),
                        "lyrics": params.lyrics,
                        "lm_model": os.getenv("ACESTEP_LM_MODEL_PATH", ""),
                        "dit_model": "None (Analysis Only)"
                    }

                # Generate music using unified interface
                sequential_runs = 1
                if req.task_type == "cover" and h.device == "mps":
                    # If user asked for multiple outputs, run sequentially on MPS to avoid OOM.
                    if config.batch_size is not None and config.batch_size > 1:
                        sequential_runs = int(config.batch_size)
                        config.batch_size = 1
                        print(f"[API Server] Job {job_id}: MPS cover sequential mode enabled (runs={sequential_runs})")

                def _progress_for_slice(start: float, end: float):
                    base = {"seen": False, "value": 0.0}
                    def _cb(value: float, desc: str = "") -> None:
                        try:
                            value_f = max(0.0, min(1.0, float(value)))
                        except Exception:
                            value_f = 0.0
                        if not base["seen"]:
                            base["seen"] = True
                            base["value"] = value_f
                        # Normalize progress to avoid initial jump (e.g., 0.51 -> 0.0)
                        if value_f <= base["value"]:
                            norm = 0.0
                        else:
                            denom = max(1e-6, 1.0 - base["value"])
                            norm = min(1.0, (value_f - base["value"]) / denom)
                        mapped = start + (end - start) * norm
                        _progress_cb(mapped, desc=desc)
                    return _cb

                aggregated_result = None
                all_audios: List[Dict[str, Any]] = []
                for run_idx in range(sequential_runs):
                    if sequential_runs > 1:
                        print(f"[API Server] Job {job_id}: Sequential cover run {run_idx + 1}/{sequential_runs}")
                    if sequential_runs > 1:
                        start = run_idx / sequential_runs
                        end = (run_idx + 1) / sequential_runs
                        progress_cb = _progress_for_slice(start, end)
                    else:
                        progress_cb = _progress_cb

                    result = generate_music(
                        dit_handler=h,
                        llm_handler=llm_to_pass,
                        params=params,
                        config=config,
                        save_dir=app.state.temp_audio_dir,
                        progress=progress_cb,
                    )
                    if not result.success:
                        raise RuntimeError(f"Music generation failed: {result.error or result.status_message}")

                    if aggregated_result is None:
                        aggregated_result = result
                    all_audios.extend(result.audios)

                # Use aggregated result with combined audios
                if aggregated_result is None:
                    raise RuntimeError("Music generation failed: no results")
                aggregated_result.audios = all_audios
                result = aggregated_result

                if not result.success:
                    raise RuntimeError(f"Music generation failed: {result.error or result.status_message}")

                # Extract results
                audio_paths = [audio["path"] for audio in result.audios if audio.get("path")]
                first_audio = audio_paths[0] if len(audio_paths) > 0 else None
                second_audio = audio_paths[1] if len(audio_paths) > 1 else None

                # Get metadata from LM or CoT results
                lm_metadata = result.extra_outputs.get("lm_metadata", {})
                metas_out = _normalize_metas(lm_metadata)

                # Update metas with actual values used
                if params.cot_bpm:
                    metas_out["bpm"] = params.cot_bpm
                elif bpm:
                    metas_out["bpm"] = bpm

                if params.cot_duration:
                    metas_out["duration"] = params.cot_duration
                elif audio_duration:
                    metas_out["duration"] = audio_duration

                if params.cot_keyscale:
                    metas_out["keyscale"] = params.cot_keyscale
                elif key_scale:
                    metas_out["keyscale"] = key_scale

                if params.cot_timesignature:
                    metas_out["timesignature"] = params.cot_timesignature
                elif time_signature:
                    metas_out["timesignature"] = time_signature

                # Store original user input in metas (not the final/modified values)
                metas_out["prompt"] = original_prompt
                metas_out["lyrics"] = original_lyrics

                # Extract seed values for response (comma-separated for multiple audios)
                seed_values = []
                for audio in result.audios:
                    audio_params = audio.get("params", {})
                    seed = audio_params.get("seed")
                    if seed is not None:
                        seed_values.append(str(seed))
                seed_value = ",".join(seed_values) if seed_values else ""

                # Build generation_info using the helper function (like gradio_ui)
                time_costs = result.extra_outputs.get("time_costs", {})
                generation_info = _build_generation_info(
                    lm_metadata=lm_metadata,
                    time_costs=time_costs,
                    seed_value=seed_value,
                    inference_steps=req.inference_steps,
                    num_audios=len(result.audios),
                )

                def _none_if_na_str(v: Any) -> Optional[str]:
                    if v is None:
                        return None
                    s = str(v).strip()
                    if s in {"", "N/A"}:
                        return None
                    return s

                # Get model information
                lm_model_name = os.getenv("ACESTEP_LM_MODEL_PATH", "acestep-5Hz-lm-0.6B")
                # Use selected_model_name (set at the beginning of _run_one_job)
                dit_model_name = selected_model_name

                return {
                    "first_audio_path": _path_to_audio_url(first_audio) if first_audio else None,
                    "second_audio_path": _path_to_audio_url(second_audio) if second_audio else None,
                    "audio_paths": [_path_to_audio_url(p) for p in audio_paths],
                    "raw_audio_paths": list(audio_paths),
                    "generation_info": generation_info,
                    "status_message": result.status_message,
                    "seed_value": seed_value,
                    # Final prompt/lyrics (may be modified by thinking/format)
                    "prompt": caption or "",
                    "lyrics": lyrics or "",
                    # metas contains original user input + other metadata
                    "metas": metas_out,
                    "bpm": metas_out.get("bpm") if isinstance(metas_out.get("bpm"), int) else None,
                    "duration": metas_out.get("duration") if isinstance(metas_out.get("duration"), (int, float)) else None,
                    "genres": _none_if_na_str(metas_out.get("genres")),
                    "keyscale": _none_if_na_str(metas_out.get("keyscale")),
                    "timesignature": _none_if_na_str(metas_out.get("timesignature")),
                    "lm_model": lm_model_name,
                    "dit_model": dit_model_name,
                }

            t0 = time.time()
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(executor, _blocking_generate)
                job_store.mark_succeeded(job_id, result)

                # Update local cache
                _update_local_cache(job_id, result, "succeeded")
            except Exception as e:
                error_traceback = traceback.format_exc()
                print(f"[API Server] Job {job_id} FAILED: {e}")
                print(f"[API Server] Traceback:\n{error_traceback}")
                job_store.mark_failed(job_id, error_traceback)

                # Update local cache
                _update_local_cache(job_id, None, "failed")
            finally:
                # Best-effort cache cleanup to reduce MPS memory fragmentation between jobs
                try:
                    if hasattr(h, "_empty_cache"):
                        h._empty_cache()
                    else:
                        import torch
                        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                            torch.mps.empty_cache()
                except Exception:
                    pass
                dt = max(0.0, time.time() - t0)
                async with app.state.stats_lock:
                    app.state.recent_durations.append(dt)
                    if app.state.recent_durations:
                        app.state.avg_job_seconds = sum(app.state.recent_durations) / len(app.state.recent_durations)

        async def _queue_worker(worker_idx: int) -> None:
            while True:
                job_id, req = await app.state.job_queue.get()
                await process_queue_item(
                    job_id=job_id,
                    req=req,
                    app_state=app.state,
                    store=store,
                    run_one_job=_run_one_job,
                    cleanup_job_temp_files=_cleanup_job_temp_files,
                )

        async def _job_store_cleanup_worker() -> None:
            """Background task to periodically clean up old completed jobs."""
            await run_job_store_cleanup_loop(
                store=store,
                cleanup_interval_seconds=JOB_STORE_CLEANUP_INTERVAL,
            )

        worker_count = max(1, WORKER_COUNT)
        workers = [asyncio.create_task(_queue_worker(i)) for i in range(worker_count)]
        cleanup_task = asyncio.create_task(_job_store_cleanup_worker())
        app.state.worker_tasks = workers
        app.state.cleanup_task = cleanup_task

        # =================================================================
        # Initialize models at startup (not lazily on first request)
        # =================================================================

        # Check if --no-init flag is set (skip model loading at startup)
        no_init = _env_bool("ACESTEP_NO_INIT", False)

        # Detect GPU memory and get configuration (always needed)
        gpu_config = get_gpu_config()
        set_global_gpu_config(gpu_config)
        app.state.gpu_config = gpu_config

        gpu_memory_gb = gpu_config.gpu_memory_gb
        auto_offload = gpu_memory_gb > 0 and gpu_memory_gb < VRAM_AUTO_OFFLOAD_THRESHOLD_GB

        # Print GPU configuration info
        print(f"\n{'='*60}")
        print("[API Server] GPU Configuration Detected:")
        print(f"{'='*60}")
        print(f"  GPU Memory: {gpu_memory_gb:.2f} GB")
        print(f"  Configuration Tier: {gpu_config.tier}")
        print(f"  Max Duration (with LM): {gpu_config.max_duration_with_lm}s")
        print(f"  Max Duration (without LM): {gpu_config.max_duration_without_lm}s")
        print(f"  Max Batch Size (with LM): {gpu_config.max_batch_size_with_lm}")
        print(f"  Max Batch Size (without LM): {gpu_config.max_batch_size_without_lm}")
        print(f"  Default LM Init: {gpu_config.init_lm_default}")
        print(f"  Available LM Models: {gpu_config.available_lm_models or 'None'}")
        print(f"{'='*60}\n")

        if no_init:
            print("[API Server] --no-init mode: Skipping all model loading at startup")
            print("[API Server] Models will be lazy-loaded on first request")
            print("[API Server] Server is ready to accept requests (models not loaded yet)")
        else:
            print("[API Server] Initializing models at startup...")

            if auto_offload:
                print("[API Server] Auto-enabling CPU offload (GPU < 16GB)")
            elif gpu_memory_gb > 0:
                print("[API Server] CPU offload disabled by default (GPU >= 16GB)")
            else:
                print("[API Server] No GPU detected, running on CPU")

            project_root = _get_project_root()
            config_path = os.getenv("ACESTEP_CONFIG_PATH", "acestep-v15-turbo")
            device = os.getenv("ACESTEP_DEVICE", "auto")
            use_flash_attention = _env_bool("ACESTEP_USE_FLASH_ATTENTION", True)

            # Auto-determine offload settings based on GPU config if not explicitly set
            offload_to_cpu_env = os.getenv("ACESTEP_OFFLOAD_TO_CPU")
            if offload_to_cpu_env is not None:
                offload_to_cpu = _env_bool("ACESTEP_OFFLOAD_TO_CPU", False)
            else:
                offload_to_cpu = auto_offload
                if auto_offload:
                    print("[API Server] Auto-setting offload_to_cpu=True based on GPU memory")

            offload_dit_to_cpu = _env_bool("ACESTEP_OFFLOAD_DIT_TO_CPU", False)
            compile_model = _env_bool("ACESTEP_COMPILE_MODEL", False)

            # Checkpoint directory
            checkpoint_dir = os.path.join(project_root, "checkpoints")
            os.makedirs(checkpoint_dir, exist_ok=True)

            # Download and initialize primary DiT model
            dit_model_name = _get_model_name(config_path)
            if dit_model_name:
                try:
                    _ensure_model_downloaded(dit_model_name, checkpoint_dir)
                except Exception as e:
                    print(f"[API Server] Warning: Failed to download DiT model: {e}")

            # Download VAE model
            try:
                _ensure_model_downloaded("vae", checkpoint_dir)
            except Exception as e:
                print(f"[API Server] Warning: Failed to download VAE model: {e}")

            print(f"[API Server] Loading primary DiT model: {config_path}")
            status_msg, ok = handler.initialize_service(
                project_root=project_root,
                config_path=config_path,
                device=device,
                use_flash_attention=use_flash_attention,
                compile_model=compile_model,
                offload_to_cpu=offload_to_cpu,
                offload_dit_to_cpu=offload_dit_to_cpu,
            )
            if not ok:
                app.state._init_error = status_msg
                print(f"[API Server] ERROR: Primary model failed to load: {status_msg}")
                raise RuntimeError(status_msg)
            app.state._initialized = True
            print(f"[API Server] Primary model loaded: {_get_model_name(config_path)}")

            # Initialize secondary model if configured
            if handler2 and config_path2:
                model2_name = _get_model_name(config_path2)
                if model2_name:
                    try:
                        _ensure_model_downloaded(model2_name, checkpoint_dir)
                    except Exception as e:
                        print(f"[API Server] Warning: Failed to download secondary model: {e}")

                print(f"[API Server] Loading secondary DiT model: {config_path2}")
                try:
                    status_msg2, ok2 = handler2.initialize_service(
                        project_root=project_root,
                        config_path=config_path2,
                        device=device,
                        use_flash_attention=use_flash_attention,
                        compile_model=compile_model,
                        offload_to_cpu=offload_to_cpu,
                        offload_dit_to_cpu=offload_dit_to_cpu,
                    )
                    app.state._initialized2 = ok2
                    if ok2:
                        print(f"[API Server] Secondary model loaded: {model2_name}")
                    else:
                        print(f"[API Server] Warning: Secondary model failed: {status_msg2}")
                except Exception as e:
                    print(f"[API Server] Warning: Failed to initialize secondary model: {e}")
                    app.state._initialized2 = False

            # Initialize third model if configured
            if handler3 and config_path3:
                model3_name = _get_model_name(config_path3)
                if model3_name:
                    try:
                        _ensure_model_downloaded(model3_name, checkpoint_dir)
                    except Exception as e:
                        print(f"[API Server] Warning: Failed to download third model: {e}")

                print(f"[API Server] Loading third DiT model: {config_path3}")
                try:
                    status_msg3, ok3 = handler3.initialize_service(
                        project_root=project_root,
                        config_path=config_path3,
                        device=device,
                        use_flash_attention=use_flash_attention,
                        compile_model=compile_model,
                        offload_to_cpu=offload_to_cpu,
                        offload_dit_to_cpu=offload_dit_to_cpu,
                    )
                    app.state._initialized3 = ok3
                    if ok3:
                        print(f"[API Server] Third model loaded: {model3_name}")
                    else:
                        print(f"[API Server] Warning: Third model failed: {status_msg3}")
                except Exception as e:
                    print(f"[API Server] Warning: Failed to initialize third model: {e}")
                    app.state._initialized3 = False

            # Initialize LLM model based on GPU configuration
            # ACESTEP_INIT_LLM controls LLM initialization:
            #   - "auto" / empty / not set: Use GPU config default (auto-detect)
            #   - "true"/"1"/"yes": Force enable LLM after GPU config is applied
            #   - "false"/"0"/"no": Force disable LLM
            #
            # Flow: GPU detection → model validation → ACESTEP_INIT_LLM override
            # This ensures GPU optimizations (offload, quantization, etc.) are always applied.
            init_llm_env = os.getenv("ACESTEP_INIT_LLM", "").strip().lower()

            # Step 1: Start with GPU auto-detection result
            init_llm = gpu_config.init_lm_default
            print(f"[API Server] GPU auto-detection: init_llm={init_llm} (VRAM: {gpu_config.gpu_memory_gb:.1f}GB, tier: {gpu_config.tier})")

            # Step 2: Apply user override if set
            if not init_llm_env or init_llm_env == "auto":
                print("[API Server] ACESTEP_INIT_LLM=auto, using GPU auto-detection result")
            elif init_llm_env in {"1", "true", "yes", "y", "on"}:
                if init_llm:
                    print("[API Server] ACESTEP_INIT_LLM=true (GPU already supports LLM, no override needed)")
                else:
                    init_llm = True
                    print("[API Server] ACESTEP_INIT_LLM=true, overriding GPU auto-detection (force enable)")
            else:
                if not init_llm:
                    print("[API Server] ACESTEP_INIT_LLM=false (GPU already disabled LLM, no override needed)")
                else:
                    init_llm = False
                    print("[API Server] ACESTEP_INIT_LLM=false, overriding GPU auto-detection (force disable)")

            if init_llm:
                print("[API Server] Loading LLM model...")

                # Auto-select LM model based on GPU config if not explicitly set
                lm_model_path_env = os.getenv("ACESTEP_LM_MODEL_PATH", "").strip()
                if lm_model_path_env:
                    lm_model_path = lm_model_path_env
                    print(f"[API Server] Using user-specified LM model: {lm_model_path}")
                else:
                    # Get recommended LM model for this GPU tier
                    recommended_lm = get_recommended_lm_model(gpu_config)
                    if recommended_lm:
                        lm_model_path = recommended_lm
                        print(f"[API Server] Auto-selected LM model: {lm_model_path} based on GPU tier")
                    else:
                        # No recommended model (GPU tier too low), default to smallest
                        lm_model_path = "acestep-5Hz-lm-0.6B"
                        print(f"[API Server] No recommended model for this GPU tier, using smallest: {lm_model_path}")

                # Validate LM model support (warning only, does not block)
                is_supported, warning_msg = is_lm_model_supported(lm_model_path, gpu_config)
                if not is_supported:
                    print(f"[API Server] Warning: {warning_msg}")
                    # Try to fall back to a supported model
                    recommended_lm = get_recommended_lm_model(gpu_config)
                    if recommended_lm:
                        lm_model_path = recommended_lm
                        print(f"[API Server] Falling back to supported LM model: {lm_model_path}")
                    else:
                        # No supported model, but user may have forced init
                        print(f"[API Server] No GPU-validated LM model available, attempting {lm_model_path} anyway (may cause OOM)")

            if init_llm:
                lm_backend = os.getenv("ACESTEP_LM_BACKEND", "vllm").strip().lower()
                if lm_backend not in {"vllm", "pt", "mlx"}:
                    lm_backend = "vllm"
                lm_device = os.getenv("ACESTEP_LM_DEVICE", device)

                # Auto-determine LM offload based on GPU config
                lm_offload_env = os.getenv("ACESTEP_LM_OFFLOAD_TO_CPU")
                if lm_offload_env is not None:
                    lm_offload = _env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False)
                else:
                    lm_offload = offload_to_cpu

                lm_model_name = _get_model_name(lm_model_path)
                try:
                    _ensure_model_downloaded(lm_model_name, checkpoint_dir)
                except Exception as e:
                    print(f"[API Server] Warning: Failed to download LLM model: {e}")

                llm_status, llm_ok = llm_handler.initialize(
                    checkpoint_dir=checkpoint_dir,
                    lm_model_path=lm_model_path,
                    backend=lm_backend,
                    device=lm_device,
                    offload_to_cpu=lm_offload,
                    dtype=None,
                )
                if llm_ok:
                    app.state._llm_initialized = True
                    print(f"[API Server] LLM model loaded: {lm_model_path}")
                else:
                    app.state._llm_init_error = llm_status
                    print(f"[API Server] Warning: LLM model failed to load: {llm_status}")
            else:
                print("[API Server] Skipping LLM initialization (disabled or not supported for this GPU)")
                app.state._llm_initialized = False
                # Disable lazy loading of LLM - don't try to load it later during requests
                app.state._llm_lazy_load_disabled = True
                print("[API Server] LLM lazy loading disabled. To enable LLM:")
                print("[API Server]   - Set ACESTEP_INIT_LLM=true in .env or environment")
                print("[API Server]   - Or use --init-llm command line flag")

            print("[API Server] All models initialized successfully!")

        try:
            yield
        finally:
            cleanup_task.cancel()
            for t in workers:
                t.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="ACE-Step API", version="1.0", lifespan=lifespan)

    # Enable CORS for browser-based frontends (e.g. studio.html opened via file://)
    # Restricted to localhost origins and the "null" origin (file:// protocol)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["null", "http://localhost", "http://127.0.0.1"],
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Mount OpenRouter-compatible endpoints (/v1/chat/completions, /v1/models)
    from acestep.openrouter_adapter import create_openrouter_router
    openrouter_router = create_openrouter_router(lambda: app.state)
    app.include_router(openrouter_router)

    async def _queue_position(job_id: str) -> int:
        async with app.state.pending_lock:
            try:
                return list(app.state.pending_ids).index(job_id) + 1
            except ValueError:
                return 0

    async def _eta_seconds_for_position(pos: int) -> Optional[float]:
        if pos <= 0:
            return None
        async with app.state.stats_lock:
            avg = float(getattr(app.state, "avg_job_seconds", INITIAL_AVG_JOB_SECONDS))
        return pos * avg

    register_model_service_routes(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=_wrap_response,
        store=store,
        queue_maxsize=QUEUE_MAXSIZE,
        initial_avg_job_seconds=INITIAL_AVG_JOB_SECONDS,
        get_project_root=_get_project_root,
        get_model_name=_get_model_name,
        ensure_model_downloaded=_ensure_model_downloaded,
        env_bool=_env_bool,
    )

    register_sample_format_routes(
        app=app,
        verify_token_from_request=verify_token_from_request,
        wrap_response=_wrap_response,
        simple_example_data=SIMPLE_EXAMPLE_DATA,
        custom_example_data=CUSTOM_EXAMPLE_DATA,
        format_sample=format_sample,
        get_project_root=_get_project_root,
        get_model_name=_get_model_name,
        ensure_model_downloaded=_ensure_model_downloaded,
        env_bool=_env_bool,
        to_int=_request_to_int,
        to_float=_request_to_float,
    )

    register_lora_routes(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=_wrap_response,
    )

    register_reinitialize_route(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=_wrap_response,
        env_bool=_env_bool,
        get_project_root=_get_project_root,
    )

    register_training_api_routes(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=_wrap_response,
        start_tensorboard=partial(
            _runtime_start_tensorboard,
            stop_tensorboard_fn=_runtime_stop_tensorboard,
        ),
        stop_tensorboard=_runtime_stop_tensorboard,
        temporary_llm_model=partial(
            _runtime_temporary_llm_model,
            get_project_root=_get_project_root,
            get_model_name=_get_model_name,
            ensure_model_downloaded=_ensure_model_downloaded,
            env_bool=_env_bool,
        ),
        atomic_write_json=_runtime_atomic_write_json,
        append_jsonl=_runtime_append_jsonl,
    )

    register_audio_route(
        app=app,
        verify_api_key=verify_api_key,
    )

    register_release_task_route(
        app=app,
        verify_token_from_request=verify_token_from_request,
        wrap_response=_wrap_response,
        store=store,
        request_parser_cls=RequestParser,
        request_model_cls=GenerateMusicRequest,
        validate_audio_path=_validate_audio_path,
        save_upload_to_temp=_save_upload_to_temp,
        upload_file_type=StarletteUploadFile,
        default_dit_instruction=DEFAULT_DIT_INSTRUCTION,
        lm_default_temperature=LM_DEFAULT_TEMPERATURE,
        lm_default_cfg_scale=LM_DEFAULT_CFG_SCALE,
        lm_default_top_p=LM_DEFAULT_TOP_P,
    )

    register_query_result_route(
        app=app,
        verify_token_from_request=verify_token_from_request,
        wrap_response=_wrap_response,
        store=store,
        map_status=_map_status,
        result_key_prefix=RESULT_KEY_PREFIX,
        task_timeout_seconds=TASK_TIMEOUT_SECONDS,
        log_buffer=log_buffer,
    )

    return app


app = create_app()


def main() -> None:
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="ACE-Step API server")
    parser.add_argument(
        "--host",
        default=os.getenv("ACESTEP_API_HOST", "127.0.0.1"),
        help="Bind host (default from ACESTEP_API_HOST or 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ACESTEP_API_PORT", "8001")),
        help="Bind port (default from ACESTEP_API_PORT or 8001)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("ACESTEP_API_KEY", None),
        help="API key for authentication (default from ACESTEP_API_KEY)",
    )
    parser.add_argument(
        "--download-source",
        type=str,
        choices=["huggingface", "modelscope", "auto"],
        default=os.getenv("ACESTEP_DOWNLOAD_SOURCE", "auto"),
        help="Preferred model download source: auto (default), huggingface, or modelscope",
    )
    parser.add_argument(
        "--init-llm",
        action="store_true",
        default=_env_bool("ACESTEP_INIT_LLM", False),
        help="Initialize LLM even if GPU memory is insufficient (may cause OOM). "
             "Can also be set via ACESTEP_INIT_LLM=true environment variable.",
    )
    parser.add_argument(
        "--lm-model-path",
        type=str,
        default=os.getenv("ACESTEP_LM_MODEL_PATH", ""),
        help="LM model to load (e.g., 'acestep-5Hz-lm-0.6B'). Default from ACESTEP_LM_MODEL_PATH.",
    )
    parser.add_argument(
        "--no-init",
        action="store_true",
        default=_env_bool("ACESTEP_NO_INIT", False),
        help="Skip model loading at startup (models will be lazy-loaded on first request). "
             "Can also be set via ACESTEP_NO_INIT=true environment variable.",
    )
    args = parser.parse_args()

    # Set API key from command line argument
    if args.api_key:
        os.environ["ACESTEP_API_KEY"] = args.api_key

    # Set download source preference
    if args.download_source and args.download_source != "auto":
        os.environ["ACESTEP_DOWNLOAD_SOURCE"] = args.download_source
        print(f"Using preferred download source: {args.download_source}")

    # Set init LLM flag
    if args.init_llm:
        os.environ["ACESTEP_INIT_LLM"] = "true"
        print("[API Server] LLM initialization enabled via --init-llm")

    # Set LM model path
    if args.lm_model_path:
        os.environ["ACESTEP_LM_MODEL_PATH"] = args.lm_model_path
        print(f"[API Server] Using LM model: {args.lm_model_path}")

    # Set no-init flag
    if args.no_init:
        os.environ["ACESTEP_NO_INIT"] = "true"
        print("[API Server] --no-init: Models will NOT be loaded at startup (lazy load on first request)")

    # IMPORTANT: in-memory queue/store -> workers MUST be 1
    uvicorn.run(
        "acestep.api_server:app",
        host=str(args.host),
        port=int(args.port),
        reload=False,
        workers=1,
    )

if __name__ == "__main__":
    main()






