"""Sample and dataset-save route registration for training dataset APIs."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException

from acestep.api.train_api_dataset_models import SaveDatasetRequest, UpdateSampleRequest, _serialize_samples


def register_training_dataset_sample_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
) -> None:
    """Register dataset save and sample CRUD routes used by training workflows."""

    @app.post("/v1/dataset/save")
    async def save_dataset(request: SaveDatasetRequest, _: None = Depends(verify_api_key)):
        """Save dataset to JSON file."""

        builder = app.state.dataset_builder
        if builder is None:
            raise HTTPException(status_code=400, detail="No dataset to save")

        try:
            if request.custom_tag is not None:
                builder.metadata.custom_tag = request.custom_tag
            if request.tag_position is not None:
                builder.metadata.tag_position = request.tag_position
            if request.all_instrumental is not None:
                builder.metadata.all_instrumental = request.all_instrumental
            if request.genre_ratio is not None:
                builder.metadata.genre_ratio = request.genre_ratio

            status = builder.save_dataset(request.save_path.strip(), request.dataset_name)

            if status.startswith("✅"):
                app.state.dataset_json_path = request.save_path.strip()

            if status.startswith("✅"):
                return wrap_response({"message": status, "save_path": request.save_path})
            return wrap_response(None, code=400, error=status)
        except Exception as exc:
            return wrap_response(None, code=500, error=f"Save failed: {exc}")

    @app.get("/v1/dataset/samples")
    async def get_all_samples(_: None = Depends(verify_api_key)):
        """Get all samples in the current dataset."""

        builder = app.state.dataset_builder
        if builder is None:
            raise HTTPException(status_code=400, detail="No dataset loaded")

        return wrap_response(
            {
                "dataset_name": builder.metadata.name,
                "num_samples": len(builder.samples),
                "labeled_count": builder.get_labeled_count(),
                "samples": _serialize_samples(builder),
            }
        )

    @app.get("/v1/dataset/sample/{sample_idx}")
    async def get_sample(sample_idx: int, _: None = Depends(verify_api_key)):
        """Get a specific sample by index."""

        builder = app.state.dataset_builder
        if builder is None:
            raise HTTPException(status_code=400, detail="No dataset loaded")

        if sample_idx < 0 or sample_idx >= len(builder.samples):
            raise HTTPException(status_code=404, detail=f"Sample index {sample_idx} out of range")

        sample = builder.samples[sample_idx]
        payload = sample.to_dict()
        payload["index"] = sample_idx
        return wrap_response(payload)

    @app.put("/v1/dataset/sample/{sample_idx}")
    async def update_sample(sample_idx: int, request: UpdateSampleRequest, _: None = Depends(verify_api_key)):
        """Update a sample's metadata."""

        builder = app.state.dataset_builder
        if builder is None:
            raise HTTPException(status_code=400, detail="No dataset loaded")

        try:
            sample, status = builder.update_sample(
                sample_idx,
                caption=request.caption,
                genre=request.genre,
                prompt_override=request.prompt_override,
                lyrics=request.lyrics if not request.is_instrumental else "[Instrumental]",
                bpm=request.bpm,
                keyscale=request.keyscale,
                timesignature=request.timesignature,
                language="unknown" if request.is_instrumental else request.language,
                is_instrumental=request.is_instrumental,
                labeled=True,
            )

            if status.startswith("✅"):
                sample_payload = sample.to_dict()
                sample_payload["index"] = sample_idx
                return wrap_response({"message": status, "sample": sample_payload})
            return wrap_response(None, code=400, error=status)
        except Exception as exc:
            return wrap_response(None, code=500, error=f"Update failed: {exc}")
