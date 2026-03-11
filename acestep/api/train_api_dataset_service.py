"""Dataset-route registration facade for training APIs."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI

from acestep.api.train_api_dataset_auto_label_routes import register_training_dataset_auto_label_routes
from acestep.api.train_api_dataset_preprocess_routes import register_training_dataset_preprocess_routes
from acestep.api.train_api_dataset_sample_routes import register_training_dataset_sample_routes
from acestep.api.train_api_dataset_scan_load_routes import register_training_dataset_scan_load_routes
from acestep.api.train_api_dataset_status_routes import register_training_dataset_status_routes
from acestep.llm_inference import LLMHandler


def register_training_dataset_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
    temporary_llm_model: Callable[[FastAPI, LLMHandler, Optional[str]], Any],
    atomic_write_json: Callable[[str, Dict[str, Any]], None],
    append_jsonl: Callable[[str, Dict[str, Any]], None],
) -> None:
    """Register all dataset-related training routes via focused route modules."""

    register_training_dataset_scan_load_routes(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
    )
    register_training_dataset_auto_label_routes(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
        temporary_llm_model=temporary_llm_model,
        atomic_write_json=atomic_write_json,
        append_jsonl=append_jsonl,
    )
    register_training_dataset_status_routes(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
    )
    register_training_dataset_preprocess_routes(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
    )
    register_training_dataset_sample_routes(
        app=app,
        verify_api_key=verify_api_key,
        wrap_response=wrap_response,
    )

