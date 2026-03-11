"""Scan/load dataset route registration for training APIs."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI

from acestep.api.train_api_dataset_models import LoadDatasetRequest, ScanDirectoryRequest, _serialize_samples


def register_training_dataset_scan_load_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
) -> None:
    """Register dataset scan/load routes used by training workflows."""

    @app.post("/v1/dataset/scan")
    async def scan_dataset_directory(request: ScanDirectoryRequest, _: None = Depends(verify_api_key)):
        """Scan directory for audio files and create dataset."""

        from acestep.training.dataset_builder import DatasetBuilder

        try:
            builder = DatasetBuilder()
            builder.metadata.name = request.dataset_name
            builder.metadata.custom_tag = request.custom_tag
            builder.metadata.tag_position = request.tag_position
            builder.metadata.all_instrumental = request.all_instrumental

            samples, status = builder.scan_directory(request.audio_dir.strip())

            if not samples:
                return wrap_response(None, code=400, error=status)

            builder.set_all_instrumental(request.all_instrumental)
            if request.custom_tag:
                builder.set_custom_tag(request.custom_tag, request.tag_position)

            app.state.dataset_builder = builder
            app.state.dataset_json_path = os.path.join(request.audio_dir.strip(), f"{builder.metadata.name}.json")

            return wrap_response(
                {
                    "message": status,
                    "num_samples": len(samples),
                    "samples": _serialize_samples(builder),
                }
            )
        except Exception as exc:
            return wrap_response(None, code=500, error=f"Scan failed: {exc}")

    @app.post("/v1/dataset/load")
    async def load_dataset(request: LoadDatasetRequest, _: None = Depends(verify_api_key)):
        """Load existing dataset from JSON file."""

        from acestep.training.dataset_builder import DatasetBuilder

        try:
            builder = DatasetBuilder()
            samples, status = builder.load_dataset(request.dataset_path.strip())

            if not samples:
                return wrap_response(
                    {
                        "message": status,
                        "dataset_name": "",
                        "num_samples": 0,
                        "labeled_count": 0,
                        "samples": [],
                    },
                    code=400,
                    error=status,
                )

            app.state.dataset_builder = builder

            return wrap_response(
                {
                    "message": status,
                    "dataset_name": builder.metadata.name,
                    "num_samples": len(samples),
                    "labeled_count": builder.get_labeled_count(),
                    "samples": _serialize_samples(builder),
                }
            )
        except Exception as exc:
            error_msg = f"Load failed: {exc}"
            return wrap_response(
                {
                    "message": error_msg,
                    "dataset_name": "",
                    "num_samples": 0,
                    "labeled_count": 0,
                    "samples": [],
                },
                code=500,
                error=error_msg,
            )
