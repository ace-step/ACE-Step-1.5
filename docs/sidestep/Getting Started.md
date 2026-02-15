## Prerequisites

- **Python 3.11+**
- **NVIDIA GPU with CUDA** (for training -- CPU/MPS are experimental)
- **Git** (to clone the repositories)
- **uv** (recommended) -- the fast Python package manager from Astral

### Installing uv

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

---

## Installation

### Option 1: Windows Easy Install

1. Clone Side-Step (or download as zip)
2. Double-click `install_windows.bat`
3. The script handles everything: uv, Python, ACE-Step, dependencies, model download

The installer creates two sibling folders:
```
your-folder/
  ACE-Step-1.5/     # Base repo (checkpoints, optional vanilla)
  Side-Step/         # Your training toolkit
```

### Option 2: Manual Install (Linux / macOS / Windows)

```bash
# 1. Clone Side-Step
git clone https://github.com/koda-dernet/Side-Step.git
cd Side-Step

# 2. Install dependencies (includes PyTorch with CUDA)
uv sync

# 3. Launch -- first run triggers the setup wizard
uv run python train.py
```

### Getting Model Checkpoints

You need the ACE-Step model weights before training. Two options:

**Option A: Use ACE-Step's downloader**
```bash
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync
uv run acestep-download
```
This downloads ~8 GB of weights into `ACE-Step-1.5/checkpoints/`.

**Option B: Manual download from HuggingFace**
Go to [HuggingFace ACE-Step](https://huggingface.co/ACE-Step/Ace-Step1.5) and download the model folders into a `checkpoints/` directory.

> **IMPORTANT:** Never rename checkpoint folders. See [[Model Management]] for details.

---

## First-Run Setup

When you run `python train.py` for the first time (without any arguments), the setup wizard activates:

1. **Welcome + disclaimers** -- Reminds you about model weights and the no-rename rule
2. **Vanilla intent** -- "Do you plan to use Vanilla training mode?"
   - If **yes**: provide the path to your ACE-Step installation
   - If **no**: corrected mode is fully standalone, no ACE-Step needed
3. **Checkpoint directory** -- Where your model weights live (e.g., `../ACE-Step-1.5/checkpoints`)
4. **Model scan** -- Lists all discovered models with official/custom labels

Settings are saved to:
- Linux/macOS: `~/.config/sidestep/settings.json`
- Windows: `%APPDATA%\sidestep\settings.json`

You can re-run setup at any time from the main menu: **Settings (paths, vanilla mode)**.

---

## Included Automatically

Everything is installed by `uv sync` -- no extras, no manual pip installs:

- **Flash Attention 2** -- Prebuilt wheels, no compilation. Auto-detected on Ampere+ GPUs (RTX 30xx+). Falls back to SDPA on older hardware or macOS. See [[VRAM Optimization Guide]].
- **Gradient checkpointing** -- Enabled by default. Cuts VRAM dramatically (~7 GiB for batch size 1, down from 20-42 GiB without it). See [[VRAM Optimization Guide]].
- **PyTorch with CUDA 12.8** -- Correct CUDA-enabled build per platform.
- **bitsandbytes** -- 8-bit optimizers (AdamW8bit) for ~30-40% optimizer VRAM savings.
- **Prodigy** -- Adaptive optimizer that auto-tunes learning rate.
- **LyCORIS** -- LoKR adapter support (experimental Kronecker product adapters).

---

## Next Steps

- [[Model Management]] -- Understand checkpoint structure and fine-tune support
- [[Training Guide]] -- Start training your first adapter
- [[VRAM Optimization Guide]] -- VRAM optimizations, GPU profiles, and all wizard settings explained
