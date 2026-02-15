# End-to-End Tutorial

This walkthrough takes you from raw audio files to generating music with a trained LoRA adapter. Every step includes the CLI command and links to detailed documentation.

**Prerequisites:** Side-Step installed and working, model checkpoints downloaded, GPU with CUDA support. See [[Getting Started]] if you have not set up yet.

---

## Step 1: Prepare Your Dataset

Collect your audio files into a single folder. Side-Step supports `.wav`, `.mp3`, `.flac`, `.ogg`, `.opus`, and `.m4a`.

```text
my_audio/
├── track1.wav
├── track2.wav
├── track3.mp3
└── track4.flac
```

**Optional but recommended:** Create a dataset JSON file with metadata for each track. This gives the model more information to learn from (captions, lyrics, genre, BPM, etc.):

```json
[
  {
    "audio_path": "./track1.wav",
    "caption": "Energetic rock with distorted guitars and driving drums",
    "genre": "Rock",
    "bpm": 140,
    "custom_tag": "mystyle"
  },
  {
    "audio_path": "./track2.wav",
    "caption": "Mellow acoustic folk song with fingerpicked guitar",
    "genre": "Folk",
    "bpm": 95
  }
]
```

Save this as `my_dataset.json` in the same directory as your audio files.

For full details on all available fields, see [[Dataset Preparation]].

---

## Step 2: Preprocess

Convert your raw audio into preprocessed `.pt` tensor files. This runs in two low-VRAM passes: (1) VAE + Text Encoder (~3 GB), then (2) DIT encoder (~6 GB).

**Without a dataset JSON (auto-captions from filenames):**

```bash
uv run train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --preprocess \
    --audio-dir ./my_audio \
    --tensor-output ./my_tensors
```

**With a dataset JSON:**

```bash
uv run train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --preprocess \
    --audio-dir ./my_audio \
    --dataset-json ./my_audio/my_dataset.json \
    --tensor-output ./my_tensors
```

After preprocessing, you will have a `my_tensors/` directory containing `.pt` files and a `manifest.json`. These tensors work for both LoRA and LoKR training -- you only need to preprocess once.

---

## Step 3: Train

Start training with the preprocessed tensors:

```bash
uv run train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --dataset-dir ./my_tensors \
    --output-dir ./output/my_lora \
    --epochs 100
```

This uses the `recommended` defaults (rank 64, cosine LR schedule, AdamW optimizer). To use a preset instead:

```bash
# Start the wizard and load a preset
uv run train.py
```

The wizard lets you load a preset (e.g., `vram_12gb` for a 12 GB GPU), adjust individual settings, and start training interactively. See [[Preset Management]] for the full list of built-in presets.

**Key flags to know:**

| Flag | Purpose |
| :--- | :--- |
| `--epochs 100` | How many times to loop through the dataset |
| `--rank 64` | LoRA capacity (higher = more expressive, more VRAM) |
| `--save-every 10` | Save a checkpoint every N epochs |
| `--offload-encoder` | Free ~2-4 GB VRAM by moving encoders to CPU |
| `--optimizer-type adamw8bit` | Use 8-bit optimizer to save VRAM |

For all available options, see the Complete Argument Reference in the README or [[The Settings Wizard]].

---

## Step 4: Monitor

While training runs (or after it finishes), view your training metrics with TensorBoard:

```bash
tensorboard --logdir ./output/my_lora/runs
```

Open `http://localhost:6006` in your browser. Watch for:

- **Loss** decreasing and stabilizing (good) vs. loss dropping then rising (overfitting).
- **Learning rate** following the expected schedule (warmup then decay).
- **Gradient norms** staying stable (spikes may indicate training issues).

---

## Step 5: Use Your LoRA

After training completes, your adapter is saved in `./output/my_lora/final/`.

### In ACE-Step Gradio

1. Start ACE-Step's Gradio UI.
2. In **Service Configuration**, find the **LoRA Adapter** section.
3. Enter the path to your adapter:
   ```
   /full/path/to/Side-Step/output/my_lora/final
   ```
4. Click **Load LoRA**.
5. Toggle **Use LoRA** on.
6. Adjust **LoRA Scale** (1.0 = full strength).
7. Generate audio. If you used a `custom_tag`, include it in your prompt.

**Important:** Use the correct shift and inference steps for your model variant. If you trained on turbo, use `shift=3.0` and 8 inference steps. For base/sft, use `shift=1.0` and 50 steps. See [[Shift and Timestep Sampling]] for details.

For the full guide on output layout, LoKR limitations, and checkpoint usage, see [[Using Your Adapter]].

---

## Step 6: Iterate

Training is iterative. Here are common next steps:

### Resume training for more epochs

```bash
uv run train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --dataset-dir ./my_tensors \
    --output-dir ./output/my_lora \
    --resume-from ./output/my_lora/checkpoints/epoch_100 \
    --epochs 200
```

### Try a different preset

Load a VRAM-appropriate preset to optimize for your GPU:

```bash
uv run train.py    # wizard mode, load a preset at the start
```

### Test intermediate checkpoints

Every checkpoint is inference-ready. Point ACE-Step at any checkpoint directory to hear how your LoRA sounds at different training stages:

```
./output/my_lora/checkpoints/epoch_50
./output/my_lora/checkpoints/epoch_100
```

### Adjust hyperparameters

- **Overfitting?** (loss drops then rises, output sounds like your training data verbatim) -- Lower rank, increase dropout, add more training data.
- **Underfitting?** (loss stays high, LoRA has no audible effect) -- Increase epochs, increase rank, check your dataset quality.
- **Running out of VRAM?** -- See [[VRAM Optimization Guide]] for tier-specific settings.

---

## Quick Reference

| Step | Command | Output |
| :--- | :--- | :--- |
| Preprocess | `uv run train.py fixed --preprocess --audio-dir ./my_audio --tensor-output ./my_tensors ...` | `./my_tensors/*.pt` |
| Train | `uv run train.py fixed --dataset-dir ./my_tensors --output-dir ./output/my_lora ...` | `./output/my_lora/final/` |
| Monitor | `tensorboard --logdir ./output/my_lora/runs` | Browser at localhost:6006 |
| Inference | Load `./output/my_lora/final` in ACE-Step Gradio | Generated audio |

---

## See Also

- [[Dataset Preparation]] -- JSON format, metadata fields, audio requirements
- [[Using Your Adapter]] -- Output layout, Gradio loading, LoKR limitations
- [[Training Guide]] -- Full training options and hyperparameters
- [[Preset Management]] -- Built-in presets, save/load/import/export
- [[VRAM Optimization Guide]] -- GPU memory profiles
- [[Windows Notes]] -- Windows-specific setup and workarounds
