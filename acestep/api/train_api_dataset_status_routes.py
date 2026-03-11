"""Latest-status route registration for training dataset APIs."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI

from acestep.api import train_api_models


def register_training_dataset_status_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
) -> None:
    """Register latest-status routes for auto-label and preprocess workflows."""

    @app.get("/v1/dataset/preprocess_status")
    async def get_preprocess_status_latest(_: None = Depends(verify_api_key)):
        """Get latest preprocess task status."""

        with train_api_models._preprocess_lock:
            latest_task_id = train_api_models._preprocess_latest_task_id
            if latest_task_id is None:
                return wrap_response(
                    {
                        "task_id": None,
                        "status": "idle",
                        "progress": "",
                        "current": 0,
                        "total": 0,
                    }
                )

            task = train_api_models._preprocess_tasks.get(latest_task_id)
            if task is None:
                return wrap_response(
                    {
                        "task_id": latest_task_id,
                        "status": "idle",
                        "progress": "",
                        "current": 0,
                        "total": 0,
                    }
                )

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

    @app.get("/v1/dataset/auto_label_status")
    async def get_auto_label_status_latest(_: None = Depends(verify_api_key)):
        """Get latest auto-label task status."""

        with train_api_models._auto_label_lock:
            latest_task_id = train_api_models._auto_label_latest_task_id
            if latest_task_id is None:
                return wrap_response(
                    {
                        "task_id": None,
                        "status": "idle",
                        "progress": "",
                        "current": 0,
                        "total": 0,
                    }
                )
            task = train_api_models._auto_label_tasks.get(latest_task_id)
            if task is None:
                return wrap_response(
                    {
                        "task_id": latest_task_id,
                        "status": "idle",
                        "progress": "",
                        "current": 0,
                        "total": 0,
                    }
                )

            response_data = {
                "task_id": task.task_id,
                "status": task.status,
                "progress": task.progress,
                "current": task.current,
                "total": task.total,
                "save_path": task.save_path,
                "last_updated_index": task.last_updated_index,
                "last_updated_sample": task.last_updated_sample,
            }
            if task.status == "completed" and task.result:
                response_data["result"] = task.result
            elif task.status == "failed" and task.error:
                response_data["error"] = task.error
            return wrap_response(response_data)
