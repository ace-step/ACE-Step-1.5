# [BETA] Side-Step for ACE-Step 1.5

```bash
  ███████ ██ ██████  ███████       ███████ ████████ ███████ ██████
  ██      ██ ██   ██ ██            ██         ██    ██      ██   ██
  ███████ ██ ██   ██ █████   █████ ███████    ██    █████   ██████
       ██ ██ ██   ██ ██                 ██    ██    ██      ██
  ███████ ██ ██████  ███████       ███████    ██    ███████ ██
  by dernet     ((BETA TESTING))
```

**Side-Step** is a **standalone** training toolkit for [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) models. It provides corrected LoRA and LoKR fine-tuning implementations that fix fundamental bugs (for models other than turbo) in the original trainer while adding low-VRAM support for local GPUs.

> **Standalone?** Yes. Side-Step installs as its own project with its own dependencies. The corrected (fixed) training loop, preprocessing, and wizard all work without a base ACE-Step installation -- you only need the model checkpoints. Vanilla training mode still requires base ACE-Step installed alongside.


## Why Side-Step?

The original ACE-Step trainer has two critical discrepancies from how the base models were actually trained. Side-Step was built to bridge this gap:

1.  **Continuous Timestep Sampling:** The original trainer uses a discrete 8-step schedule. This is fine for turbo, which the original training script is hardcoded for. Side-Step implements **Logit-Normal continuous sampling**, ensuring the model learns the full range of the denoising process.
2.  **CFG Dropout (Classifier-Free Guidance):** The original trainer lacks condition dropout. Side-Step implements a **15% null-condition dropout**, teaching the model how to handle both prompted and unprompted generation. Without this, inference quality suffers.
3.  **Standalone Core:** The corrected training loop, preprocessing, and wizard bundle all required ACE-Step utilities. No base ACE-Step install needed -- just the model weights.
4.  **Built for the cloud:** The original Gradio breaks when you try to use it for training. Use this instead :)

---

## Beta Status & Support
**Current Version:** 0.8.0-beta

| Feature | Status | Standalone? | Note |
| :--- | :--- | :--- | :--- |
| **Fixed Training (LoRA)** | Working | Yes | Recommended for all users. Corrected timesteps + CFG dropout. |
| **Fixed Training (LoKR)** | **Experimental** | Yes | Uses LyCORIS. May have rough edges. |
| **Vanilla Training** | Working | **No** | Reproduction of original behavior. Requires base ACE-Step 1.5 installed alongside. |
| **Interactive Wizard** | Working | Yes | `python train.py` with no args. Session loop, go-back, presets, first-run setup. |
| **CLI Preprocessing** | Beta | Yes | Two-pass pipeline, low VRAM. Adapter-agnostic (same tensors for LoRA and LoKR). |
| **Gradient Estimation** | Beta | Yes | Ranks attention modules by sensitivity. In Experimental menu. |
| **Presets System** | Working | Yes | Save/load/manage training configurations. Stores adapter type. |
| **TUI (Textual UI)** | **BROKEN** | -- | Do not use `sidestep_tui.py` yet. |

> **Something broken?** This is a beta. You can always roll back:
> ```bash
> git log --oneline -5   # find the commit you want
> git checkout <hash>
> ```
> If you hit issues, please open an issue -- it helps us stabilize faster.

### What's new in 0.8.0-beta

