"""
Individual wizard steps for the training flow.

Each step function takes an ``answers`` dict and writes user responses
into it.  All prompts support ``allow_back=True`` for go-back navigation.
"""

from __future__ import annotations

from acestep.training_v2.ui import console, is_rich_active
from acestep.training_v2.ui.prompt_helpers import (
    IS_WINDOWS,
    DEFAULT_NUM_WORKERS,
    menu,
    ask,
    ask_path,
    ask_bool,
    native_path,
    section,
)


# ---- Basic steps ------------------------------------------------------------

def step_config_mode(a: dict) -> None:
    """Choose basic vs advanced configuration depth."""
    a["config_mode"] = menu(
        "How much do you want to configure?",
        [
            ("basic", "Basic (recommended defaults, fewer questions)"),
            ("advanced", "Advanced (all settings exposed)"),
        ],
        default=1,
        allow_back=True,
    )


def step_required(a: dict) -> None:
    """Collect required paths and model selection."""
    from acestep.training_v2.settings import get_checkpoint_dir
    from acestep.training_v2.model_discovery import (
        pick_model,
        prompt_base_model,
    )

    section("Required Settings")

    # Checkpoint dir: prefer settings default over hardcoded fallback
    ckpt_default = a.get("checkpoint_dir") or get_checkpoint_dir() or native_path("./checkpoints")
    a["checkpoint_dir"] = ask_path(
        "Checkpoint directory", default=ckpt_default,
        must_exist=True, allow_back=True,
    )

    # Model selection via interactive picker (replaces hardcoded choices)
    result = pick_model(a["checkpoint_dir"])
    if result is None:
        # No models found -- fall back to manual entry
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

        # If fine-tune with unknown base, ask the user
        if not info.is_official and info.base_model == "unknown":
            a["base_model"] = prompt_base_model(name)

    a["dataset_dir"] = ask_path(
        "Dataset directory (preprocessed .pt files)",
        default=a.get("dataset_dir"),
        must_exist=True, allow_back=True,
    )
    a["output_dir"] = ask(
        "Output directory for adapter weights",
        default=a.get("output_dir"),
        required=True, allow_back=True,
    )


def step_lora(a: dict) -> None:
    """LoRA hyperparameters."""
    section("LoRA Settings (press Enter for defaults)")
    a["rank"] = ask("Rank", default=a.get("rank", 64), type_fn=int, allow_back=True)
    a["alpha"] = ask("Alpha", default=a.get("alpha", 128), type_fn=int, allow_back=True)
    a["dropout"] = ask("Dropout", default=a.get("dropout", 0.1), type_fn=float, allow_back=True)

    a["attention_type"] = menu(
        "Which attention layers to target?",
        [
            ("both", "Both self-attention and cross-attention"),
            ("self", "Self-attention only (audio patterns)"),
            ("cross", "Cross-attention only (text conditioning)"),
        ],
        default=1,
        allow_back=True,
    )

    a["target_modules_str"] = ask(
        "Target projections",
        default=a.get("target_modules_str", "q_proj k_proj v_proj o_proj"),
        allow_back=True,
    )


def step_lokr(a: dict) -> None:
    """LoKR hyperparameters (LyCORIS Kronecker adapter)."""
    section("LoKR Settings (press Enter for defaults)")
    a["lokr_linear_dim"] = ask("Linear dimension", default=a.get("lokr_linear_dim", 64), type_fn=int, allow_back=True)
    a["lokr_linear_alpha"] = ask("Linear alpha", default=a.get("lokr_linear_alpha", 128), type_fn=int, allow_back=True)
    a["lokr_factor"] = ask("Factor (-1 = auto)", default=a.get("lokr_factor", -1), type_fn=int, allow_back=True)

    a["lokr_decompose_both"] = ask_bool(
        "Decompose both Kronecker factors?",
        default=a.get("lokr_decompose_both", False),
        allow_back=True,
    )
    a["lokr_use_tucker"] = ask_bool(
        "Use Tucker decomposition?",
        default=a.get("lokr_use_tucker", False),
        allow_back=True,
    )
    a["lokr_use_scalar"] = ask_bool(
        "Use scalar scaling?",
        default=a.get("lokr_use_scalar", False),
        allow_back=True,
    )
    a["lokr_weight_decompose"] = ask_bool(
        "Enable DoRA-style weight decomposition?",
        default=a.get("lokr_weight_decompose", False),
        allow_back=True,
    )

    a["attention_type"] = menu(
        "Which attention layers to target?",
        [
            ("both", "Both self-attention and cross-attention"),
            ("self", "Self-attention only (audio patterns)"),
            ("cross", "Cross-attention only (text conditioning)"),
        ],
        default=1,
        allow_back=True,
    )

    a["target_modules_str"] = ask(
        "Target projections",
        default=a.get("target_modules_str", "q_proj k_proj v_proj o_proj"),
        allow_back=True,
    )


