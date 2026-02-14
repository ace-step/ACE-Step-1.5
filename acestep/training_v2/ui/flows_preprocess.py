"""
Wizard flow for preprocessing audio into tensors.

Uses a step-list pattern for go-back navigation.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from acestep.training_v2.ui import console, is_rich_active
from acestep.training_v2.ui.prompt_helpers import (
    DEFAULT_NUM_WORKERS,
    GoBack,
    _esc,
    ask,
    ask_path,
    native_path,
    section,
    step_indicator,
)


# ---- Steps ------------------------------------------------------------------

def _step_model(a: dict) -> None:
    """Checkpoint directory and model selection."""
    from acestep.training_v2.settings import get_checkpoint_dir
    from acestep.training_v2.model_discovery import pick_model, prompt_base_model

    section("Preprocessing Settings")

    ckpt_default = a.get("checkpoint_dir") or get_checkpoint_dir() or native_path("./checkpoints")
    a["checkpoint_dir"] = ask_path(
        "Checkpoint directory", default=ckpt_default,
        must_exist=True, allow_back=True,
    )

    # Model picker (replaces hardcoded turbo/base/sft choices)
    result = pick_model(a["checkpoint_dir"])
    if result is None:
        if is_rich_active() and console is not None:
            console.print("  [yellow]No model directories found. Enter variant name manually.[/]")
        else:
            print("  No model directories found. Enter variant name manually.")
        a["model_variant"] = ask(
            "Model variant or folder name", default=a.get("model_variant", "turbo"),
            allow_back=True,
        )
        a["base_model"] = a["model_variant"]
    else:
        name, info = result
        a["model_variant"] = name
        a["base_model"] = info.base_model
        if not info.is_official and info.base_model == "unknown":
            a["base_model"] = prompt_base_model(name)


def _step_source(a: dict) -> None:
    """Dataset JSON or audio directory."""
    if is_rich_active() and console is not None:
        console.print(
            "\n  [dim]A dataset JSON provides lyrics, genre, BPM, key, and "
            "other metadata for each audio file, plus audio file paths.\n"
            "  Without it, you will be asked for an audio directory and all "
            "tracks will default to [Instrumental] with no genre/BPM info.[/]"
        )
    else:
        print(
            "\n  A dataset JSON provides lyrics, genre, BPM, key, and "
            "other metadata for each audio file, plus audio file paths.\n"
            "  Without it, you will be asked for an audio directory and all "
            "tracks will default to [Instrumental] with no genre/BPM info."
        )

    a["dataset_json"] = _ask_dataset_json(a.get("dataset_json"))

    if not a.get("dataset_json"):
        if is_rich_active() and console is not None:
            console.print("  [dim]Subdirectories will be scanned recursively.[/]")
        else:
            print("  Subdirectories will be scanned recursively.")
        a["audio_dir"] = ask_path(
            "Audio directory (source audio files)",
            default=a.get("audio_dir"),
            must_exist=True, allow_back=True,
        )
    else:
        a["audio_dir"] = None


def _ask_dataset_json(default: str | None) -> str | None:
    """Prompt for a dataset JSON path with search-nearby fallback.

    When the entered path is not found, searches common sibling
    directories (``datasets/``, ``data/``) and CWD for a matching
    filename before giving up.  Lets the user retry instead of
    silently falling through to audio-directory mode.
    """
    from acestep.training_v2.ui.prompt_helpers import ask_bool

    while True:
        dataset_json = ask(
            "Dataset JSON file (leave empty to skip)",
            default=default, allow_back=True,
        )
        if dataset_json in (None, "None", ""):
            return None

        resolved = _resolve_dataset_json(dataset_json)
        if resolved is not None:
            return str(resolved)

        # Not found -- offer to retry
        _print_not_found(dataset_json)
        if ask_bool("Try a different path?", default=True):
            default = dataset_json  # keep what they typed as the new default
            continue
        return None


def _resolve_dataset_json(raw_path: str) -> Path | None:
    """Try to find the dataset JSON, searching nearby if needed."""
    candidate = Path(raw_path).expanduser()

    # 1. Exact path (absolute or relative to CWD)
    resolved = candidate.resolve()
    if resolved.is_file():
        return resolved

    # 2. If they gave just a filename, search common subdirectories
    search_dirs = [
        Path.cwd(),
        Path.cwd() / "datasets",
        Path.cwd() / "data",
    ]
    name = candidate.name
    for d in search_dirs:
        p = (d / name).resolve()
        if p.is_file():
            _print_found_nearby(raw_path, p)
            return p

    # 3. Glob for the filename anywhere one level deep from CWD
    for match in sorted(Path.cwd().glob(f"*/{name}")):
        if match.is_file():
            _print_found_nearby(raw_path, match)
            return match

    return None


def _print_found_nearby(original: str, found: Path) -> None:
    """Tell the user we found their file at a different path."""
    if is_rich_active() and console is not None:
        console.print(f"  [yellow]'{_esc(original)}' not at that exact path,[/]")
        console.print(f"  [green]but found it at: {_esc(found)}[/]")
    else:
        print(f"  '{original}' not at that exact path,")
        print(f"  but found it at: {found}")


def _print_not_found(path: str) -> None:
    """Tell the user the file was not found anywhere."""
    if is_rich_active() and console is not None:
        console.print(f"  [red]Not found: {_esc(path)}[/]")
        console.print("  [dim]Searched CWD, datasets/, data/, and one level deep.[/]")
    else:
        print(f"  Not found: {path}")
        print("  Searched CWD, datasets/, data/, and one level deep.")


def _step_output(a: dict) -> None:
    """Output directory and max duration."""
    a["tensor_output"] = ask(
        "Output directory for .pt tensor files",
        default=a.get("tensor_output"),
        required=True, allow_back=True,
    )
    a["max_duration"] = ask(
        "Max audio duration in seconds",
        default=a.get("max_duration", 240.0),
        type_fn=float, allow_back=True,
    )


# ---- Step list and runner ---------------------------------------------------

_STEPS: list[tuple[str, Callable[..., Any]]] = [
    ("Model & Checkpoint", _step_model),
    ("Audio Source", _step_source),
    ("Output Settings", _step_output),
]


def wizard_preprocess() -> argparse.Namespace:
    """Interactive wizard for preprocessing.

    Returns:
        A populated ``argparse.Namespace`` with ``preprocess=True``.

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
        subcommand="fixed",
        plain=False,
        yes=True,
        _from_wizard=True,
        adapter_type="lora",
        checkpoint_dir=answers["checkpoint_dir"],
        model_variant=answers["model_variant"],
        base_model=answers.get("base_model", answers["model_variant"]),
        device="auto",
        precision="auto",
        dataset_dir=answers.get("tensor_output", ""),
        num_workers=DEFAULT_NUM_WORKERS,
        pin_memory=True,
        prefetch_factor=2 if DEFAULT_NUM_WORKERS > 0 else 0,
        persistent_workers=DEFAULT_NUM_WORKERS > 0,
        learning_rate=1e-4,
        batch_size=1,
        gradient_accumulation=4,
        epochs=100,
        warmup_steps=100,
        weight_decay=0.01,
        max_grad_norm=1.0,
        seed=42,
        rank=64,
        alpha=128,
        dropout=0.1,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        attention_type="both",
        bias="none",
        output_dir=native_path("./lora_output"),
        save_every=10,
        resume_from=None,
        log_dir=None,
        log_every=10,
        log_heavy_every=50,
        sample_every_n_epochs=0,
        optimizer_type="adamw",
        scheduler_type="cosine",
        gradient_checkpointing=True,
        offload_encoder=False,
        preprocess=True,
        audio_dir=answers.get("audio_dir"),
        dataset_json=answers.get("dataset_json"),
        tensor_output=answers.get("tensor_output"),
        max_duration=answers.get("max_duration", 240.0),
        cfg_ratio=0.15,
        estimate_batches=None,
        top_k=16,
        granularity="module",
        module_config=None,
        auto_estimate=False,
        estimate_output=None,
    )
