## Overview

Side-Step supports two adapter types and two training modes:

|                    | Corrected (Fixed) | Vanilla (Original)          |
| ------------------ | ----------------- | --------------------------- |
| **LoRA** (PEFT)    | Recommended       | For reproducing old results |
| **LoKR** (LyCORIS) | Experimental      | Experimental                |

**Corrected mode** (the default and recommended path) uses:
- Continuous logit-normal timestep sampling (matches how base/SFT were trained)
- 15% CFG dropout (teaches the model to handle prompted and unprompted generation)
- Standalone -- no base ACE-Step installation needed

**Vanilla mode** reproduces the original ACE-Step training behavior:
- Discrete 8-step timestep schedule
- No CFG dropout
- Requires base ACE-Step installed alongside

---

## Quick Start: Wizard

The easiest way to train is the interactive wizard:

```bash
uv run python train.py
```

The wizard walks you through:
1. Selecting adapter type (LoRA or LoKR)
2. Choosing training mode (Corrected or Vanilla)
3. Picking your model (interactive selector with fuzzy search)
4. Setting hyperparameters (Basic mode uses good defaults, Advanced exposes everything)
5. Confirming and starting

### Wizard Features

- **Go-back navigation**: Type `b` at any prompt to return to the previous question
- **Presets**: Save and load named configurations (main menu > Manage presets)
- **Flow chaining**: After preprocessing, the wizard offers to start training immediately
- **Settings**: Configure checkpoint paths and vanilla mode (main menu > Settings)
- **Session loop**: The wizard stays open after each action -- no need to restart

---

## Quick Start: CLI

For automated pipelines or when you know exactly what you want:

### Preprocessing

Convert raw audio to training tensors:

```bash
# With a dataset JSON (lyrics, genre, BPM metadata)
uv run python train.py fixed \
    --checkpoint-dir ../ACE-Step-1.5/checkpoints \
    --model-variant base \
    --preprocess \
    --dataset-json ./my_dataset.json \
    --audio-dir ./my_audio \
    --tensor-output ./my_tensors

# Without metadata (all tracks treated as instrumentals)
uv run python train.py fixed \
    --checkpoint-dir ../ACE-Step-1.5/checkpoints \
    --model-variant base \
    --preprocess \
    --audio-dir ./my_audio \
    --tensor-output ./my_tensors
```

Preprocessing runs in two passes to minimize VRAM:
1. **Pass 1** -- VAE + Text Encoder (~3 GB): encodes audio to latents, text to embeddings
2. **Pass 2** -- DiT Encoder (~6 GB): generates condition encodings

### Training

```bash
# LoRA (stable, recommended)
uv run python train.py fixed \
    --checkpoint-dir ../ACE-Step-1.5/checkpoints \
    --model-variant base \
    --dataset-dir ./my_tensors \
    --output-dir ./output/my_lora \
    --epochs 100 \
    --lr 1e-4

# LoKR (experimental)
uv run python train.py fixed \
    --checkpoint-dir ../ACE-Step-1.5/checkpoints \
    --model-variant base \
    --adapter-type lokr \
    --dataset-dir ./my_tensors \
    --output-dir ./output/my_lokr \
    --epochs 100

# Training on a fine-tune
uv run python train.py fixed \
    --checkpoint-dir ../ACE-Step-1.5/checkpoints \
    --model-variant my-custom-finetune \
    --base-model base \
    --dataset-dir ./my_tensors \
    --output-dir ./output/finetune_lora
```

---

## LoRA vs LoKR

### LoRA (Low-Rank Adaptation)

- Uses the PEFT library
- Well-tested, stable, widely supported
- Adds low-rank matrices to attention layers
- Good default: rank 64, alpha 128

### LoKR (Low-Rank Kronecker)

- Uses the LyCORIS library (included automatically)
- **Experimental** -- may have rough edges
- Uses Kronecker product factorization instead of simple low-rank decomposition
- May capture different patterns than LoRA
- Additional options: Tucker decomposition, DoRA-style weight decomposition

> **Warning:** LoKR is experimental. The LyCORIS + Lightning Fabric interaction has not been exhaustively tested. If you encounter issues, fall back to LoRA.

### Preprocessing is adapter-agnostic

