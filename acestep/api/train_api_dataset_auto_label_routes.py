"""Auto-label route-registration facade for training dataset APIs."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI

from acestep.api.train_api_dataset_auto_label_async_route import (
    register_training_dataset_auto_label_async_route,
)
from acestep.api.train_api_dataset_auto_label_status_route import (
    register_training_dataset_auto_label_status_route,
)
from acestep.api.train_api_dataset_auto_label_sync_route import (
    register_training_dataset_auto_label_sync_route,
)
from acestep.llm_inference import LLMHandler


def register_training_dataset_auto_label_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
    temporary_llm_model: Callable[[FastAPI, LLMHandler, Optional[str]], Any],
    atomic_write_json: Callable[[str, Dict[str, Any]], None],
    append_jsonl: Callable[[str, Dict[str, Any]], None],
) -> None:
    """Register all auto-label routes via focused submodules."""

    register_training_dataset_auto_label_sync_route(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
        temporary_llm_model=temporary_llm_model,
        atomic_write_json=atomic_write_json,
        append_jsonl=append_jsonl,
    )
    register_training_dataset_auto_label_async_route(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
        temporary_llm_model=temporary_llm_model,
        atomic_write_json=atomic_write_json,
        append_jsonl=append_jsonl,
    )
    register_training_dataset_auto_label_status_route(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
    )
