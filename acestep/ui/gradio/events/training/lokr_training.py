"""LoKr training handlers for the training UI.

Contains functions for starting LoKr training, listing available
checkpoint epochs, and exporting trained LoKr weights.
"""

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
from loguru import logger

from acestep.training.path_safety import safe_path
from acestep.ui.gradio.i18n import t
from .training_utils import _format_duration, _training_loss_figure


def start_lokr_training(
    tensor_dir: str,
    dit_handler,
    lokr_linear_dim: int,
    lokr_linear_alpha: int,
    lokr_factor: int,
    lokr_decompose_both: bool,
    lokr_use_tucker: bool,
    lokr_use_scalar: bool,
    lokr_weight_decompose: bool,
    learning_rate: float,
    train_epochs: int,
    train_batch_size: int,
    gradient_accumulation: int,
    save_every_n_epochs: int,
    training_shift: float,
    training_seed: int,
    lokr_output_dir: str,
    training_state: Dict,
    progress=None,
):
    """Start LoKr training from preprocessed tensors.

    This is a generator function that yields progress updates as
    (status, log_text, plot_figure, training_state) tuples.
    """
    if not tensor_dir or not tensor_dir.strip():
        yield "❌ Please enter a tensor directory path", "", None, training_state
        return

    try:
        tensor_dir = safe_path(tensor_dir.strip())
    except ValueError:
        yield f"❌ Rejected unsafe tensor directory path: {tensor_dir}", "", None, training_state
        return
    if not os.path.isdir(tensor_dir):
        yield f"❌ Tensor directory not found: {tensor_dir}", "", None, training_state
        return

    if dit_handler is None or dit_handler.model is None:
        yield "❌ Model not initialized. Please initialize the service first.", "", None, training_state
        return

    if getattr(dit_handler, "quantization", None) is not None:
        yield "Switching model to training preset (disable quantization)...", "", None, training_state
        if hasattr(dit_handler, "switch_to_training_preset"):
            switch_status, switched = dit_handler.switch_to_training_preset()
            if not switched:
                yield f"❌ {switch_status}", "", None, training_state
                return
            yield f"✅ {switch_status}", "", None, training_state
        else:
            yield (
                "❌ Training requires non-quantized DiT, and auto-switch is unavailable in this build.",
                "", None, training_state,
            )
            return

    try:
        from lightning.fabric import Fabric  # noqa: F401
    except ImportError as e:
        yield (
            f"❌ Missing required packages: {e}\nPlease install: pip install lightning lycoris-lora",
            "", None, training_state,
        )
        return

    training_state["is_training"] = True
    training_state["should_stop"] = False
    training_state["adapter_type"] = "lokr"

    try:
        from acestep.training.configs import LoKRConfig as LoKRConfigClass, TrainingConfig
        from acestep.training.trainer import LoKRTrainer

        device_attr = getattr(dit_handler, "device", "")
        if hasattr(device_attr, "type"):
            device_type = str(device_attr.type).lower()
        else:
            device_type = str(device_attr).split(":", 1)[0].lower()

        if device_type == "cuda":
            num_workers, pin_memory, prefetch_factor = 4, True, 2
            persistent_workers, pin_memory_device, mixed_precision = True, "cuda", "bf16"
        elif device_type == "xpu":
            num_workers, pin_memory, prefetch_factor = 4, True, 2
            persistent_workers, pin_memory_device, mixed_precision = True, "", "bf16"
        elif device_type == "mps":
            num_workers, pin_memory, prefetch_factor = 0, False, 2
            persistent_workers, pin_memory_device, mixed_precision = False, "", "fp16"
        else:
            num_workers, pin_memory, prefetch_factor = 0, False, 2
            persistent_workers, pin_memory_device, mixed_precision = False, "", "fp32"

        lokr_config = LoKRConfigClass(
            linear_dim=lokr_linear_dim, linear_alpha=lokr_linear_alpha,
            factor=lokr_factor, decompose_both=lokr_decompose_both,
            use_tucker=lokr_use_tucker, use_scalar=lokr_use_scalar,
            weight_decompose=lokr_weight_decompose,
        )
        training_config = TrainingConfig(
            shift=training_shift, learning_rate=learning_rate,
            batch_size=train_batch_size, gradient_accumulation_steps=gradient_accumulation,
            max_epochs=train_epochs, save_every_n_epochs=save_every_n_epochs,
            seed=training_seed, output_dir=lokr_output_dir,
            num_workers=num_workers, pin_memory=pin_memory,
            prefetch_factor=prefetch_factor, persistent_workers=persistent_workers,
            pin_memory_device=pin_memory_device, mixed_precision=mixed_precision,
        )

        log_lines: list = []
        step_list: list = []
        loss_list: list = []
        initial_plot = _training_loss_figure(training_state, step_list, loss_list)
        start_time = time.time()
        yield f"🚀 Starting LoKr training from {tensor_dir}...", "", initial_plot, training_state

        trainer = LoKRTrainer(
            dit_handler=dit_handler, lokr_config=lokr_config, training_config=training_config,
        )

        training_failed = False
        failure_message = ""

        for step, loss, status in trainer.train_from_preprocessed(tensor_dir, training_state):
            status_text = str(status)
            status_lower = status_text.lower()
            if (
                status_text.startswith("❌")
                or "training failed" in status_lower
                or "error:" in status_lower
                or "module not found" in status_lower
            ):
                training_failed = True
                failure_message = status_text

            elapsed_seconds = time.time() - start_time
            time_info = f"⏱️ Elapsed: {_format_duration(elapsed_seconds)}"
            match = re.search(r"Epoch\s+(\d+)/(\d+)", status_text)
            if match:
                current_ep, total_ep = int(match.group(1)), int(match.group(2))
                if current_ep > 0:
                    eta_seconds = (elapsed_seconds / current_ep) * (total_ep - current_ep)
                    time_info += f" | ETA: ~{_format_duration(eta_seconds)}"

            display_status = f"{status_text}\n{time_info}"
            log_lines.append(status_text)
            if len(log_lines) > 15:
                log_lines = log_lines[-15:]
            log_text = "\n".join(log_lines)

            if step > 0 and loss is not None and loss == loss:
                step_list.append(step)
                loss_list.append(float(loss))

            plot_figure = _training_loss_figure(training_state, step_list, loss_list)
            yield display_status, log_text, plot_figure, training_state

            if training_state.get("should_stop", False):
                log_lines.append("ℹ️ Training stopped by user")
                yield f"ℹ️ Stopped ({time_info})", "\n".join(log_lines[-15:]), plot_figure, training_state
                break

        total_time = time.time() - start_time
        training_state["is_training"] = False
        final_plot = _training_loss_figure(training_state, step_list, loss_list)
        if training_failed:
            final_msg = f"{failure_message}\nElapsed: {_format_duration(total_time)}"
            log_lines.append(failure_message)
            yield final_msg, "\n".join(log_lines[-15:]), final_plot, training_state
            return

        completion_msg = f"✅ LoKr training completed! Total time: {_format_duration(total_time)}"
        log_lines.append(completion_msg)
        yield completion_msg, "\n".join(log_lines[-15:]), final_plot, training_state

    except Exception as e:
        logger.exception("LoKr training error")
        training_state["is_training"] = False
        yield f"❌ Error: {str(e)}", str(e), _training_loss_figure({}, [], []), training_state