Preprocessing produces the same tensors regardless of whether you plan to train with LoRA or LoKR. The adapter type only affects how trainable weights are injected into the model during training -- it does not change the data pipeline. You only need to preprocess your audio once, and the resulting `.pt` files work for both adapter types.

---

## Hyperparameter Guide

### Learning Rate

| Optimizer | Recommended LR | Notes |
|-----------|----------------|-------|
| AdamW | `1e-4` | Standard choice |
| AdamW8bit | `1e-4` | Same as AdamW but saves ~30% optimizer VRAM |
| Adafactor | `1e-4` | Minimal state memory |
| Prodigy | `1.0` | Auto-tunes the actual LR. Set scheduler to `constant` |

### Rank (LoRA) / Linear Dim (LoKR)

| Rank | Capacity | VRAM | Use Case |
|------|----------|------|----------|
| 16 | Low | Minimal | Quick tests, very small datasets |
| 64 | Medium | Standard | Recommended default |
| 128 | High | Higher | Large datasets, maximum quality |

### Epochs

Depends heavily on dataset size:
- **1-10 songs**: 200-500 epochs
- **10-50 songs**: 100-200 epochs
- **50+ songs**: 50-100 epochs

Watch the loss curve in TensorBoard. If it plateaus, you can stop early.

### VRAM Optimization

Side-Step applies several optimizations automatically and exposes others as options. For the full deep-dive, see [[VRAM Optimization Guide]].

**Automatic (no user action needed):**

1. **Gradient checkpointing** (ON by default) -- recomputes activations during backward pass, saves ~40-60% activation VRAM (~10-30% slower). Matches what the original ACE-Step trainer always did.
2. **Flash Attention 2** (auto-installed) -- fused attention kernels for better GPU utilization. Requires Ampere+ GPU (RTX 30xx or newer). Falls back to SDPA on older hardware.

**User-configurable (from least to most aggressive):**

3. **Batch size 1** (default) -- minimum memory per step
4. **8-bit optimizer** (`--optimizer-type adamw8bit`) -- saves ~30% optimizer VRAM
5. **Encoder offloading** (`--offload-encoder`) -- saves ~2-4 GB after setup
6. **Lower rank** (16 instead of 64) -- fewer trainable parameters

---

## Monitoring Training

### TensorBoard

Side-Step logs training metrics to TensorBoard automatically:

```bash
# In a separate terminal
tensorboard --logdir ./output/my_lora/runs

# Then open http://localhost:6006 in your browser
```

Key metrics to watch:
- **loss/train** -- Should decrease over time. Spikes are normal but persistent increase means overfitting
- **lr** -- Learning rate schedule. Should warm up then follow your chosen scheduler
- **grad_norm/** -- Per-layer gradient norms (logged every `--log-heavy-every` steps)

### Log File

All sessions append to `sidestep.log` in the working directory. This captures full tracebacks and debug-level messages that may not appear in the terminal. Useful for diagnosing issues.

---

## Resuming Training

If training is interrupted, resume from a checkpoint:

```bash
uv run python train.py fixed \
    --checkpoint-dir ../ACE-Step-1.5/checkpoints \
    --model-variant base \
    --dataset-dir ./my_tensors \
    --output-dir ./output/my_lora \
    --resume-from ./output/my_lora/checkpoint-epoch-50
```

The checkpoint contains LoRA/LoKR weights, optimizer state, and scheduler state. Training continues from where it left off.

---

## Gradient Estimation

Before training, you can analyze which attention modules are most sensitive to your dataset:

```bash
uv run python train.py estimate \
    --checkpoint-dir ../ACE-Step-1.5/checkpoints \
    --model-variant base \
    --dataset-dir ./my_tensors \
    --estimate-batches 5 \
    --top-k 16
```

This ranks modules by gradient sensitivity. Useful for:
- Deciding which `--target-modules` to use
- Understanding what your dataset teaches the model
- Comparing different datasets

---

## See Also

- [[Getting Started]] -- Installation and setup
- [[Model Management]] -- Checkpoint structure and fine-tune support
- [[Shift and Timestep Sampling]] -- How training timesteps work, what shift actually does, Side-Step vs upstream
- [[Estimation Guide]] -- How to use and read gradient sensitivity analysis
- [[VRAM Optimization Guide]] -- VRAM profiles, GPU tiers, and complete wizard settings reference