def _default_shift(a: dict) -> float:
    """Return default shift value based on selected model variant."""
    base = a.get("base_model", a.get("model_variant", "turbo"))
    if isinstance(base, str) and "turbo" in base.lower():
        return 3.0
    return 1.0


def _default_inference_steps(a: dict) -> int:
    """Return default num_inference_steps based on selected model variant."""
    base = a.get("base_model", a.get("model_variant", "turbo"))
    if isinstance(base, str) and "turbo" in base.lower():
        return 8
    return 50


def step_training(a: dict) -> None:
    """Core training hyperparameters."""
    section("Training Settings (press Enter for defaults)")
    a["learning_rate"] = ask("Learning rate", default=a.get("learning_rate", 1e-4), type_fn=float, allow_back=True)
    a["batch_size"] = ask("Batch size", default=a.get("batch_size", 1), type_fn=int, allow_back=True)
    a["gradient_accumulation"] = ask("Gradient accumulation", default=a.get("gradient_accumulation", 4), type_fn=int, allow_back=True)
    a["epochs"] = ask("Max epochs", default=a.get("epochs", 100), type_fn=int, allow_back=True)
    a["warmup_steps"] = ask("Warmup steps", default=a.get("warmup_steps", 100), type_fn=int, allow_back=True)
    a["seed"] = ask("Seed", default=a.get("seed", 42), type_fn=int, allow_back=True)

    # Shift & inference steps -- auto-default from model variant
    a["shift"] = ask(
        "Shift (turbo=3.0, base/sft=1.0)",
        default=a.get("shift", _default_shift(a)),
        type_fn=float, allow_back=True,
    )
    a["num_inference_steps"] = ask(
        "Inference steps (turbo=8, base/sft=50)",
        default=a.get("num_inference_steps", _default_inference_steps(a)),
        type_fn=int, allow_back=True,
    )


def step_cfg(a: dict) -> None:
    """CFG dropout (fixed mode only)."""
    section("Corrected Training Settings (press Enter for defaults)")
    a["cfg_ratio"] = ask("CFG dropout ratio", default=a.get("cfg_ratio", 0.15), type_fn=float, allow_back=True)


def step_logging(a: dict) -> None:
    """Logging and checkpoint settings."""
    import os

    section("Logging & Checkpoints (press Enter for defaults)")
    a["save_every"] = ask("Save checkpoint every N epochs", default=a.get("save_every", 10), type_fn=int, allow_back=True)
    a["log_every"] = ask("Log metrics every N steps", default=a.get("log_every", 10), type_fn=int, allow_back=True)
    resume_raw = ask("Resume from checkpoint path (leave empty to skip)", default=a.get("resume_from"), allow_back=True)
    if resume_raw in (None, "None", ""):
        a["resume_from"] = None
    else:
        # Normalize: if user pointed to a file (e.g. adapter_config.json),
        # use the containing directory instead.
        if os.path.isfile(resume_raw):
            parent = os.path.dirname(resume_raw)
            if is_rich_active() and console is not None:
                console.print(
                    f"  [yellow]That's a file -- using checkpoint directory: {parent}[/]"
                )
            else:
                print(f"  That's a file -- using checkpoint directory: {parent}")
            resume_raw = parent
        a["resume_from"] = resume_raw


# ---- Advanced steps ---------------------------------------------------------

def step_advanced_device(a: dict) -> None:
    """Advanced: device and precision."""
    section("Device & Precision (Advanced, press Enter for defaults)")
    a["device"] = ask("Device", default=a.get("device", "auto"), choices=["auto", "cuda", "cuda:0", "cuda:1", "mps", "xpu", "cpu"], allow_back=True)
    a["precision"] = ask("Precision", default=a.get("precision", "auto"), choices=["auto", "bf16", "fp16", "fp32"], allow_back=True)


