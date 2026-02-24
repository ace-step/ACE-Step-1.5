"""Dataset-related training API request models and route registration."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel, Field, root_validator

from acestep.api import train_api_models
from acestep.api.train_api_runtime import RuntimeComponentManager
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler


class ScanDirectoryRequest(BaseModel):
    """Request payload for scanning a directory into a dataset."""

    audio_dir: str = Field(..., description="Directory path to scan for audio files")
    dataset_name: str = Field(default="my_lora_dataset", description="Dataset name")
    custom_tag: str = Field(default="", description="Custom activation tag")
    tag_position: str = Field(default="replace", description="Tag position: prepend/append/replace")
    all_instrumental: bool = Field(default=True, description="All tracks instrumental")


class LoadDatasetRequest(BaseModel):
    """Request payload for loading an existing dataset JSON file."""

    dataset_path: str = Field(..., description="Path to dataset JSON file")


class AutoLabelRequest(BaseModel):
    """Request payload for auto-labeling dataset samples."""

    skip_metas: bool = Field(default=False, description="Skip BPM/Key/TimeSig generation")
    format_lyrics: bool = Field(default=False, description="Format user lyrics via LLM")
    transcribe_lyrics: bool = Field(default=False, description="Transcribe lyrics from audio")
    only_unlabeled: bool = Field(default=False, description="Only label unlabeled samples")

    lm_model_path: Optional[str] = Field(
        default=None,
        description="Optional LM model path to use for labeling (temporary switch)",
    )

    save_path: Optional[str] = Field(
        default=None,
        description="Optional dataset JSON path to persist progress during auto-label",
    )

    chunk_size: int = Field(default=16, ge=1, description="Chunk size for batch audio encoding")
    batch_size: int = Field(default=1, ge=1, description="Batch size for batch audio encoding")

    @root_validator(pre=True)
    def _backward_compatible_field_names(cls, values: Dict[str, Any]):
        """Map legacy payload fields to current request field names."""

        if values is None:
            return values

        if "chunk_size" not in values or values.get("chunk_size") is None:
            for key in ("hunk_size", "hunksize"):
                if key in values and values.get(key) is not None:
                    values["chunk_size"] = values[key]
                    break

        if "batch_size" not in values or values.get("batch_size") is None:
            for key in ("batchsize",):
                if key in values and values.get(key) is not None:
                    values["batch_size"] = values[key]
                    break

        return values


class SaveDatasetRequest(BaseModel):
    """Request payload for persisting current dataset state."""

    save_path: str = Field(..., description="Path to save dataset JSON")
    dataset_name: str = Field(default="my_lora_dataset", description="Dataset name")
    custom_tag: Optional[str] = Field(default=None, description="Custom activation tag")
    tag_position: Optional[str] = Field(default=None, description="Tag position: prepend/append/replace")
    all_instrumental: Optional[bool] = Field(default=None, description="All tracks instrumental")
    genre_ratio: Optional[int] = Field(default=None, ge=0, le=100, description="Genre vs caption ratio")


class UpdateSampleRequest(BaseModel):
    """Request payload for updating a single dataset sample."""

    sample_idx: int = Field(..., ge=0, description="Sample index")
    caption: str = Field(default="", description="Music description")
    genre: str = Field(default="", description="Genre tags")
    prompt_override: Optional[str] = Field(default=None, description="caption/genre/None")
    lyrics: str = Field(default="[Instrumental]", description="Lyrics")
    bpm: Optional[int] = Field(default=None, description="BPM")
    keyscale: str = Field(default="", description="Musical key")
    timesignature: str = Field(default="", description="Time signature")
    language: str = Field(default="unknown", description="Vocal language")
    is_instrumental: bool = Field(default=True, description="Instrumental track")


class PreprocessDatasetRequest(BaseModel):
    """Request payload for dataset tensor preprocessing."""

    output_dir: str = Field(..., description="Output directory for preprocessed tensors")
    skip_existing: bool = Field(default=False, description="Skip tensors that already exist (by sample id filename)")


def _serialize_samples(builder: Any) -> list[Dict[str, Any]]:
    """Return stable sample payload list for dataset endpoints."""

    return [
        {
            "index": i,
            "filename": sample.filename,
            "audio_path": sample.audio_path,
            "duration": sample.duration,
            "caption": sample.caption,
            "genre": sample.genre,
            "prompt_override": sample.prompt_override,
            "lyrics": sample.lyrics,
            "bpm": sample.bpm,
            "keyscale": sample.keyscale,
            "timesignature": sample.timesignature,
            "language": sample.language,
            "is_instrumental": sample.is_instrumental,
            "labeled": sample.labeled,
        }
        for i, sample in enumerate(builder.samples)
    ]


def register_training_dataset_routes(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
    temporary_llm_model: Callable[[FastAPI, LLMHandler, Optional[str]], Any],
    atomic_write_json: Callable[[str, Dict[str, Any]], None],
    append_jsonl: Callable[[str, Dict[str, Any]], None],
) -> None:
    """Register dataset APIs used by training workflows."""

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

    @app.post("/v1/dataset/auto_label")
    async def auto_label_dataset(request: AutoLabelRequest, _: None = Depends(verify_api_key)):
        """Auto-label all samples using AI."""

        builder = app.state.dataset_builder
        if builder is None:
            raise HTTPException(status_code=400, detail="No dataset loaded. Please scan or load a dataset first.")

        handler: AceStepHandler = app.state.handler
        llm: LLMHandler = app.state.llm_handler

        if handler is None or handler.model is None:
            raise HTTPException(status_code=500, detail="Model not initialized")

        if llm is None or not llm.llm_initialized:
            raise HTTPException(status_code=500, detail="LLM not initialized")

        mgr = RuntimeComponentManager(handler=handler, llm=llm, app_state=app.state)
        mgr.offload_decoder_to_cpu()

        try:
            with temporary_llm_model(app, llm, request.lm_model_path):
                resolved_save_path = (request.save_path.strip() if request.save_path else None) or getattr(
                    app.state,
                    "dataset_json_path",
                    None,
                )
                resolved_save_path = os.path.normpath(resolved_save_path) if resolved_save_path else None
                resolved_jsonl_path = f"{resolved_save_path}.autolabel.jsonl" if resolved_save_path else None

                if resolved_save_path:
                    try:
                        dataset = {
                            "metadata": builder.metadata.to_dict(),
                            "samples": [sample.to_dict() for sample in builder.samples],
                        }
                        atomic_write_json(resolved_save_path, dataset)
                    except Exception:
                        logger.exception("Auto-label initial save failed")

                def sample_labeled_callback(sample_idx: int, sample: Any, status: str):
                    if resolved_save_path is None:
                        return
                    if "✅" not in status:
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

                _samples, status = builder.label_all_samples(
                    dit_handler=handler,
                    llm_handler=llm,
                    format_lyrics=request.format_lyrics,
                    transcribe_lyrics=request.transcribe_lyrics,
                    skip_metas=request.skip_metas,
                    only_unlabeled=request.only_unlabeled,
                    chunk_size=request.chunk_size,
                    batch_size=request.batch_size,
                    progress_callback=None,
                    sample_labeled_callback=sample_labeled_callback,
                )

                if mgr.decoder_moved:
                    status += "\nℹ️ Decoder was temporarily offloaded during labeling and restored afterward."

                return wrap_response(
                    {
                        "message": status,
                        "labeled_count": builder.get_labeled_count(),
                        "samples": _serialize_samples(builder),
                    }
                )
        except Exception as exc:
            return wrap_response(None, code=500, error=f"Auto-label failed: {exc}")
        finally:
            mgr.restore()

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