**Bug fixes:**
- **Fixed gradient checkpointing crash** -- Training with gradient checkpointing enabled (the default) would crash with `element 0 of tensors does not require grad`. The autograd graph was disconnecting through checkpointed segments because the `xt` input tensor wasn't carrying gradients. Now forces `xt.requires_grad_(True)` when checkpointing is active, matching ACE-Step's upstream behavior. This was the #1 blocker for new users.
- **Fixed training completing with 0 steps on Windows** -- Lightning Fabric's `setup_dataloaders()` was wrapping the DataLoader with a shim that yielded 0 batches on Windows, causing training to silently "complete" with 0 epochs and 0 steps. Reported by multiple users on RTX 3090 and other GPUs. The Fabric DataLoader wrapping is now skipped entirely (the model/optimizer are still Fabric-managed for mixed precision).
- **Fixed multi-GPU device selection** -- Using `cuda:1` (or any non-default GPU) no longer causes training to silently fail. The Fabric device setup has been rewritten to use `torch.cuda.set_device()` instead of passing device indices as lists.
- **LoRA save path fix** -- Adapter files (`adapter_config.json`, `adapter_model.safetensors`) are now saved directly into the output directory. Previously they were nested in an `adapter/` subdirectory, causing Gradio/ComfyUI to fail to find the weights at the path Side-Step reported.
- **Massive VRAM reduction** -- Gradient checkpointing is now ON by default and actually works (see above fix). Measured at ~7 GiB for batch size 1 on a 48 GiB GPU (15% utilization). Previously Side-Step had checkpointing off or broken, causing 20-42 GiB VRAM usage. This brings Side-Step well below ACE-Step's memory footprint.
- **0-step training detection** -- If training completes with zero steps processed, Side-Step now reports a clear `[FAIL]` error instead of a misleading "Training Complete" screen with 0 epochs.
- **Windows `num_workers` safety** -- Explicitly clamps `num_workers=0` on Windows even if overridden via CLI, preventing spawn-based multiprocessing crashes.

**Features:**
- **Inference-ready checkpoints** -- Intermediate checkpoints (`checkpoints/epoch_N/`) now save adapter files flat alongside `training_state.pt`. Point any inference tool directly at a checkpoint directory -- no more digging into nested subdirectories. Checkpoints are usable for both inference AND resume.
- **Resume support in basic training loop** -- The non-Fabric fallback loop now supports `--resume-from`, matching the Fabric path.
- **VRAM-tier presets** -- Four new built-in presets (`vram_24gb_plus`, `vram_16gb`, `vram_12gb`, `vram_8gb`) with tuned settings for each GPU tier. Rank, optimizer, batch size, and offloading are pre-configured for your VRAM budget.
- **Flash Attention 2 auto-installed** -- Prebuilt wheels are now a default dependency. No compilation, no `--extra flash`. Falls back to SDPA silently on unsupported hardware.
- **Banner shows version** -- The startup banner now displays the Side-Step version for easier bug reporting.

### What's new in 0.7.0-beta

- **Truly standalone packaging** -- Side-Step is now its own project with a real `pyproject.toml` and full dependency list. Install it with `uv sync` -- no ACE-Step overlay required. The installer now creates Side-Step alongside ACE-Step as sibling directories.
- **First-run setup wizard** -- On first launch, Side-Step walks you through configuring your checkpoint directory, ACE-Step path (if you want vanilla mode), and validates your setup. Accessible any time from the main menu under "Settings".
- **Model discovery with fuzzy search** -- Instead of hardcoded `turbo/base/sft` choices, the wizard now scans your checkpoint directory for all model folders, labels official vs custom models, and lets you pick by number or search by name. Fine-tunes with arbitrary folder names are fully supported.
- **Fine-tune training support** -- Train on custom fine-tunes by selecting their folder. Side-Step auto-detects the base model from `config.json`. If it can't, it asks which base the fine-tune descends from to condition timestep sampling correctly.
- **`--base-model` CLI argument** -- New flag for CLI users training on fine-tunes. Overrides timestep parameters when `config.json` doesn't contain them.
- **`--model-variant` accepts any folder name** -- No longer restricted to turbo/base/sft. Pass any subfolder name from your checkpoints directory (e.g., `--model-variant my-custom-finetune`).
- **`acestep.__path__` extension** -- When vanilla mode is configured, Side-Step extends its package path to reach ACE-Step's modules. No overlay, no symlinks, no `sys.path` hacks.
- **Settings persistence** -- Checkpoint dir, ACE-Step path, and vanilla intent are saved to `~/.config/sidestep/settings.json` and reused as defaults in subsequent sessions.

### What's new in 0.6.0-beta

