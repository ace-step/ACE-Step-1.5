"""
Wizard flow for gradient sensitivity estimation.

Uses a step-list pattern for go-back navigation.
"""

from __future__ import annotations

import argparse
from typing import Any, Callable

from acestep.training_v2.ui import console, is_rich_active
from acestep.training_v2.ui.prompt_helpers import (
    DEFAULT_NUM_WORKERS,
    GoBack,
    ask,
    ask_path,
    native_path,
    section,
    step_indicator,
)


# ---- Steps ------------------------------------------------------------------

def _step_model(a: dict) -> None:
    """Prompt for checkpoint directory, model variant, and dataset path.

    Args:
        a: Mutable answers dict; mutated with ``checkpoint_dir``,
            ``model_variant``, and ``dataset_dir``.

    Raises:
        GoBack: When the user navigates back.
    """
    section("Gradient Sensitivity Estimation")
    if is_rich_active() and console is not None:
        console.print(
            "  [dim]Estimates which LoRA layers learn fastest for your dataset.\n"
            "  Results are saved as JSON and can be used to guide rank selection.[/]\n"
        )
    else:
        print(
            "  Estimates which LoRA layers learn fastest for your dataset.\n"
            "  Results are saved as JSON and can be used to guide rank selection.\n"
        )

    a["checkpoint_dir"] = ask_path(
        "Checkpoint directory", default=a.get("checkpoint_dir", native_path("./checkpoints")),
        must_exist=True, allow_back=True,
    )
    a["model_variant"] = ask(
        "Model variant", default=a.get("model_variant", "base"),
        choices=["turbo", "base", "sft"], allow_back=True,
    )
    a["dataset_dir"] = ask_path(
        "Dataset directory (preprocessed .pt files)",
        default=a.get("dataset_dir"),
        must_exist=True, allow_back=True,
    )


def _step_params(a: dict) -> None:
    """Prompt for estimation hyperparameters.

    Args:
        a: Mutable answers dict; mutated with ``estimate_batches``,
            ``top_k``, and ``granularity``.

    Raises:
        GoBack: When the user navigates back.
    """
    section("Estimation Parameters (press Enter for defaults)")
    a["estimate_batches"] = ask("Number of estimation batches", default=a.get("estimate_batches", 5), type_fn=int, allow_back=True)
    a["top_k"] = ask("Top-K layers to highlight", default=a.get("top_k", 16), type_fn=int, allow_back=True)
    a["granularity"] = ask("Granularity", default=a.get("granularity", "module"), choices=["module", "layer"], allow_back=True)


def _step_lora(a: dict) -> None:
    """Prompt for LoRA rank, alpha, and dropout used during estimation.

    Args:
        a: Mutable answers dict; mutated with ``rank``, ``alpha``,
            and ``dropout``.

    Raises:
        GoBack: When the user navigates back.
    """
    section("LoRA Settings (press Enter for defaults)")
    a["rank"] = ask("Rank", default=a.get("rank", 64), type_fn=int, allow_back=True)
    a["alpha"] = ask("Alpha", default=a.get("alpha", 128), type_fn=int, allow_back=True)
    a["dropout"] = ask("Dropout", default=a.get("dropout", 0.1), type_fn=float, allow_back=True)


def _step_output(a: dict) -> None:
    """Prompt for the output JSON path for estimation results.

    Args:
        a: Mutable answers dict; mutated with ``estimate_output``.

    Raises:
        GoBack: When the user navigates back.
    """
    a["estimate_output"] = ask(
        "Output JSON path",
        default=a.get("estimate_output", native_path("./estimate_results.json")),
        allow_back=True,
    )


# ---- Step list and runner ---------------------------------------------------

_STEPS: list[tuple[str, Callable[..., Any]]] = [
    ("Model & Dataset", _step_model),
    ("Estimation Parameters", _step_params),
    ("LoRA Settings", _step_lora),
    ("Output", _step_output),
]


def wizard_estimate() -> argparse.Namespace:
    """Interactive wizard for gradient estimation.

    Returns:
        A populated ``argparse.Namespace`` for the estimate subcommand.

    Raises:
        GoBack: If the user backs out of the first step.
    """
    answers: dict = {}
    total = len(_STEPS)
    i = 0

    while i < total:
        label, step_fn = _STEPS[i]
        try:
            step_indicator(i + 1, total, label)
            step_fn(answers)
            i += 1
        except GoBack:
            if i == 0:
                raise  # bubble to main menu
            i -= 1

    return argparse.Namespace(
        subcommand="estimate",
        plain=False,
        yes=True,
        _from_wizard=True,
        checkpoint_dir=answers["checkpoint_dir"],
        model_variant=answers["model_variant"],
        device="auto",
        precision="auto",
        dataset_dir=answers["dataset_dir"],
        num_workers=DEFAULT_NUM_WORKERS,
        pin_memory=True,
        prefetch_factor=2 if DEFAULT_NUM_WORKERS > 0 else 0,
        persistent_workers=DEFAULT_NUM_WORKERS > 0,
        learning_rate=1e-4,
        batch_size=1,
        gradient_accumulation=4,
        epochs=1,
        warmup_steps=0,
        weight_decay=0.01,
        max_grad_norm=1.0,
        seed=42,
        rank=answers.get("rank", 64),
        alpha=answers.get("alpha", 128),
        dropout=answers.get("dropout", 0.1),
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        attention_type="both",
        bias="none",
        output_dir=native_path("./estimate_output"),
        save_every=999,
        resume_from=None,
        log_dir=None,
        log_every=10,
        log_heavy_every=50,
        sample_every_n_epochs=0,
        optimizer_type="adamw",
        scheduler_type="cosine",
        gradient_checkpointing=True,
        offload_encoder=False,
        preprocess=False,
        audio_dir=None,
        dataset_json=None,
        tensor_output=None,
        max_duration=240.0,
        cfg_ratio=0.15,
        estimate_batches=answers.get("estimate_batches", 5),
        top_k=answers.get("top_k", 16),
        granularity=answers.get("granularity", "module"),
        module_config=None,
        auto_estimate=False,
        estimate_output=answers.get("estimate_output", native_path("./estimate_results.json")),
    )
