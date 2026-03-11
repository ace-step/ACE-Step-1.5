"""Runtime helper functions used by API training and model orchestration paths."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional


def stop_tensorboard(app: Any) -> None:
    """Stop TensorBoard process if running."""

    try:
        proc = getattr(app.state, "tensorboard_process", None)
    except Exception:
        proc = None

    if proc is None:
        return

    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        app.state.tensorboard_process = None
    except Exception:
        pass


def start_tensorboard(
    app: Any,
    logdir: str,
    stop_tensorboard_fn: Callable[[Any], None] = stop_tensorboard,
) -> Optional[str]:
    """(Re)start TensorBoard with the given logdir and return URL if successful."""

    try:
        tensorboard_port = int(os.getenv("TENSORBOARD_PORT", "6006"))
        stop_tensorboard_fn(app)

        if sys.prefix != sys.base_prefix:
            tensorboard_cmd = os.path.join(sys.prefix, "Scripts", "tensorboard.exe")
            if not os.path.exists(tensorboard_cmd):
                tensorboard_cmd = os.path.join(sys.prefix, "bin", "tensorboard")
            if not os.path.exists(tensorboard_cmd):
                tensorboard_cmd = "tensorboard"
        else:
            tensorboard_cmd = "tensorboard"

        app.state.tensorboard_process = subprocess.Popen(
            [
                tensorboard_cmd,
                "--logdir",
                logdir,
                "--port",
                str(tensorboard_port),
                "--bind_all",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"http://localhost:{tensorboard_port}"
    except Exception:
        return None


@contextmanager
def temporary_llm_model(
    app: Any,
    llm: Any,
    lm_model_path: Optional[str],
    get_project_root: Callable[[], str],
    get_model_name: Callable[[str], str],
    ensure_model_downloaded: Callable[[str, str], str],
    env_bool: Callable[[str, bool], bool],
):
    """Temporarily switch LLM model for a critical section and restore afterward."""

    desired = (lm_model_path or "").strip()
    if not desired:
        yield
        return

    if llm is None or not getattr(llm, "llm_initialized", False):
        yield
        return

    lock = getattr(app.state, "_llm_init_lock", None)
    if lock is None:
        yield
        return

    with lock:
        prev_params = getattr(llm, "last_init_params", None)
        prev_model = (prev_params or {}).get("lm_model_path") if isinstance(prev_params, dict) else None
        if prev_model and prev_model.strip() == desired:
            yield
            return

        project_root = get_project_root()
        checkpoint_dir = os.path.join(project_root, "checkpoints")
        os.makedirs(checkpoint_dir, exist_ok=True)

        lm_model_name = get_model_name(desired)
        if lm_model_name:
            try:
                ensure_model_downloaded(lm_model_name, checkpoint_dir)
            except Exception:
                pass

        restore_params = prev_params if isinstance(prev_params, dict) else None

        ok_switched = False
        try:
            new_params = dict(restore_params) if restore_params else {
                "checkpoint_dir": checkpoint_dir,
                "backend": os.getenv("ACESTEP_LM_BACKEND", "vllm").strip().lower() or "vllm",
                "device": os.getenv("ACESTEP_LM_DEVICE", os.getenv("ACESTEP_DEVICE", "auto")),
                "offload_to_cpu": env_bool("ACESTEP_LM_OFFLOAD_TO_CPU", False),
                "dtype": None,
            }
            new_params["checkpoint_dir"] = checkpoint_dir
            new_params["lm_model_path"] = desired

            status, ok = llm.initialize(**new_params)
            if ok:
                ok_switched = True
                try:
                    app.state._llm_initialized = True
                    app.state._llm_init_error = None
                except Exception:
                    pass
            else:
                try:
                    app.state._llm_initialized = False
                    app.state._llm_init_error = status
                except Exception:
                    pass
        except Exception as exc:
            try:
                app.state._llm_initialized = False
                app.state._llm_init_error = str(exc)
            except Exception:
                pass

        try:
            yield
        finally:
            if not ok_switched or not restore_params:
                return
            try:
                llm.initialize(**restore_params)
                try:
                    app.state._llm_initialized = True
                    app.state._llm_init_error = None
                except Exception:
                    pass
            except Exception as exc:
                try:
                    app.state._llm_initialized = False
                    app.state._llm_init_error = str(exc)
                except Exception:
                    pass


def atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    """Write JSON atomically to reduce corruption risk during incremental saves."""

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory or None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise


def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    """Append a single JSONL record for audit/progress tracing."""

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(record, ensure_ascii=False) + "\n")
