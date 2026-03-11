"""Async auto-label route registration for training dataset APIs."""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from loguru import logger

from acestep.api import train_api_models
from acestep.api.train_api_dataset_models import AutoLabelRequest, _serialize_samples
from acestep.api.train_api_runtime import RuntimeComponentManager
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler


def register_training_dataset_auto_label_async_route(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
    temporary_llm_model: Callable[[FastAPI, LLMHandler, Optional[str]], Any],
    atomic_write_json: Callable[[str, Dict[str, Any]], None],
    append_jsonl: Callable[[str, Dict[str, Any]], None],
) -> None:
    """Register the asynchronous auto-label route."""

    @app.post("/v1/dataset/auto_label_async")
    async def auto_label_dataset_async(request: AutoLabelRequest, _: None = Depends(verify_api_key)):
        """Start auto-labeling task asynchronously and return task_id immediately."""

        builder = app.state.dataset_builder
        if builder is None:
            raise HTTPException(status_code=400, detail="No dataset loaded. Please scan or load a dataset first.")

        handler: AceStepHandler = app.state.handler
        llm: LLMHandler = app.state.llm_handler

        if handler is None or handler.model is None:
            raise HTTPException(status_code=500, detail="Model not initialized")

        if llm is None or not llm.llm_initialized:
            raise HTTPException(status_code=500, detail="LLM not initialized")

        task_id = str(uuid4())

        if request.only_unlabeled:
            samples_to_label = [sample for sample in builder.samples if not sample.labeled or not sample.caption]
        else:
            samples_to_label = builder.samples

        total = len(samples_to_label)
        if total == 0:
            return wrap_response(
                {
                    "task_id": task_id,
                    "message": "All samples already labeled" if request.only_unlabeled else "No samples to label",
                    "total": 0,
                }
            )

        resolved_save_path = (request.save_path.strip() if request.save_path else None) or getattr(
            app.state,
            "dataset_json_path",
            None,
        )
        resolved_save_path = os.path.normpath(resolved_save_path) if resolved_save_path else None
        with train_api_models._auto_label_lock:
            train_api_models._auto_label_tasks[task_id] = train_api_models.AutoLabelTask(
                task_id=task_id,
                status="running",
                progress=(f"Starting... (save_path={resolved_save_path})" if resolved_save_path else "Starting..."),
                current=0,
                total=total,
                save_path=resolved_save_path,
                created_at=time.time(),
                updated_at=time.time(),
            )
            train_api_models._auto_label_latest_task_id = task_id

        if resolved_save_path:
            try:
                dataset = {
                    "metadata": builder.metadata.to_dict(),
                    "samples": [sample.to_dict() for sample in builder.samples],
                }
                atomic_write_json(resolved_save_path, dataset)
            except Exception as exc:
                logger.exception("Auto-label initial save failed")
                with train_api_models._auto_label_lock:
                    task = train_api_models._auto_label_tasks.get(task_id)
                    if task:
                        task.progress = f"⚠️ Initial save failed: {exc}"
                        task.updated_at = time.time()

        def run_labeling() -> None:
            mgr = RuntimeComponentManager(handler=handler, llm=llm, app_state=app.state)
            mgr.offload_decoder_to_cpu()

            try:
                with temporary_llm_model(app, llm, request.lm_model_path):

                    def progress_callback(msg: str):
                        with train_api_models._auto_label_lock:
                            task = train_api_models._auto_label_tasks.get(task_id)
                            if task:
                                task.progress = msg
                                task.updated_at = time.time()
                                import re

                                match = re.match(r"^(?:VAE encoding|Tokenizing|Labeling|Encoding) (\d+)/(\d+)", msg)
                                if match:
                                    task.current = int(match.group(1))
                                    task.total = int(match.group(2))

                    resolved_jsonl_path = f"{resolved_save_path}.autolabel.jsonl" if resolved_save_path else None

                    def sample_labeled_callback(sample_idx: int, sample: Any, status: str):
                        if "✅" not in status:
                            return

                        with train_api_models._auto_label_lock:
                            task = train_api_models._auto_label_tasks.get(task_id)
                            if task:
                                task.progress = status
                                task.last_updated_index = sample_idx
                                task.last_updated_sample = sample.to_dict()
                                task.updated_at = time.time()

                        if resolved_save_path is None:
                            return
                        try:
                            if resolved_jsonl_path is not None:
                                append_jsonl(
                                    resolved_jsonl_path,
                                    {
                                        "ts": time.time(),
                                        "index": sample_idx,
                                        "status": status,
                                        "sample": sample.to_dict(),
                                    },
                                )
                            dataset = {
                                "metadata": builder.metadata.to_dict(),
                                "samples": [sample.to_dict() for sample in builder.samples],
                            }
                            atomic_write_json(resolved_save_path, dataset)
                        except Exception:
                            logger.exception("Auto-label incremental save failed")
                            with train_api_models._auto_label_lock:
                                task = train_api_models._auto_label_tasks.get(task_id)
                                if task:
                                    task.progress = "⚠️ Auto-label incremental save failed (see server logs)"
                                    task.updated_at = time.time()

                    _samples, status = builder.label_all_samples(
                        dit_handler=handler,
                        llm_handler=llm,
                        format_lyrics=request.format_lyrics,
                        transcribe_lyrics=request.transcribe_lyrics,
                        skip_metas=request.skip_metas,
                        only_unlabeled=request.only_unlabeled,
                        chunk_size=request.chunk_size,
                        batch_size=request.batch_size,
                        progress_callback=progress_callback,
                        sample_labeled_callback=sample_labeled_callback,
                    )

                    if mgr.decoder_moved:
                        status += "\nℹ️ Decoder was temporarily offloaded during labeling and restored afterward."

                    with train_api_models._auto_label_lock:
                        task = train_api_models._auto_label_tasks.get(task_id)
                        if task:
                            task.status = "completed"
                            task.progress = status
                            task.current = task.total
                            task.updated_at = time.time()
                            task.result = {
                                "message": status,
                                "labeled_count": builder.get_labeled_count(),
                                "samples": _serialize_samples(builder),
                            }
            except Exception as exc:
                with train_api_models._auto_label_lock:
                    task = train_api_models._auto_label_tasks.get(task_id)
                    if task:
                        task.status = "failed"
                        task.error = str(exc)
                        task.progress = f"Failed: {exc}"
                        task.updated_at = time.time()
            finally:
                mgr.restore()

        import threading

        thread = threading.Thread(target=run_labeling, daemon=True)
        thread.start()

        return wrap_response(
            {
                "task_id": task_id,
                "message": "Auto-labeling task started",
                "total": total,
            }
        )