def list_lokr_export_epochs(lokr_output_dir: str) -> Tuple[Any, str]:
    """List available LoKr checkpoint epochs for export dropdown.

    Returns:
        Tuple of (dropdown_update, status_message).
    """
    default_choice = t("training.latest_auto")
    if not lokr_output_dir or not lokr_output_dir.strip():
        return (
            gr.update(choices=[default_choice], value=default_choice),
            t("training.lokr_output_dir_required"),
        )

    try:
        lokr_output_dir = safe_path(lokr_output_dir.strip())
    except ValueError:
        return (
            gr.update(choices=[default_choice], value=default_choice),
            "❌ Rejected unsafe output directory path",
        )

    checkpoint_dir = os.path.join(lokr_output_dir, "checkpoints")
    if not os.path.isdir(checkpoint_dir):
        return (
            gr.update(choices=[default_choice], value=default_choice),
            t("training.lokr_no_checkpoints_use_latest"),
        )

    checkpoints: List[Tuple[int, str]] = []
    for d in os.listdir(checkpoint_dir):
        if not d.startswith("epoch_"):
            continue
        weight_file = os.path.join(checkpoint_dir, d, "lokr_weights.safetensors")
        if not os.path.exists(weight_file):
            continue
        try:
            epoch_num = int(d.split("_")[1])
        except Exception:
            continue
        checkpoints.append((epoch_num, d))

    if not checkpoints:
        return (
            gr.update(choices=[default_choice], value=default_choice),
            t("training.lokr_no_exportable_checkpoints"),
        )

    checkpoints.sort(key=lambda x: x[0], reverse=True)
    choices = [default_choice] + [d for _, d in checkpoints]
    return (
        gr.update(choices=choices, value=default_choice),
        t("training.lokr_found_checkpoints", count=len(checkpoints)),
    )


