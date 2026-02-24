"""Training run wiring helpers extracted from ``events.__init__``."""

from typing import Any, Iterator

from loguru import logger

from .. import training_handlers as train_h
from .context import TrainingWiringContext
from .training_lokr_wiring import register_lokr_training_handlers


def _normalize_training_state(training_state: Any) -> dict[str, bool]:
    """Return a valid mutable training-state mapping for streaming wrappers."""

    if isinstance(training_state, dict):
        return training_state
    return {"is_training": False, "should_stop": False}


def _build_training_wrapper(dit_handler: Any):
    """Build the training stream wrapper bound to the current DiT handler."""

    def training_wrapper(
        tensor_dir: Any,
        lora_rank: Any,
        lora_alpha: Any,
        lora_dropout: Any,
        learning_rate: Any,
        train_epochs: Any,
        train_batch_size: Any,
        gradient_accumulation: Any,
        save_every_n_epochs: Any,
        training_shift: Any,
        training_seed: Any,
        lora_output_dir: Any,
        resume_checkpoint_dir: Any,
        training_state: Any,
    ) -> Iterator[tuple[Any, Any, Any, dict[str, bool]]]:
        """Stream LoRA training progress and normalize failure outputs for UI."""

        state = _normalize_training_state(training_state)
        try:
            for progress, log_msg, plot, next_state in train_h.start_training(
                tensor_dir,
                dit_handler,
                lora_rank,
                lora_alpha,
                lora_dropout,
                learning_rate,
                train_epochs,
                train_batch_size,
                gradient_accumulation,
                save_every_n_epochs,
                training_shift,
                training_seed,
                lora_output_dir,
                resume_checkpoint_dir,
                state,
            ):
                yield progress, log_msg, plot, next_state
        except Exception as exc:  # pragma: no cover - defensive UI wrapper
            logger.exception("Training wrapper error")
            yield f"\u274c Error: {exc!s}", f"{exc!s}", None, state

    return training_wrapper


def register_training_run_handlers(context: TrainingWiringContext) -> None:
    """Register training run-tab handlers with stable IO ordering."""

    training_section = context.training_section
    training_wrapper = _build_training_wrapper(context.dit_handler)

    # ========== Training Tab Handlers ==========
    training_section["load_dataset_btn"].click(
        fn=train_h.load_training_dataset,
        inputs=[training_section["training_tensor_dir"]],
        outputs=[training_section["training_dataset_info"]],
    )

    training_section["start_training_btn"].click(
        fn=training_wrapper,
        inputs=[
            training_section["training_tensor_dir"],
            training_section["lora_rank"],
            training_section["lora_alpha"],
            training_section["lora_dropout"],
            training_section["learning_rate"],
            training_section["train_epochs"],
            training_section["train_batch_size"],
            training_section["gradient_accumulation"],
            training_section["save_every_n_epochs"],
            training_section["training_shift"],
            training_section["training_seed"],
            training_section["lora_output_dir"],
            training_section["resume_checkpoint_dir"],
            training_section["training_state"],
        ],
        outputs=[
            training_section["training_progress"],
            training_section["training_log"],
            training_section["training_loss_plot"],
            training_section["training_state"],
        ],
    )

    training_section["stop_training_btn"].click(
        fn=train_h.stop_training,
        inputs=[training_section["training_state"]],
        outputs=[
            training_section["training_progress"],
            training_section["training_state"],
        ],
    )

    training_section["export_lora_btn"].click(
        fn=train_h.export_lora,
        inputs=[
            training_section["export_path"],
            training_section["lora_output_dir"],
        ],
        outputs=[training_section["export_status"]],
    )

    register_lokr_training_handlers(
        context,
        normalize_training_state=_normalize_training_state,
    )
