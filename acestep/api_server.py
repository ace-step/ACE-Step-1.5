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

import glob
import json
import os
import sys
import time
import urllib.parse
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from loguru import logger

try:
    from dotenv import load_dotenv
except ImportError:  # Optional dependency
    load_dotenv = None  # type: ignore

from fastapi import FastAPI
from acestep.api.train_api_service import (
    initialize_training_state,
)
from acestep.api.jobs.store import _JobStore
from acestep.api.log_capture import install_log_capture
from acestep.api.route_setup import configure_api_routes
from acestep.api.server_cli import run_api_server_main
from acestep.api.lifespan_runtime import initialize_lifespan_runtime
from acestep.api.job_blocking_generation import run_blocking_generate
from acestep.api.job_execution_runtime import run_one_job_runtime
from acestep.api.job_model_selection import select_generation_handler
from acestep.api.job_runtime_state import (
    cleanup_job_temp_files as _cleanup_job_temp_files_state,
    ensure_models_initialized as _ensure_models_initialized,
    update_progress_job_cache as _update_progress_job_cache,
    update_terminal_job_cache as _update_terminal_job_cache,
)
from acestep.api.startup_model_init import initialize_models_at_startup
from acestep.api.worker_runtime import start_worker_tasks, stop_worker_tasks
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
    generate_music,
    create_sample,
    format_sample,
)
from acestep.ui.gradio.events.results_handlers import _build_generation_info

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
        runtime = initialize_lifespan_runtime(
            app=app,
            store=store,
            queue_maxsize=QUEUE_MAXSIZE,
            avg_window=AVG_WINDOW,
            initial_avg_job_seconds=INITIAL_AVG_JOB_SECONDS,
            get_project_root=_get_project_root,
            initialize_training_state_fn=initialize_training_state,
            ace_handler_cls=AceStepHandler,
            llm_handler_cls=LLMHandler,
        )
        handler = runtime.handler
        llm_handler = runtime.llm_handler
        handler2 = runtime.handler2
        handler3 = runtime.handler3
        config_path2 = runtime.config_path2
        config_path3 = runtime.config_path3
        executor = runtime.executor

        async def _run_one_job(job_id: str, req: GenerateMusicRequest) -> None:
            llm: LLMHandler = app.state.llm_handler

            def _build_blocking_result(
                selected_handler: AceStepHandler,
                selected_model_name: str,
            ) -> Dict[str, Any]:
                return run_blocking_generate(
                    app_state=app.state,
                    req=req,
                    job_id=job_id,
                    store=store,
                    llm_handler=llm,
                    selected_handler=selected_handler,
                    selected_model_name=selected_model_name,
                    map_status=_map_status,
                    result_key_prefix=RESULT_KEY_PREFIX,
                    result_expire_seconds=RESULT_EXPIRE_SECONDS,
                    get_project_root=_get_project_root,
                    get_model_name=_get_model_name,
                    ensure_model_downloaded=_ensure_model_downloaded,
                    env_bool=_env_bool,
                    parse_description_hints=_parse_description_hints,
                    parse_timesteps=_parse_timesteps,
                    is_instrumental=_is_instrumental,
                    create_sample_fn=create_sample,
                    format_sample_fn=format_sample,
                    generate_music_fn=generate_music,
                    default_dit_instruction=DEFAULT_DIT_INSTRUCTION,
                    task_instructions=TASK_INSTRUCTIONS,
                    build_generation_info_fn=_build_generation_info,
                    path_to_audio_url_fn=_path_to_audio_url,
                    log_fn=print,
                )

            await run_one_job_runtime(
                app_state=app.state,
                store=store,
                job_id=job_id,
                req=req,
                ensure_models_initialized_fn=_ensure_models_initialized,
                select_generation_handler_fn=select_generation_handler,
                get_model_name=_get_model_name,
                build_blocking_result_fn=_build_blocking_result,
                update_progress_job_cache_fn=_update_progress_job_cache,
                update_terminal_job_cache_fn=_update_terminal_job_cache,
                map_status=_map_status,
                result_key_prefix=RESULT_KEY_PREFIX,
                result_expire_seconds=RESULT_EXPIRE_SECONDS,
                log_fn=print,
            )

        async def _cleanup_job_temp_files_for_job(job_id: str) -> None:
            await _cleanup_job_temp_files_state(app.state, job_id)

        workers, cleanup_task = start_worker_tasks(
            app_state=app.state,
            store=store,
            worker_count=WORKER_COUNT,
            run_one_job=_run_one_job,
            cleanup_job_temp_files=_cleanup_job_temp_files_for_job,
            cleanup_interval_seconds=JOB_STORE_CLEANUP_INTERVAL,
        )
        initialize_models_at_startup(
            app=app,
            handler=handler,
            llm_handler=llm_handler,
            handler2=handler2,
            handler3=handler3,
            config_path2=config_path2,
            config_path3=config_path3,
            get_project_root=_get_project_root,
            get_model_name=_get_model_name,
            ensure_model_downloaded=_ensure_model_downloaded,
            env_bool=_env_bool,
        )
        try:
            yield
        finally:
            stop_worker_tasks(
                workers=workers,
                cleanup_task=cleanup_task,
                executor=executor,
            )

    app = FastAPI(title="ACE-Step API", version="1.0", lifespan=lifespan)

    configure_api_routes(
        app=app,
        store=store,
        queue_maxsize=QUEUE_MAXSIZE,
        initial_avg_job_seconds=INITIAL_AVG_JOB_SECONDS,
        verify_api_key=verify_api_key,
        verify_token_from_request=verify_token_from_request,
        wrap_response=_wrap_response,
        get_project_root=_get_project_root,
        get_model_name=_get_model_name,
        ensure_model_downloaded=_ensure_model_downloaded,
        env_bool=_env_bool,
        simple_example_data=SIMPLE_EXAMPLE_DATA,
        custom_example_data=CUSTOM_EXAMPLE_DATA,
        format_sample=format_sample,
        to_int=_request_to_int,
        to_float=_request_to_float,
        request_parser_cls=RequestParser,
        request_model_cls=GenerateMusicRequest,
        validate_audio_path=_validate_audio_path,
        save_upload_to_temp=_save_upload_to_temp,
        default_dit_instruction=DEFAULT_DIT_INSTRUCTION,
        lm_default_temperature=LM_DEFAULT_TEMPERATURE,
        lm_default_cfg_scale=LM_DEFAULT_CFG_SCALE,
        lm_default_top_p=LM_DEFAULT_TOP_P,
        map_status=_map_status,
        result_key_prefix=RESULT_KEY_PREFIX,
        task_timeout_seconds=TASK_TIMEOUT_SECONDS,
        log_buffer=log_buffer,
        runtime_start_tensorboard=_runtime_start_tensorboard,
        runtime_stop_tensorboard=_runtime_stop_tensorboard,
        runtime_temporary_llm_model=_runtime_temporary_llm_model,
        runtime_atomic_write_json=_runtime_atomic_write_json,
        runtime_append_jsonl=_runtime_append_jsonl,
    )

    return app


app = create_app()


def main() -> None:
    """CLI entrypoint for API server startup."""

    run_api_server_main(env_bool=_env_bool)

if __name__ == "__main__":
    main()







