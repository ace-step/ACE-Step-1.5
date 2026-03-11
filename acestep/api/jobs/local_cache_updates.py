"""Helpers for writing API job state into the local cache backend."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional


def _get_record_env_and_time(
    store: Any,
    job_id: str,
    now_fn: Callable[[], float],
) -> tuple[str, float]:
    """Return `(env, create_time)` derived from store record or defaults."""

    record = store.get(job_id)
    if record is None:
        return "development", now_fn()
    return getattr(record, "env", "development"), getattr(record, "created_at", now_fn())


def update_local_cache(
    local_cache: Any,
    store: Any,
    job_id: str,
    result: Optional[Dict[str, Any]],
    status: str,
    map_status: Callable[[str], int],
    result_key_prefix: str,
    result_expire_seconds: int,
    now_fn: Callable[[], float] = time.time,
) -> None:
    """Persist terminal job result payload to local cache.

    Args:
        local_cache: Cache object exposing `set(key, value, ex=...)`.
        store: Job store exposing `get(job_id)`.
        job_id: Job identifier.
        result: Optional terminal result payload.
        status: Terminal job status string.
        map_status: Status mapper from text status to integer code.
        result_key_prefix: Prefix for cache keys.
        result_expire_seconds: Cache TTL in seconds.
        now_fn: Time provider for deterministic tests.
    """

    if not local_cache:
        return

    env, create_time = _get_record_env_and_time(store=store, job_id=job_id, now_fn=now_fn)
    status_int = map_status(status)

    if status == "succeeded" and result:
        if result.get("status_message") == "Full Hardware Analysis Success":
            result_data = [result]
        else:
            audio_paths = result.get("audio_paths", [])
            final_prompt = result.get("prompt", "")
            final_lyrics = result.get("lyrics", "")
            metas_raw = result.get("metas", {}) or {}
            metas = {
                "bpm": metas_raw.get("bpm"),
                "duration": metas_raw.get("duration"),
                "genres": metas_raw.get("genres", ""),
                "keyscale": metas_raw.get("keyscale", ""),
                "timesignature": metas_raw.get("timesignature", ""),
                "prompt": metas_raw.get("prompt", ""),
                "lyrics": metas_raw.get("lyrics", ""),
            }
            generation_info = result.get("generation_info", "")
            seed_value = result.get("seed_value", "")
            lm_model = result.get("lm_model", "")
            dit_model = result.get("dit_model", "")

            if audio_paths:
                result_data = [
                    {
                        "file": path,
                        "wave": "",
                        "status": status_int,
                        "create_time": int(create_time),
                        "env": env,
                        "prompt": final_prompt,
                        "lyrics": final_lyrics,
                        "metas": metas,
                        "generation_info": generation_info,
                        "seed_value": seed_value,
                        "lm_model": lm_model,
                        "dit_model": dit_model,
                        "progress": 1.0,
                        "stage": "succeeded",
                    }
                    for path in audio_paths
                ]
            else:
                result_data = [{
                    "file": "",
                    "wave": "",
                    "status": status_int,
                    "create_time": int(create_time),
                    "env": env,
                    "prompt": final_prompt,
                    "lyrics": final_lyrics,
                    "metas": metas,
                    "generation_info": generation_info,
                    "seed_value": seed_value,
                    "lm_model": lm_model,
                    "dit_model": dit_model,
                    "progress": 1.0,
                    "stage": "succeeded",
                }]
    else:
        result_data = [{
            "file": "",
            "wave": "",
            "status": status_int,
            "create_time": int(create_time),
            "env": env,
            "progress": 0.0,
            "stage": "failed" if status == "failed" else status,
        }]

    result_key = f"{result_key_prefix}{job_id}"
    local_cache.set(result_key, result_data, ex=result_expire_seconds)


def update_local_cache_progress(
    local_cache: Any,
    store: Any,
    job_id: str,
    progress: float,
    stage: str,
    map_status: Callable[[str], int],
    result_key_prefix: str,
    result_expire_seconds: int,
    now_fn: Callable[[], float] = time.time,
) -> None:
    """Persist running/queued progress payload to local cache."""

    if not local_cache:
        return

    env, create_time = _get_record_env_and_time(store=store, job_id=job_id, now_fn=now_fn)
    status_int = map_status("running")
    result_data = [{
        "file": "",
        "wave": "",
        "status": status_int,
        "create_time": int(create_time),
        "env": env,
        "progress": float(progress),
        "stage": stage,
    }]
    result_key = f"{result_key_prefix}{job_id}"
    local_cache.set(result_key, result_data, ex=result_expire_seconds)
