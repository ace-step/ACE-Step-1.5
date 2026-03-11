"""Auto-label status-by-task route registration for training dataset APIs."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException

from acestep.api import train_api_models


def register_training_dataset_auto_label_status_route(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
) -> None:
    """Register the task-id status route for auto-label workflows."""

    @app.get("/v1/dataset/auto_label_status/{task_id}")
    async def get_auto_label_status(task_id: str, _: None = Depends(verify_api_key)):
        """Get auto-labeling task status and progress."""

        with train_api_models._auto_label_lock:
            task = train_api_models._auto_label_tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

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