- **Mostly standalone** -- The corrected (fixed) training loop, preprocessing pipeline, and wizard no longer require a base ACE-Step installation. All needed ACE-Step utilities are vendored in `_vendor/`. You only need the model checkpoint files. Vanilla training mode still requires base ACE-Step.
- **Enhanced prompt builder** -- Preprocessing now supports `custom_tag`, `genre`, and `prompt_override` fields from dataset JSON metadata, matching upstream feature parity without the AudioSample dependency.
- **Hardened metadata lookup** -- Dataset JSON entries with `audio_path` but no `filename` field are now handled correctly (basename is extracted as fallback key).

### What's new in 0.5.0-beta

- **LoKR adapter support (experimental)** -- Train LoKR (Low-Rank Kronecker) adapters via [LyCORIS](https://github.com/KohakuBlueleaf/LyCORIS) as an alternative to LoRA. LoKR uses Kronecker product factorization and may capture different patterns than LoRA. **This is experimental and may break.** The underlying LyCORIS + Fabric interaction has not been exhaustively tested across all hardware.
- **Restructured wizard menu** -- The main menu now offers "Train a LoRA" and "Train a LoKR" as distinct top-level choices, each leading to a corrected/vanilla sub-menu
- **Unified preprocessing** -- Preprocessing is adapter-agnostic: the same tensors work for both LoRA and LoKR. The adapter type only affects weight injection during training, not the data pipeline. *(Previously, LoKR had a separate preprocessing mode that incorrectly fed target audio into context latents, giving the decoder the answer during training and producing misleadingly low loss.)*
- **LoKR-aware presets** -- Presets now save and restore adapter type and all LoKR-specific hyperparameters

### What's new in 0.4.0-beta

- **Session loop** -- the wizard no longer exits after each action; preprocess, train, and manage presets in one session
- **Go-back navigation** -- type `b` at any prompt to return to the previous question
- **Step indicators** -- `[Step 3/8] LoRA Settings` shows your progress through each flow
- **Presets system** -- save, load, import, and export named training configurations
- **Flow chaining** -- after preprocessing, the wizard offers to start training immediately
- **Experimental submenu** -- gradient estimation and upcoming features live here
- **GPU cleanup** -- memory is released between session loop iterations to prevent VRAM leaks
- **Config summaries** -- preprocessing and estimation show a summary before starting
- **Basic/Advanced mode** -- choose how many questions the training wizard asks

---

## Prerequisites

- **Python 3.11+** -- Managed automatically by `uv`. If using pip, install Python 3.11 manually.
- **NVIDIA GPU with CUDA support** -- CUDA 12.x recommended. AMD and Intel GPUs are not supported.
- **8 GB+ VRAM** -- See [VRAM Profiles](#optimization--vram-profiles) for per-tier settings. Training is possible on 8 GB GPUs with aggressive optimization.
- **Git** -- Required for cloning repositories and version management.
- **uv** (recommended) or **pip** -- `uv` handles Python, PyTorch+CUDA, and all dependencies automatically. Plain pip requires manual PyTorch installation.

---

## Installation

Side-Step is **partly standalone**: the corrected training loop, preprocessing, wizard, and all CLI tools work without a base ACE-Step installation. You only need the model checkpoint files. The only thing that requires ACE-Step installed alongside is **vanilla training mode** (which reproduces the original bugged behavior for backward compatibility).

We **strongly recommend** using [uv](https://docs.astral.sh/uv/) for dependency management -- it handles Python 3.11, PyTorch with CUDA, Flash Attention wheels, and all other dependencies automatically.

### Windows (Easy Install)

Download or clone Side-Step, then double-click **`install_windows.bat`** (or run the PowerShell script). It handles everything: uv, Python 3.11, Side-Step deps, ACE-Step (alongside for checkpoints), and model download.

```powershell
# Or run from PowerShell directly:
git clone https://github.com/koda-dernet/Side-Step.git
cd Side-Step
.\install_windows.ps1
```

The installer creates two sibling directories:
- `Side-Step/` -- your training toolkit (standalone)
- `ACE-Step-1.5/` -- model checkpoints + optional vanilla mode

### Linux / macOS (Recommended: uv)

```bash
# 1. Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone Side-Step
git clone https://github.com/koda-dernet/Side-Step.git
cd Side-Step

# 3. Install dependencies (includes PyTorch with CUDA + Flash Attention)
uv sync

# 4. First run will guide you through setup (checkpoint path, etc.)
uv run python train.py
```

### Model Checkpoints

You need the model weights before you can train. Options:

1. **From ACE-Step (recommended):** Clone ACE-Step 1.5 alongside Side-Step and use `acestep-download`:
   ```bash
   git clone https://github.com/ace-step/ACE-Step-1.5.git
   cd ACE-Step-1.5 && uv sync && uv run acestep-download
   ```
   Then point Side-Step at the checkpoints folder on first run or via `--checkpoint-dir ../ACE-Step-1.5/checkpoints`.
2. **Manual download:** Get the weights from [HuggingFace](https://huggingface.co/ACE-Step/Ace-Step1.5) and place them in a `checkpoints/` directory inside Side-Step.

> **IMPORTANT: Never rename checkpoint folders.** The model loader uses folder names and `config.json` files to identify model variants (turbo, base, sft). Renaming them will break loading.

### Vanilla Mode (optional -- requires ACE-Step)

Vanilla training mode reproduces the original ACE-Step training behavior (bugged discrete timesteps, no CFG dropout). Most users should use **fixed** mode instead. If you specifically need vanilla mode:

```bash
# Clone ACE-Step alongside Side-Step
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5 && uv sync && cd ..

# On first run, Side-Step's setup wizard will ask if you want vanilla mode
# and where your ACE-Step installation is.
```

> **Note:** With plain pip, you are responsible for installing the correct PyTorch version with CUDA support for your platform. This is the #1 source of "it doesn't work" issues. `uv sync` handles this automatically.

### Included automatically

Everything is installed by `uv sync` -- no extras, no manual pip installs:

- **Flash Attention 2** -- Prebuilt wheels, no compilation. Auto-detected on Ampere+ GPUs (RTX 30xx+). Falls back to SDPA on older hardware or macOS.
- **Gradient checkpointing** -- Enabled by default. Cuts VRAM dramatically (~7 GiB for batch size 1, down from 20-42 GiB without it).
- **PyTorch with CUDA 12.8** -- Correct CUDA-enabled build per platform.
- **bitsandbytes** -- 8-bit optimizers (AdamW8bit) for ~30-40% optimizer VRAM savings.
- **Prodigy** -- Adaptive optimizer that auto-tunes learning rate.
- **LyCORIS** -- LoKR adapter support (experimental Kronecker product adapters).

---

## Platform Compatibility

| Platform | Status | Notes |
| :--- | :--- | :--- |
| **Linux (CUDA)** | Primary | Developed and tested here |
| **Windows (CUDA)** | Supported | Easy installer included; DataLoader workers auto-set to 0 |
| **macOS (MPS)** | Experimental | Apple Silicon only; some ops may fall back to CPU |

---

## Usage

### Option A: The Interactive Wizard (Recommended)
Simply run the script with no arguments. The wizard now stays open in a session loop -- you can preprocess, configure, train, and manage presets without restarting.
```bash
# With uv (recommended)
uv run python train.py

# Without uv
python train.py
```

The wizard supports:
- **Go-back**: Type `b` at any prompt to return to the previous question
- **Presets**: Save and load named training configurations
- **Flow chaining**: After preprocessing, jump straight to training
- **Basic/Advanced modes**: Choose how detailed you want the configuration

### Option B: The Quick Start One-Liner
If you have your preprocessed tensors ready in `./my_data`, run:
```bash
# LoRA (default)
uv run python train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --dataset-dir ./my_data \
    --output-dir ./output/my_lora \
    --epochs 100

# LoKR (experimental)
uv run python train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --adapter-type lokr \
    --dataset-dir ./my_data \
    --output-dir ./output/my_lokr \
    --epochs 100
```

### Option C: Preprocess Audio (Two-Pass, Low VRAM)
Convert raw audio files into `.pt` tensors without loading all models at once.
The pipeline runs in two passes: (1) VAE + Text Encoder (~3 GB), then (2) DIT encoder (~6 GB).
```bash
uv run python train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --preprocess \
    --audio-dir ./my_audio \
    --tensor-output ./my_tensors
```
With a metadata JSON for lyrics/genre/BPM:
```bash
uv run python train.py fixed \
    --checkpoint-dir ./checkpoints \
    --preprocess \
    --audio-dir ./my_audio \
    --dataset-json ./my_dataset.json \
    --tensor-output ./my_tensors
```

### Option D: Gradient Estimation
Find which attention modules learn fastest for your dataset (useful for rank/target selection):
```bash
uv run python train.py estimate \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --dataset-dir ./my_tensors \
    --estimate-batches 5 \
    --top-k 16
```

### Option E: Vanilla Training (Requires ACE-Step)
Reproduces the original ACE-Step training behavior (bugged discrete timesteps, no CFG dropout). Most users should use **fixed** mode instead. Requires a base ACE-Step installation alongside Side-Step:
```bash
uv run python train.py vanilla \
    --checkpoint-dir ./ACE-Step-1.5/checkpoints \
    --audio-dir ./my_audio \
    --output-dir ./output/my_vanilla_lora
```

> **Advanced subcommands:** `selective` (corrected training with dataset-specific module selection) and `compare-configs` (compare module config JSON files) are also available. These are advanced/WIP features -- run `uv run train.py selective --help` or `uv run train.py compare-configs --help` for details.

---

## Presets

Side-Step ships with seven built-in presets:

| Preset | Description |
| :--- | :--- |
| `recommended` | Balanced defaults for most LoRA fine-tuning tasks |
| `high_quality` | Rank 128, 1000 epochs -- for when quality matters most |
| `quick_test` | Rank 16, 10 epochs -- fast iteration for testing |
| `vram_24gb_plus` | Comfortable tier -- Rank 128, Batch 2, AdamW |
| `vram_16gb` | Standard tier -- Rank 64, Batch 1, AdamW |
| `vram_12gb` | Tight tier -- Rank 32, AdamW8bit, Encoder offloading |
| `vram_8gb` | Minimal tier -- Rank 16, AdamW8bit, Encoder offloading, High grad accumulation |

User presets are saved to `./presets/` (project-local, next to your training data). This ensures presets persist across Docker runs and stay visible alongside your project. Presets from the global location (`~/.config/sidestep/presets/`) are also scanned as a fallback. You can import/export presets as JSON files to share with others.

---

## Optimization & VRAM Profiles
Side-Step is optimized for both heavy Cloud GPUs (H100/A100) and local "underpowered" gear (RTX 3060/4070).

**Applied automatically (no configuration needed):**
- **Gradient checkpointing** (ON by default) -- recomputes activations during backward, saves ~40-60% activation VRAM. This matches the original ACE-Step behavior.
- **Flash Attention 2** (auto-installed) -- fused attention kernels for better GPU utilization. Requires Ampere+ GPU (RTX 30xx+). Falls back to SDPA on older hardware.

| Profile | VRAM | Key Settings |
| :--- | :--- | :--- |
| **Comfortable** | 24 GB+ | AdamW, Batch 2+, Rank 64-128 |
| **Standard** | 16-24 GB | AdamW, Batch 1, Rank 64 |
| **Tight** | 10-16 GB | **AdamW8bit**, Encoder Offloading, Rank 32-64 |
| **Minimal** | <10 GB | **AdaFactor** or **AdamW8bit**, Encoder Offloading, Rank 16, High Grad Accumulation |

### Additional VRAM Options (Advanced mode):
*   **`--offload-encoder`**: Moves the heavy VAE and Text Encoders to CPU after setup. Frees ~2-4 GB VRAM.
*   **`--no-gradient-checkpointing`**: Disable gradient checkpointing for max speed if you have VRAM to spare.
*   **`--optimizer-type prodigy`**: Uses the Prodigy optimizer to automatically find the best learning rate for you.

---

## Project Structure
```text
Side-Step/                       <-- Standalone project root
├── train.py                     <-- Your main entry point
├── pyproject.toml               <-- Dependencies (uv sync installs everything)
├── requirements-sidestep.txt    <-- Fallback for plain pip
├── install_windows.bat          <-- Windows easy installer (double-click)
├── install_windows.ps1          <-- PowerShell installer script
└── acestep/
    └── training_v2/             <-- Side-Step logic (all standalone)
        ├── trainer_fixed.py     <-- The corrected training loop
        ├── preprocess.py        <-- Two-pass preprocessing pipeline
        ├── estimate.py          <-- Gradient sensitivity estimation
        ├── model_loader.py      <-- Per-component model loading (supports fine-tunes)
        ├── model_discovery.py   <-- Checkpoint scanning & fuzzy search
        ├── settings.py          <-- Persistent user settings (~/.config/sidestep/)
        ├── _compat.py           <-- Version pin & compatibility check
        ├── optim.py             <-- 8-bit and adaptive optimizers
        ├── _vendor/             <-- Vendored ACE-Step utilities (standalone)
        ├── presets/             <-- Built-in preset JSON files
        ├── cli/                 <-- CLI argument parsing & dispatch
        └── ui/                  <-- Wizard, flows, setup, presets, visual logic
```

---
## Complete Argument Reference

Every argument, its default, and what it does.

### Global Flags

Available in: all subcommands (placed **before** the subcommand name)

| Argument | Default | Description |
|----------|---------|-------------|
| `--plain` | `False` | Disable Rich output; use plain text. Also set automatically when stdout is piped |
| `--yes` or `-y` | `False` | Skip the confirmation prompt and start training immediately |

### Model and Paths

Available in: vanilla, fixed

| Argument | Default | Description |
|----------|---------|-------------|
| `--checkpoint-dir` | **(required)** | Path to the root checkpoints directory (contains `acestep-v15-turbo/`, etc.) |
| `--model-variant` | `turbo` | Model variant or subfolder name. Official: `turbo`, `base`, `sft`. For fine-tunes: use the exact folder name (e.g., `my-custom-finetune`) |
| `--base-model` | *(auto)* | Base model a fine-tune was trained from: `turbo`, `base`, or `sft`. Auto-detected for official models. Only needed for custom fine-tunes whose `config.json` lacks timestep parameters |
| `--dataset-dir` | **(required)** | Directory containing your preprocessed `.pt` tensor files and `manifest.json` |

### Device and Precision

Available in: all subcommands

| Argument | Default | Description |
|----------|---------|-------------|
| `--device` | `auto` | Which device to train on. Options: `auto`, `cuda`, `cuda:0`, `cuda:1`, `mps`, `xpu`, `cpu`. Auto-detection priority: CUDA > MPS (Apple Silicon) > XPU (Intel) > CPU |
| `--precision` | `auto` | Floating point precision. Options: `auto`, `bf16`, `fp16`, `fp32`. Auto picks: bf16 on CUDA/XPU, fp16 on MPS, fp32 on CPU |

### Adapter Selection

Available in: vanilla, fixed

| Argument | Default | Description |
|----------|---------|-------------|
| `--adapter-type` | `lora` | Adapter type: `lora` (PEFT, stable) or `lokr` (LyCORIS, experimental). LoKR uses Kronecker product factorization |

### LoRA Settings (used when --adapter-type=lora)

Available in: vanilla, fixed

| Argument | Default | Description |
|----------|---------|-------------|
| `--rank` or `-r` | `64` | LoRA rank. Higher = more capacity and more VRAM. Recommended: 64 (ACE-Step dev recommendation) |
| `--alpha` | `128` | LoRA scaling factor. Controls how strongly the adapter affects the model. Usually 2x the rank. Recommended: 128 |
| `--dropout` | `0.1` | Dropout probability on LoRA layers. Helps prevent overfitting. Range: 0.0 to 0.5 |
| `--attention-type` | `both` | Which attention layers to target. Options: `both` (self + cross attention, 192 modules), `self` (self-attention only, audio patterns, 96 modules), `cross` (cross-attention only, text conditioning, 96 modules) |
| `--target-modules` | `q_proj k_proj v_proj o_proj` | Which projection layers get adapters. Space-separated list. Combined with `--attention-type` to determine final target modules |
| `--bias` | `none` | Whether to train bias parameters. Options: `none` (no bias training), `all` (train all biases), `lora_only` (only biases in LoRA layers) |

### LoKR Settings (used when --adapter-type=lokr) -- Experimental

Available in: vanilla, fixed.

| Argument | Default | Description |
|----------|---------|-------------|
| `--lokr-linear-dim` | `64` | LoKR linear dimension (analogous to LoRA rank) |
| `--lokr-linear-alpha` | `128` | LoKR linear alpha (scaling factor, analogous to LoRA alpha) |
| `--lokr-factor` | `-1` | Kronecker factorization factor. -1 = automatic |
| `--lokr-decompose-both` | `False` | Decompose both Kronecker factors for additional compression |
| `--lokr-use-tucker` | `False` | Use Tucker decomposition for more efficient factorization |
| `--lokr-use-scalar` | `False` | Use scalar scaling |
| `--lokr-weight-decompose` | `False` | Enable DoRA-style weight decomposition |

### Training Hyperparameters

Available in: vanilla, fixed

| Argument | Default | Description |
|----------|---------|-------------|
| `--lr` or `--learning-rate` | `0.0001` | Initial learning rate. For Prodigy optimizer, set to `1.0` |
| `--batch-size` | `1` | Number of samples per training step. Usually 1 for music generation (audio tensors are large) |
| `--gradient-accumulation` | `4` | Number of steps to accumulate gradients before updating weights. Effective batch size = batch-size x gradient-accumulation |
| `--epochs` | `100` | Maximum number of training epochs (full passes through the dataset) |
| `--warmup-steps` | `100` | Number of optimizer steps where the learning rate ramps up from 10% to 100% |
| `--weight-decay` | `0.01` | Weight decay (L2 regularization). Helps prevent overfitting |
| `--max-grad-norm` | `1.0` | Maximum gradient norm for gradient clipping. Prevents training instability from large gradients |
| `--seed` | `42` | Random seed for reproducibility. Same seed + same data = same results |
| `--shift` | `3.0` | Noise schedule shift for inference. Turbo=`3.0`, base/sft=`1.0`. Stored as metadata -- does not affect the training loop (see [Technical Notes](#technical-notes-shift-and-timestep-sampling)) |
| `--num-inference-steps` | `8` | Denoising steps for inference. Turbo=`8`, base/sft=`50`. Stored as metadata -- does not affect the training loop |
| `--optimizer-type` | `adamw` | Optimizer: `adamw`, `adamw8bit` (saves VRAM), `adafactor` (minimal state), `prodigy` (auto-tunes LR) |
| `--scheduler-type` | `cosine` | LR schedule: `cosine`, `cosine_restarts`, `linear`, `constant`, `constant_with_warmup`. Prodigy auto-forces `constant` |
| `--gradient-checkpointing` | `True` | Recompute activations during backward to save VRAM (~40-60% less activation memory, ~10-30% slower). On by default; use `--no-gradient-checkpointing` to disable |
| `--offload-encoder` | `False` | Move encoder/VAE to CPU after setup. Frees ~2-4GB VRAM with minimal speed impact |

### Corrected Training (fixed mode only)

Available in: fixed

| Argument | Default | Description |
|----------|---------|-------------|
| `--cfg-ratio` | `0.15` | Classifier-free guidance dropout rate. With this probability, each sample's condition is replaced with a null embedding during training. This teaches the model to work both with and without text prompts. The model was originally trained with 0.15 |

### Data Loading

Available in: vanilla, fixed

| Argument | Default | Description |
|----------|---------|-------------|
| `--num-workers` | `4` (Linux), `0` (Windows) | Number of parallel data loading worker processes. Auto-set to 0 on Windows |
| `--pin-memory` / `--no-pin-memory` | `True` | Pin loaded tensors in CPU memory for faster GPU transfer. Disable if you're low on RAM |
| `--prefetch-factor` | `2` | Number of batches each worker prefetches in advance |
| `--persistent-workers` / `--no-persistent-workers` | `True` | Keep data loading workers alive between epochs instead of respawning them |

### Checkpointing

Available in: vanilla, fixed

| Argument | Default | Description |
|----------|---------|-------------|
| `--output-dir` | **(required)** | Directory where LoRA weights, checkpoints, and TensorBoard logs are saved |
| `--save-every` | `10` | Save a full checkpoint (LoRA weights + optimizer + scheduler state) every N epochs |
| `--resume-from` | *(none)* | Path to a checkpoint directory to resume training from. Restores LoRA weights, optimizer state, and scheduler state |

### Logging and Monitoring

Available in: vanilla, fixed

| Argument | Default | Description |
|----------|---------|-------------|
| `--log-dir` | `{output-dir}/runs` | Directory for TensorBoard log files. View with `tensorboard --logdir <path>` |
| `--log-every` | `10` | Log loss and learning rate every N optimizer steps |
| `--log-heavy-every` | `50` | Log per-layer gradient norms every N optimizer steps. These are more expensive to compute but useful for debugging |
| `--sample-every-n-epochs` | `0` | Generate an audio sample every N epochs during training. 0 = disabled. (Not yet implemented) |

> **Log file:** All runs automatically append to `sidestep.log` in the working directory. This file captures full tracebacks and debug-level messages that may not appear in the terminal. Useful for diagnosing silent crashes or sharing logs when reporting issues.

### Preprocessing (optional)

Available in: vanilla, fixed

| Argument | Default | Description |
|----------|---------|-------------|
| `--preprocess` | `False` (flag) | If set, run audio preprocessing before training |
| `--audio-dir` | *(none)* | Source directory containing audio files (for preprocessing) |
| `--dataset-json` | *(none)* | Path to labeled dataset JSON file (for preprocessing) |
| `--tensor-output` | *(none)* | Output directory where preprocessed .pt tensor files will be saved |
| `--max-duration` | `240` | Maximum audio duration in seconds. Longer files are truncated |

---

## Technical Notes: Shift and Timestep Sampling

> **Important:** The `--shift` and `--num-inference-steps` settings are **inference metadata only**. They are saved alongside your adapter so you know which values to use when generating audio with the trained LoRA/LoKR. **They do not enter the training loop.**

### How Side-Step trains (corrected/fixed mode)

Side-Step's corrected training loop uses **continuous logit-normal timestep sampling** -- an exact reimplementation of the `sample_t_r()` function defined inside each ACE-Step model variant's own `forward()` method. The core operation is:

```python
t = sigmoid(N(timestep_mu, timestep_sigma))
```

The `timestep_mu` and `timestep_sigma` parameters are read automatically from each model's `config.json` at startup. All three model variants (turbo, base, sft) define the same `sample_t_r()` function and call it the same way during their native training forward pass. Our `sample_timesteps()` matches this line-for-line.

### How the upstream community trainer trains

The original ACE-Step community trainer (`acestep/training/trainer.py`) uses a **discrete 8-step schedule** hardcoded from `shift=3.0`:

```python
TURBO_SHIFT3_TIMESTEPS = [1.0, 0.955, 0.9, 0.833, 0.75, 0.643, 0.5, 0.3]
```

Each training step randomly picks one of these 8 values. This is **not** how the models were originally trained -- it only approximates the turbo model's inference schedule. For base and sft models, this schedule is wrong entirely.

### Where shift actually matters

`shift` controls the **inference** timestep schedule via `t_shifted = shift * t / (1 + (shift - 1) * t)`. This warp is applied inside `generate_audio()`, not during training. With `shift=1.0` you get a uniform linear schedule (more steps needed); with `shift=3.0` the schedule compresses toward the high end (fewer steps needed -- that's what makes turbo fast).

### Why this matters

- **Side-Step can train all variants** (turbo, base, sft) because it uses the same continuous sampling the models expect.
- **The upstream trainer only works properly for turbo** because its discrete schedule is derived from `shift=3.0`.
- **Changing `--shift` in Side-Step will not change your training results** -- the training timestep distribution is controlled by `timestep_mu` and `timestep_sigma` from the model config, which Side-Step reads automatically.
- **You still need the correct shift at inference time.** Use `shift=3.0` for turbo LoRAs and `shift=1.0` for base/sft LoRAs when generating audio.

---

## Contributing
Contributions are welcome! Specifically looking for help fixing the **Textual TUI** and testing the new preprocessing + estimation modules.

**License:** Follows the original ACE-Step 1.5 licensing
