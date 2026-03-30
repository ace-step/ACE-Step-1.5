"""Lifespan bootstrap helpers for API server runtime state initialization."""

from __future__ import annotations

import asyncio
import os
import sys
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable


@dataclass
class LifespanRuntime:
    """Runtime objects returned after lifespan state initialization."""

    cache_root: str
    tmp_root: str
    handler: Any
    llm_handler: Any
    handler2: Any
    handler3: Any
    config_path2: str
    config_path3: str
    executor: ThreadPoolExecutor


def _initialize_local_cache(app: Any, cache_root: str) -> None:
    """Initialize local cache store when optional dependency is available."""

    try:
        from acestep.local_cache import get_local_cache

        local_cache_dir = os.path.join(cache_root, "local_redis")
        app.state.local_cache = get_local_cache(local_cache_dir)
    except ImportError:
        app.state.local_cache = None


def initialize_lifespan_runtime(
    *,
    app: Any,
    store: Any,
    queue_maxsize: int,
    avg_window: int,
    initial_avg_job_seconds: float,
    get_project_root: Callable[[], str],
    initialize_training_state_fn: Callable[[Any], None],
    ace_handler_cls: Callable[[], Any],
    llm_handler_cls: Callable[[], Any],
) -> LifespanRuntime:
    """Initialize process environment, model handlers, and app.state runtime fields."""

    for proxy_var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
        os.environ.pop(proxy_var, None)

    project_root = get_project_root()
    cache_root = os.path.join(project_root, ".cache", "acestep")
    tmp_root = (os.getenv("ACESTEP_TMPDIR") or os.path.join(cache_root, "tmp")).strip()
    triton_cache_root = (os.getenv("TRITON_CACHE_DIR") or os.path.join(cache_root, "triton")).strip()
    inductor_cache_root = (
        (os.getenv("TORCHINDUCTOR_CACHE_DIR") or os.path.join(cache_root, "torchinductor")).strip()
    )

    for path in [cache_root, tmp_root, triton_cache_root, inductor_cache_root]:
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            pass

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

    handler = ace_handler_cls()
    llm_handler = llm_handler_cls()
    init_lock = asyncio.Lock()
    app.state._initialized = False
    app.state._init_error = None
    app.state._init_lock = init_lock

    app.state.llm_handler = llm_handler
    app.state._llm_initialized = False
    app.state._llm_init_error = None
    app.state._llm_init_lock = Lock()
    app.state._llm_lazy_load_disabled = False

    handler2 = None
    handler3 = None
    config_path2 = os.getenv("ACESTEP_CONFIG_PATH2", "").strip()
    config_path3 = os.getenv("ACESTEP_CONFIG_PATH3", "").strip()
    if config_path2:
        handler2 = ace_handler_cls()
    if config_path3:
        handler3 = ace_handler_cls()

    app.state.handler2 = handler2
    app.state.handler3 = handler3
    app.state._initialized2 = False
    app.state._initialized3 = False
    app.state._init_error2 = None
    app.state._init_error3 = None
    app.state._config_path = os.getenv("ACESTEP_CONFIG_PATH", "acestep-v15-turbo")
    app.state._config_path2 = config_path2
    app.state._config_path3 = config_path3

    max_workers = int(os.getenv("ACESTEP_API_WORKERS", "1"))
    executor = ThreadPoolExecutor(max_workers=max_workers)

    app.state.job_queue = asyncio.Queue(maxsize=queue_maxsize)
    app.state.pending_ids = deque()
    app.state.pending_lock = asyncio.Lock()
    app.state.job_temp_files = {}
    app.state.job_temp_files_lock = asyncio.Lock()
    app.state.stats_lock = asyncio.Lock()
    app.state.recent_durations = deque(maxlen=avg_window)
    app.state.avg_job_seconds = initial_avg_job_seconds

    app.state.handler = handler
    app.state.executor = executor
    app.state.job_store = store
    app.state._python_executable = sys.executable
    initialize_training_state_fn(app)

    app.state.temp_audio_dir = os.path.join(tmp_root, "api_audio")
    os.makedirs(app.state.temp_audio_dir, exist_ok=True)
    _initialize_local_cache(app, cache_root)

    return LifespanRuntime(
        cache_root=cache_root,
        tmp_root=tmp_root,
        handler=handler,
        llm_handler=llm_handler,
        handler2=handler2,
        handler3=handler3,
        config_path2=config_path2,
        config_path3=config_path3,
        executor=executor,
    )
