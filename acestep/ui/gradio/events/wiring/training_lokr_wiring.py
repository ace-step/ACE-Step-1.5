"""LoKr-specific training run wiring helpers."""

from typing import Any, Callable, Iterator

from loguru import logger

from .. import training_handlers as train_h
from .context import TrainingWiringContext


def _build_lokr_training_wrapper(
    dit_handler: Any,
    normalize_training_state: Callable[[Any], dict[str, bool]],
):
    """Build the LoKr training stream wrapper bound to the current DiT handler."""

    def lokr_training_wrapper(
        tensor_dir: Any,
        lokr_linear_dim: Any,
        lokr_linear_alpha: Any,
        lokr_factor: Any,
        lokr_decompose_both: Any,
        lokr_use_tucker: Any,
        lokr_use_scalar: Any,
        lokr_weight_decompose: Any,
        lokr_learning_rate: Any,
        lokr_train_epochs: Any,
        lokr_train_batch_size: Any,
        lokr_gradient_accumulation: Any,
        lokr_save_every_n_epochs: Any,
        lokr_training_shift: Any,
        lokr_training_seed: Any,
        lokr_output_dir: Any,
        training_state: Any,
    ) -> Iterator[tuple[Any, Any, Any, dict[str, bool]]]:
        """Stream LoKr training progress and normalize failure outputs for UI."""

        state = normalize_training_state(training_state)
        try:
            for progress, log_msg, plot, next_state in train_h.start_lokr_training(
                tensor_dir,
                dit_handler,
                lokr_linear_dim,
                lokr_linear_alpha,
                lokr_factor,
                lokr_decompose_both,
                lokr_use_tucker,
                lokr_use_scalar,
                lokr_weight_decompose,
                lokr_learning_rate,
                lokr_train_epochs,
                lokr_train_batch_size,
                lokr_gradient_accumulation,
                lokr_save_every_n_epochs,
                lokr_training_shift,
                lokr_training_seed,
                lokr_output_dir,
                state,
            ):
                yield progress, log_msg, plot, next_state
        except Exception as exc:  # pragma: no cover - defensive UI wrapper
            logger.exception("LoKr training wrapper error")
            yield f"\u274c Error: {exc!r}", f"{exc!r}", None, state

    return lokr_training_wrapper


def register_lokr_training_handlers(
    context: TrainingWiringContext,
    *,
    normalize_training_state: Callable[[Any], dict[str, bool]],
) -> None:
    """Register LoKr training handlers with stable IO ordering."""

    training_section = context.training_section
    lokr_training_wrapper = _build_lokr_training_wrapper(
        context.dit_handler,
        normalize_training_state,
    )

    # ========== LoKr Training Tab Handlers ==========
    training_section["lokr_load_dataset_btn"].click(
        fn=train_h.load_training_dataset,
        inputs=[training_section["lokr_training_tensor_dir"]],
        outputs=[training_section["lokr_training_dataset_info"]],
    )

    training_section["start_lokr_training_btn"].click(
        fn=lokr_training_wrapper,
        inputs=[
            training_section["lokr_training_tensor_dir"],
            training_section["lokr_linear_dim"],
            training_section["lokr_linear_alpha"],
            training_section["lokr_factor"],
            training_section["lokr_decompose_both"],
            training_section["lokr_use_tucker"],
            training_section["lokr_use_scalar"],
            training_section["lokr_weight_decompose"],
            training_section["lokr_learning_rate"],
            training_section["lokr_train_epochs"],
            training_section["lokr_train_batch_size"],
            training_section["lokr_gradient_accumulation"],
            training_section["lokr_save_every_n_epochs"],
            training_section["lokr_training_shift"],
            training_section["lokr_training_seed"],
            training_section["lokr_output_dir"],
            training_section["training_state"],
        ],
        outputs=[
            training_section["lokr_training_progress"],
            training_section["lokr_training_log"],
            training_section["lokr_training_loss_plot"],
            training_section["training_state"],
        ],
    )

    training_section["stop_lokr_training_btn"].click(
        fn=train_h.stop_training,
        inputs=[training_section["training_state"]],
        outputs=[
            training_section["lokr_training_progress"],
            training_section["training_state"],
        ],
    )

    training_section["refresh_lokr_export_epochs_btn"].click(
        fn=train_h.list_lokr_export_epochs,
        inputs=[training_section["lokr_output_dir"]],
        outputs=[
            training_section["lokr_export_epoch"],
            training_section["lokr_export_status"],
        ],
    )

    training_section["export_lokr_btn"].click(
        fn=train_h.export_lokr,
        inputs=[
            training_section["lokr_export_path"],
            training_section["lokr_output_dir"],
            training_section["lokr_export_epoch"],
        ],
        outputs=[training_section["lokr_export_status"]],
    )
