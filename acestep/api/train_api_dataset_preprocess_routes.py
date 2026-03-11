"""Preprocess route registration for training dataset APIs."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException

from acestep.api import train_api_models
from acestep.api.train_api_dataset_models import PreprocessDatasetRequest
from acestep.api.train_api_runtime import RuntimeComponentManager
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler


def register_training_dataset_preprocess_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
) -> None:
    """Register preprocess routes used by training workflows."""

    @app.post("/v1/dataset/preprocess")
    async def preprocess_dataset(request: PreprocessDatasetRequest, _: None = Depends(verify_api_key)):
        """Preprocess dataset to tensor files for training."""

        builder = app.state.dataset_builder
        if builder is None:
            raise HTTPException(status_code=400, detail="No dataset loaded")

        handler: AceStepHandler = app.state.handler
        if handler is None or handler.model is None:
            raise HTTPException(status_code=500, detail="Model not initialized")

        preprocess_notes = []
        llm: LLMHandler = app.state.llm_handler
        mgr = RuntimeComponentManager(handler=handler, llm=llm, app_state=app.state)
        mgr.offload_decoder_to_cpu()
        mgr.unload_llm()

        try:
            output_paths, status = await asyncio.to_thread(
                builder.preprocess_to_tensors,
                dit_handler=handler,
                output_dir=request.output_dir.strip(),
                skip_existing=request.skip_existing,
                progress_callback=None,
            )

            if status.startswith("✅"):
                if mgr.llm_unloaded:
                    status += "\nℹ️ LLM was temporarily unloaded during preprocessing and restored afterward."
                if mgr.decoder_moved:
                    status += "\nℹ️ Decoder was temporarily offloaded during preprocessing and restored afterward."
                if preprocess_notes:
                    status += "\n" + "\n".join(preprocess_notes)

                return wrap_response(
                    {
                        "message": status,
                        "output_dir": request.output_dir,
                        "num_tensors": len(output_paths),
                    }
                )
            return wrap_response(None, code=400, error=status)
        except Exception as exc:
            return wrap_response(None, code=500, error=f"Preprocessing failed: {exc}")
        finally:
            mgr.restore()

    @app.post("/v1/dataset/preprocess_async")
    async def preprocess_dataset_async(request: PreprocessDatasetRequest, _: None = Depends(verify_api_key)):
        """Start preprocessing task asynchronously and return task_id immediately."""

        builder = app.state.dataset_builder
        if builder is None:
            raise HTTPException(status_code=400, detail="No dataset loaded")

        handler: AceStepHandler = app.state.handler
        if handler is None or handler.model is None:
            raise HTTPException(status_code=500, detail="Model not initialized")

        task_id = str(uuid4())

        labeled_samples = [sample for sample in builder.samples if sample.labeled]
        total = len(labeled_samples)

        if total == 0:
            return wrap_response(
                {
                    "task_id": task_id,
                    "message": "No labeled samples to preprocess",
                    "total": 0,
                }
            )

        with train_api_models._preprocess_lock:
            train_api_models._preprocess_tasks[task_id] = train_api_models.PreprocessTask(
                task_id=task_id,
                status="running",
                progress="Starting preprocessing...",
                current=0,
                total=total,
                created_at=time.time(),
            )
            train_api_models._preprocess_latest_task_id = task_id

        def run_preprocessing() -> None:
            mgr = RuntimeComponentManager(handler=handler, llm=app.state.llm_handler, app_state=app.state)

            try:
                preprocess_notes = []
                mgr.offload_decoder_to_cpu()
                mgr.unload_llm()

                def progress_callback(msg: str):
                    with train_api_models._preprocess_lock:
                        task = train_api_models._preprocess_tasks.get(task_id)
                        if task:
                            import re

                            match = re.match(r"Preprocessing (\d+)/(\d+)", msg)
                            if match:
                                task.current = int(match.group(1))
                                task.progress = msg

                output_paths, status = builder.preprocess_to_tensors(
                    dit_handler=handler,
                    output_dir=request.output_dir.strip(),
                    skip_existing=request.skip_existing,
                    progress_callback=progress_callback,
                )

                if mgr.llm_unloaded:
                    status += "\nℹ️ LLM was temporarily unloaded during preprocessing and restored afterward."
                if mgr.decoder_moved:
                    status += "\nℹ️ Decoder was temporarily offloaded during preprocessing and restored afterward."
                if preprocess_notes:
                    status += "\n" + "\n".join(preprocess_notes)

                with train_api_models._preprocess_lock:
                    task = train_api_models._preprocess_tasks.get(task_id)
                    if task:
                        task.status = "completed"
                        task.progress = status
                        task.current = task.total
                        task.result = {
                            "message": status,
                            "output_dir": request.output_dir,
                            "num_tensors": len(output_paths),
                        }
            except Exception as exc:
                with train_api_models._preprocess_lock:
                    task = train_api_models._preprocess_tasks.get(task_id)
                    if task:
                        task.status = "failed"
                        task.error = str(exc)
                        task.progress = f"Failed: {exc}"
            finally:
                mgr.restore()

        import threading

        thread = threading.Thread(target=run_preprocessing, daemon=True)
        thread.start()

        return wrap_response(
            {
                "task_id": task_id,
                "message": "Preprocessing task started",
                "total": total,
            }
        )

    @app.get("/v1/dataset/preprocess_status/{task_id}")
    async def get_preprocess_status(task_id: str, _: None = Depends(verify_api_key)):
        """Get preprocessing task status and progress."""

        with train_api_models._preprocess_lock:
            task = train_api_models._preprocess_tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            response_data = {
                "task_id": task.task_id,
                "status": task.status,
                "progress": task.progress,
                "current": task.current,
                "total": task.total,
            }

            if task.status == "completed" and task.result:
                response_data["result"] = task.result
            elif task.status == "failed" and task.error:
                response_data["error"] = task.error

            return wrap_response(response_data)