def step_advanced_optimizer(a: dict) -> None:
    """Advanced: optimizer and scheduler."""
    section("Optimizer & Scheduler (press Enter for defaults)")
    a["optimizer_type"] = menu(
        "Which optimizer to use?",
        [
            ("adamw", "AdamW (default, reliable)"),
            ("adamw8bit", "AdamW 8-bit (saves ~30% optimizer VRAM, needs bitsandbytes)"),
            ("adafactor", "Adafactor (minimal state memory)"),
            ("prodigy", "Prodigy (auto-tunes LR -- set LR to 1.0, needs prodigyopt)"),
        ],
        default=1,
        allow_back=True,
    )
    if a["optimizer_type"] == "prodigy":
        a["learning_rate"] = ask("Learning rate (Prodigy: use 1.0)", default=1.0, type_fn=float, allow_back=True)

    a["scheduler_type"] = menu(
        "LR scheduler?",
        [
            ("cosine", "Cosine Annealing (smooth decay to near-zero, most popular)"),
            ("cosine_restarts", "Cosine with Restarts (cyclical decay, LR resets periodically)"),
            ("linear", "Linear (steady decay to near-zero)"),
            ("constant", "Constant (flat LR after warmup)"),
            ("constant_with_warmup", "Constant with Warmup (explicit warmup then flat)"),
        ],
        default=1,
        allow_back=True,
    )


def step_advanced_vram(a: dict) -> None:
    """Advanced: VRAM savings."""
    section("VRAM Savings (Advanced, press Enter for defaults)")
    a["gradient_checkpointing"] = ask_bool(
        "Enable gradient checkpointing? (saves ~40-60% activation VRAM, ~10-30% slower)",
        default=a.get("gradient_checkpointing", True),
        allow_back=True,
    )
    a["offload_encoder"] = ask_bool(
        "Offload encoder/VAE to CPU? (saves ~2-4GB VRAM after setup)",
        default=a.get("offload_encoder", False),
        allow_back=True,
    )


def step_advanced_training(a: dict) -> None:
    """Advanced: weight decay, grad norm, bias."""
    section("Advanced Training Settings (press Enter for defaults)")
    a["weight_decay"] = ask("Weight decay", default=a.get("weight_decay", 0.01), type_fn=float, allow_back=True)
    a["max_grad_norm"] = ask("Max gradient norm", default=a.get("max_grad_norm", 1.0), type_fn=float, allow_back=True)
    a["bias"] = ask("Bias training mode", default=a.get("bias", "none"), choices=["none", "all", "lora_only"], allow_back=True)


def step_advanced_dataloader(a: dict) -> None:
    """Advanced: DataLoader tuning."""
    section("Data Loading (Advanced, press Enter for defaults)")
    a["num_workers"] = ask("DataLoader workers", default=a.get("num_workers", DEFAULT_NUM_WORKERS), type_fn=int, allow_back=True)
    if IS_WINDOWS and a["num_workers"] > 0:
        if is_rich_active() and console is not None:
            console.print("  [yellow]Warning: Windows detected -- forcing num_workers=0[/]")
        else:
            print("  Warning: Windows detected -- forcing num_workers=0")
        a["num_workers"] = 0
    a["pin_memory"] = ask_bool("Pin memory for GPU transfer?", default=a.get("pin_memory", True), allow_back=True)
    a["prefetch_factor"] = ask("Prefetch factor", default=a.get("prefetch_factor", 2 if a["num_workers"] > 0 else 0), type_fn=int, allow_back=True)
    a["persistent_workers"] = ask_bool("Keep workers alive between epochs?", default=a.get("persistent_workers", a["num_workers"] > 0), allow_back=True)


def step_advanced_logging(a: dict) -> None:
    """Advanced: TensorBoard logging."""
    section("Advanced Logging (press Enter for defaults)")
    log_dir_raw = ask("TensorBoard log directory (leave empty for default)", default=a.get("log_dir"), allow_back=True)
    a["log_dir"] = None if log_dir_raw in (None, "None", "") else log_dir_raw
    a["log_heavy_every"] = ask("Log gradient norms every N steps", default=a.get("log_heavy_every", 50), type_fn=int, allow_back=True)
    a["sample_every_n_epochs"] = ask("Generate sample every N epochs (0=disabled)", default=a.get("sample_every_n_epochs", 0), type_fn=int, allow_back=True)
