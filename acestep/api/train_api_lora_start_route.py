"""LoRA training start route registration."""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from loguru import logger

from acestep.api.train_api_models import StartTrainingRequest, initialize_training_state
from acestep.api.train_api_runtime import RuntimeComponentManager, unwrap_module
from acestep.handler import AceStepHandler


def register_lora_training_start_route(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[[Any, int, Optional[str]], Dict[str, Any]],
    start_tensorboard: Callable[[FastAPI, str], Optional[str]],
) -> None:
    """Register the `/v1/training/start` route."""

    @app.post("/v1/training/start")
    async def start_training(request: StartTrainingRequest, _: None = Depends(verify_api_key)):
        """Start LoRA training from preprocessed tensors."""

        initialize_training_state(app)
        training_state = app.state.training_state
        if training_state.get("is_training", False):
            raise HTTPException(status_code=400, detail="Training already in progress")

        handler: AceStepHandler = app.state.handler
        if handler is None or handler.model is None:
            raise HTTPException(status_code=500, detail="Model not initialized")
        if not hasattr(handler.model, "decoder") or handler.model.decoder is None:
            raise HTTPException(
                status_code=500,
                detail="Decoder not found. Please reload the model via /v1/reinitialize before training.",
            )

        handler.model.decoder = unwrap_module(handler.model.decoder)
        mgr = RuntimeComponentManager(handler=handler, llm=app.state.llm_handler, app_state=app.state)
        mgr.move_decoder_to(str(handler.device))
        mgr.offload_vae_to_cpu()
        mgr.offload_text_encoder_to_cpu()
        mgr.offload_model_encoder_to_cpu()
        mgr.unload_llm()

        try:
            from acestep.training.configs import LoRAConfig as LoRAConfigClass, TrainingConfig
            from acestep.training.trainer import LoRATrainer

            lora_config = LoRAConfigClass(r=request.lora_rank, alpha=request.lora_alpha, dropout=request.lora_dropout)
            training_config = TrainingConfig(
                shift=request.training_shift,
                learning_rate=request.learning_rate,
                batch_size=request.train_batch_size,
                gradient_accumulation_steps=request.gradient_accumulation,
                max_epochs=request.train_epochs,
                save_every_n_epochs=request.save_every_n_epochs,
                seed=request.training_seed,
                output_dir=request.lora_output_dir,
                use_fp8=request.use_fp8,
                gradient_checkpointing=request.gradient_checkpointing,
            )
            trainer = LoRATrainer(dit_handler=handler, lora_config=lora_config, training_config=training_config)
        except Exception as exc:
            training_state["is_training"] = False
            mgr.restore()
            return wrap_response(None, code=500, error=f"Failed to start training: {exc}")

        tensorboard_logdir = os.path.join(request.lora_output_dir, "logs")
        os.makedirs(tensorboard_logdir, exist_ok=True)

        run_id = str(uuid4())
        training_state.update(
            {
                "is_training": True,
                "should_stop": False,
                "run_id": run_id,
                "trainer": trainer,
                "tensor_dir": request.tensor_dir,
                "tensorboard_logdir": tensorboard_logdir,
                "current_step": 0,
                "current_loss": None,
                "status": "Starting...",
                "loss_history": [],
                "training_log": "Starting...",
                "start_time": time.time(),
                "current_epoch": 0,
                "last_step_time": time.time(),
                "steps_per_second": 0.0,
                "estimated_time_remaining": 0.0,
                "error": None,
                "config": {
                    "lora_rank": request.lora_rank,
                    "lora_alpha": request.lora_alpha,
                    "learning_rate": request.learning_rate,
                    "epochs": request.train_epochs,
                },
                "_component_manager": mgr,
            }
        )
        training_state["tensorboard_url"] = start_tensorboard(app, tensorboard_logdir)

        def _runner() -> None:
            local_run_id = run_id
            try:
                for step, loss, status in trainer.train_from_preprocessed(request.tensor_dir, training_state):
                    if training_state.get("run_id") != local_run_id:
                        break
                    training_state["current_step"] = step
                    training_state["current_loss"] = loss
                    training_state["status"] = status
                    text = str(status)
                    match = re.search(r"Epoch (\d+)/(\d+)", text)
                    if match:
                        training_state["current_epoch"] = int(match.group(1))
                    if loss is not None and loss == loss and step > 0:
                        history = training_state.get("loss_history", [])
                        history.append({"step": step, "loss": float(loss)})
                        training_state["loss_history"] = history[-1000:]
                    if training_state.get("should_stop", False):
                        break
            except Exception as exc:
                training_state["error"] = str(exc)
            finally:
                training_state["is_training"] = False
                try:
                    if handler.model is not None and getattr(handler.model, "decoder", None) is not None:
                        handler.model.decoder = unwrap_module(handler.model.decoder)
                        handler.model.decoder.eval()
                except Exception:
                    logger.exception("Failed to restore decoder wrapper state after training")
                cm = training_state.pop("_component_manager", None)
                if cm is not None:
                    cm.restore()

        threading.Thread(target=_runner, daemon=True).start()
        return wrap_response(
            {
                "message": "Training started",
                "tensor_dir": request.tensor_dir,
                "output_dir": request.lora_output_dir,
                "config": training_state["config"],
                "fp8_enabled": request.use_fp8,
            }
        )