def export_lokr(
    export_path: str,
    lokr_output_dir: str,
    selected_epoch: Optional[str] = None,
) -> str:
    """Export trained LoKr weights.

    Returns:
        Status message.
    """
    if not export_path or not export_path.strip():
        return t("training.export_path_required")

    try:
        lokr_output_dir = safe_path(lokr_output_dir)
        export_path = safe_path(export_path.strip())
    except ValueError:
        return "❌ Rejected unsafe path"

    final_dir = os.path.join(lokr_output_dir, "final")
    checkpoint_dir = os.path.join(lokr_output_dir, "checkpoints")
    default_epoch_choice = t("training.latest_auto")

    chosen_epoch = (selected_epoch or "").strip()
    if not chosen_epoch:
        chosen_epoch = default_epoch_choice

    checkpoint_names: List[str] = []
    if os.path.isdir(checkpoint_dir):
        for d in os.listdir(checkpoint_dir):
            if not d.startswith("epoch_"):
                continue
            try:
                int(d.split("_")[1])
            except Exception:
                continue
            checkpoint_names.append(d)
        checkpoint_names.sort(key=lambda x: int(x.split("_")[1]))

    explicit_epoch = chosen_epoch not in {
        default_epoch_choice, "latest", "Latest", "auto", "Auto",
    }
    if explicit_epoch:
        requested = chosen_epoch
        if requested.isdigit():
            requested = f"epoch_{requested}"
        if requested not in checkpoint_names:
            return t(
                "training.lokr_selected_epoch_not_found",
                chosen=chosen_epoch,
                available=(", ".join(checkpoint_names) if checkpoint_names else "(none)"),
            )
        source_file = os.path.join(checkpoint_dir, requested, "lokr_weights.safetensors")
        if not os.path.exists(source_file):
            return t("training.lokr_no_weights_selected_epoch", epoch=requested)
    elif os.path.exists(os.path.join(final_dir, "lokr_weights.safetensors")):
        source_file = os.path.join(final_dir, "lokr_weights.safetensors")
    elif checkpoint_names:
        latest_checkpoint = checkpoint_names[-1]
        source_file = os.path.join(
            checkpoint_dir, latest_checkpoint, "lokr_weights.safetensors",
        )
        if not os.path.exists(source_file):
            return t("training.lokr_no_weights_latest_checkpoint", checkpoint=latest_checkpoint)
    else:
        return t("training.lokr_no_trained_weights_found", path=lokr_output_dir)

    try:
        import shutil

        if export_path.lower().endswith(".safetensors"):
            os.makedirs(
                os.path.dirname(export_path) if os.path.dirname(export_path) else ".",
                exist_ok=True,
            )
            shutil.copy2(source_file, export_path)
            return t("training.lokr_exported", path=export_path)

        os.makedirs(export_path, exist_ok=True)
        dst_file = os.path.join(export_path, "lokr_weights.safetensors")
        shutil.copy2(source_file, dst_file)
        return t("training.lokr_exported", path=dst_file)

    except Exception as e:
        logger.exception("LoKr export error")
        return t("training.export_failed", error=str(e))
