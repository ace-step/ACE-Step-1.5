
## Checkpoint Directory Structure

ACE-Step models are organized as subdirectories under a root `checkpoints/` folder. Each model variant has its own folder with a `config.json` and weight files:

```text
checkpoints/
  acestep-v15-turbo/     # Turbo (8-step accelerated)
    config.json
    modeling.py
    model.safetensors
    silence_latent.pt
  acestep-v15-base/      # Base (full diffusion)
    config.json
    ...
  acestep-v15-sft/       # SFT (supervised fine-tune)
    config.json
    ...
  vae/                   # VAE encoder/decoder (shared)
  Qwen3-Embedding-0.6B/  # Text encoder (shared)
```

### The Golden Rule: Never Rename Checkpoint Folders

The model loader uses `AutoModel.from_pretrained()` with `trust_remote_code=True`. This means:
- The `config.json` tells HuggingFace Transformers which Python class to load
- The `modeling.py` file in each folder defines the actual model architecture
- Renaming folders breaks the loading mechanism

If you downloaded weights manually, make sure the folder names match what the model expects.

---

## Official vs Custom Models

Side-Step's model discovery automatically classifies models:

- **Official models**: Folder names starting with `acestep-v15-` (e.g., `acestep-v15-turbo`). These are auto-detected with correct timestep parameters.
- **Custom models / fine-tunes**: Any other folder containing a `config.json`. Side-Step will ask which base model they descend from.

### How Discovery Works

When you start training or preprocessing, the wizard:
1. Scans your checkpoint directory for subfolders with `config.json`
2. Filters out non-model directories (VAE, text encoder, etc.)
3. Labels each as official or custom
4. Presents a numbered list for selection
5. Offers fuzzy search if you have many models

You can also type a name (or part of one) to filter the list.

---

## Training on Fine-Tunes

Side-Step supports training on community fine-tunes, not just the official turbo/base/sft.

### Requirements

1. **You MUST have the original base model** that the fine-tune was built from. The training loop needs it for correct timestep conditioning.
2. **The fine-tune folder** must contain a valid `config.json` (same format as official models).
3. **Do not rename** the fine-tune folder.

### Wizard Flow

1. The model picker lists your fine-tune alongside official models
2. If the fine-tune's `config.json` doesn't specify `is_turbo` or timestep parameters, Side-Step asks: "Which base model was this fine-tune trained from?"
3. Your answer conditions the training: turbo uses discrete scheduling, base/sft use continuous
4. Training proceeds normally

### CLI Flow

```bash
uv run python train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant my-custom-finetune \
    --base-model turbo \
    --dataset-dir ./my_tensors \
    --output-dir ./output/my_lora
```

The `--model-variant` accepts any folder name under `--checkpoint-dir`.
The `--base-model` tells Side-Step which timestep parameters to use.

---

## Base Model Differences

Understanding which base model you're working with matters for training quality:

| Base | `is_turbo` | Timestep Sampling | CFG | Best For |
|------|-----------|-------------------|-----|----------|
| **Turbo** | Yes | Discrete (8-step) | Not trained with CFG | Fast generation, the original training script was built for this |
| **Base** | No | Continuous (logit-normal) | Trained with CFG dropout | Full quality, benefits most from corrected training |
| **SFT** | No | Continuous (logit-normal) | Trained with CFG dropout | Instruction-following generation |

Side-Step's corrected (fixed) training mode uses continuous timestep sampling and CFG dropout -- matching how base and SFT models were actually trained. For turbo, the original discrete schedule is appropriate.

---

## Shared Components

Some checkpoint directories are shared across all model variants:

- **`vae/`** -- The audio VAE (AutoencoderOobleck). Encodes raw audio into latent space and decodes back.
- **`Qwen3-Embedding-0.6B/`** -- The text encoder. Converts text prompts into embeddings for conditioning.
- **`silence_latent.pt`** -- Pre-computed silence latent used for LoRA preprocessing context.

These are loaded separately during preprocessing and training. They don't need to be inside each model variant's folder.

---

## See Also

- [[Getting Started]] -- Installation and first-run setup
- [[Training Guide]] -- Start training adapters
