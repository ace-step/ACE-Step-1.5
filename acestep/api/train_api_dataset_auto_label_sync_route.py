"""Sync auto-label route registration for training dataset APIs."""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException
from loguru import logger

from acestep.api.train_api_dataset_models import AutoLabelRequest, _serialize_samples
from acestep.api.train_api_runtime import RuntimeComponentManager
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler


def register_training_dataset_auto_label_sync_route(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
    temporary_llm_model: Callable[[FastAPI, LLMHandler, Optional[str]], Any],
    atomic_write_json: Callable[[str, Dict[str, Any]], None],
    append_jsonl: Callable[[str, Dict[str, Any]], None],
) -> None:
    """Register the synchronous auto-label route."""

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
