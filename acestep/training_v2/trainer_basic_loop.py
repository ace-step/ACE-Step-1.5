"""
Basic (non-Fabric) training loop for FixedLoRATrainer.

Extracted from ``FixedLoRATrainer._train_basic`` to keep
``trainer_fixed.py`` under the LOC limit.  This module provides a single
generator function that yields ``TrainingUpdate`` objects exactly like
the Fabric loop, but uses manual ``loss.backward()`` and
``torch.nn.utils.clip_grad_norm_`` instead of Fabric wrappers.
"""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import torch

from acestep.training_v2.optim import build_optimizer, build_scheduler
from acestep.training_v2.tensorboard_utils import TrainingLogger
from acestep.training_v2.trainer_helpers import configure_memory_features, save_checkpoint, save_final
from acestep.training_v2.ui import TrainingUpdate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extracted helpers
# ---------------------------------------------------------------------------

def _flush_accumulated(
    trainable_params: list,
    optimizer: Any,
    scheduler: Any,
    accumulated_loss: float,
    accumulation_step: int,
    cfg: Any,
    tb: TrainingLogger,
    module: Any,
    epoch: int,
    global_step: int,
    steps_per_epoch: int,
) -> Tuple[int, float, List[TrainingUpdate]]:
    """Clip gradients, step optimizer/scheduler, zero grads, and log.

    Consolidates the duplicated optimizer-step sequence used both inside
    the accumulation check and the end-of-epoch flush.

    Returns:
        ``(global_step, avg_loss, updates)`` where *updates* is a list
        of ``TrainingUpdate`` objects the caller should yield.
    """
    torch.nn.utils.clip_grad_norm_(trainable_params, cfg.max_grad_norm)
    optimizer.step()
    scheduler.step()
    optimizer.zero_grad(set_to_none=True)
    global_step += 1

    avg_loss = accumulated_loss * cfg.gradient_accumulation_steps / accumulation_step
    _lr = scheduler.get_last_lr()[0]
    updates: List[TrainingUpdate] = []

    if global_step % cfg.log_every == 0:
        tb.log_loss(avg_loss, global_step)
        tb.log_lr(_lr, global_step)
        updates.append(TrainingUpdate(
            step=global_step, loss=avg_loss,
            msg=f"Epoch {epoch + 1}, Step {global_step}, Loss: {avg_loss:.4f}",
            kind="step", epoch=epoch + 1, max_epochs=cfg.max_epochs, lr=_lr,
            steps_per_epoch=steps_per_epoch,
        ))

    if global_step % cfg.log_heavy_every == 0:
        tb.log_per_layer_grad_norms(module.model, global_step)

    return global_step, avg_loss, updates


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_basic_training_loop(
    trainer: Any,
    data_module: Any,
    training_state: Optional[Dict[str, Any]],
) -> Generator[TrainingUpdate, None, None]:
    """Execute the basic (non-Fabric) training loop.

    Args:
        trainer: The ``FixedLoRATrainer`` instance.
        data_module: ``PreprocessedDataModule`` with training data.
        training_state: Optional dict with ``should_stop`` flag.

    Yields:
        ``TrainingUpdate`` tuples for each step/epoch/event.
    """
    cfg = trainer.training_config
    module = trainer.module
    assert module is not None

    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    yield TrainingUpdate(0, 0.0, "[INFO] Starting basic training loop (no Fabric)", kind="info")

    tb = TrainingLogger(cfg.effective_log_dir)
    train_loader = data_module.train_dataloader()

    trainable_params = [p for p in module.model.parameters() if p.requires_grad]
    if not trainable_params:
        yield TrainingUpdate(0, 0.0, "[FAIL] No trainable parameters found", kind="fail")
        tb.close()
        return

    device_type = module.device_type if hasattr(module, "device_type") else str(module.device).split(":")[0]
    optimizer_type = getattr(cfg, "optimizer_type", "adamw")
    optimizer = build_optimizer(
        trainable_params,
        optimizer_type=optimizer_type,
        lr=cfg.learning_rate,
        weight_decay=cfg.weight_decay,
        device_type=device_type,
    )

    steps_per_epoch = max(1, math.ceil(len(train_loader) / cfg.gradient_accumulation_steps))
    total_steps = steps_per_epoch * cfg.max_epochs

    scheduler = build_scheduler(
        optimizer,
        scheduler_type=getattr(cfg, "scheduler_type", "cosine"),
        total_steps=total_steps,
        warmup_steps=cfg.warmup_steps,
        lr=cfg.learning_rate,
        optimizer_type=optimizer_type,
    )

    # -- Training memory features (same as Fabric path) ----------------
    if getattr(cfg, "gradient_checkpointing", True):
        ckpt_ok, cache_off, grads_ok = configure_memory_features(module.model.decoder)
        module.force_input_grads_for_checkpointing = ckpt_ok
        if ckpt_ok:
            yield TrainingUpdate(
                0, 0.0,
                f"[INFO] Gradient checkpointing enabled "
                f"(use_cache={not cache_off}, input_grads={grads_ok})",
                kind="info",
            )

    # -- Resume ---------------------------------------------------------
    start_epoch = 0
    global_step = 0

    if cfg.resume_from and Path(cfg.resume_from).exists():
        try:
            yield TrainingUpdate(0, 0.0, f"[INFO] Loading checkpoint from {cfg.resume_from}", kind="info")
            from acestep.training_v2.trainer_helpers import resume_checkpoint
            resumed = yield from resume_checkpoint(trainer, cfg.resume_from, optimizer, scheduler)
            if resumed is not None:
                start_epoch, global_step = resumed
        except Exception as exc:
            logger.exception("Failed to load checkpoint")
            yield TrainingUpdate(0, 0.0, f"[WARN] Checkpoint load failed: {exc} -- starting fresh", kind="warn")

    accumulation_step = 0
    accumulated_loss = 0.0
    optimizer.zero_grad(set_to_none=True)
    module.model.decoder.train()

    for epoch in range(start_epoch, cfg.max_epochs):
        epoch_loss = 0.0
        num_updates = 0
        epoch_start = time.time()

        for batch in train_loader:
            if training_state and training_state.get("should_stop", False):
                _stop_loss = accumulated_loss * cfg.gradient_accumulation_steps / max(accumulation_step, 1)
                yield TrainingUpdate(global_step, _stop_loss, "[INFO] Training stopped", kind="complete")
                tb.close()
                return

            loss = module.training_step(batch)
            loss = loss / cfg.gradient_accumulation_steps
            loss.backward()
            accumulated_loss += loss.item()
            del loss
            accumulation_step += 1

            if accumulation_step >= cfg.gradient_accumulation_steps:
                global_step, avg_loss, updates = _flush_accumulated(
                    trainable_params, optimizer, scheduler,
                    accumulated_loss, accumulation_step, cfg, tb, module,
                    epoch, global_step, steps_per_epoch,
                )
                yield from updates
                epoch_loss += avg_loss
                num_updates += 1
                accumulated_loss = 0.0
                accumulation_step = 0

                if torch.cuda.is_available() and global_step % cfg.log_every == 0:
                    torch.cuda.empty_cache()

        # Flush remainder
        if accumulation_step > 0:
            global_step, avg_loss, updates = _flush_accumulated(
                trainable_params, optimizer, scheduler,
                accumulated_loss, accumulation_step, cfg, tb, module,
                epoch, global_step, steps_per_epoch,
            )
            yield from updates
            epoch_loss += avg_loss
            num_updates += 1
            accumulated_loss = 0.0
            accumulation_step = 0

        epoch_time = time.time() - epoch_start
        avg_epoch_loss = epoch_loss / max(num_updates, 1)
        tb.log_epoch_loss(avg_epoch_loss, epoch + 1)
        yield TrainingUpdate(
            step=global_step, loss=avg_epoch_loss,
            msg=f"[OK] Epoch {epoch + 1}/{cfg.max_epochs} in {epoch_time:.1f}s",
            kind="epoch", epoch=epoch + 1, max_epochs=cfg.max_epochs, epoch_time=epoch_time,
        )

        if (epoch + 1) % cfg.save_every_n_epochs == 0:
            ckpt_dir = str(output_dir / "checkpoints" / f"epoch_{epoch + 1}")
            save_checkpoint(trainer, optimizer, scheduler, epoch + 1, global_step, ckpt_dir)
            yield TrainingUpdate(
                step=global_step, loss=avg_epoch_loss,
                msg=f"[OK] Checkpoint saved at epoch {epoch + 1}",
                kind="checkpoint", epoch=epoch + 1, max_epochs=cfg.max_epochs,
                checkpoint_path=ckpt_dir,
            )

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # -- Sanity check: did we actually train? ----------------------------
    if global_step == 0:
        tb.close()
        yield TrainingUpdate(
            step=0, loss=0.0,
            msg=(
                "[FAIL] Training completed 0 steps -- no batches were processed.\n"
                "       Possible causes:\n"
                "         - Dataset directory is empty or contains no valid .pt files\n"
                "         - DataLoader failed to yield batches (device/platform issue)\n"
                "       Check the dataset path and try again."
            ),
            kind="fail",
        )
        return

    final_path = str(output_dir / "final")
    save_final(trainer, final_path)
    final_loss = module.training_losses[-1] if module.training_losses else 0.0

    adapter_label = "LoKR" if trainer.adapter_type == "lokr" else "LoRA"
    tb.flush()
    tb.close()
    yield TrainingUpdate(
        step=global_step, loss=final_loss,
        msg=(
            f"[OK] Training complete! {adapter_label} saved to {final_path}\n"
            f"     For inference, set your LoRA path to: {final_path}"
        ),
        kind="complete",
    )
