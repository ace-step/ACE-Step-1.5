# Large-Scale SFT Training Guide with Muse Dataset

This guide covers two training scenarios using the [Muse dataset](https://huggingface.co/datasets/bolshyC/Muse) (116K licensed synthetic songs):

1. **Large-Scale LoRA Fine-Tuning** — Adapter-only training on the full Muse corpus
2. **Full-Parameter SFT** — Training all decoder parameters (requires code modifications)

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Part 1: Dataset Preparation](#part-1-dataset-preparation)
- [Part 2: Large-Scale LoRA Training](#part-2-large-scale-lora-training)
- [Part 3: Full-Parameter SFT](#part-3-full-parameter-sft)
- [Part 4: Multi-GPU Training](#part-4-multi-gpu-training)
- [Appendix: Architecture Reference](#appendix-architecture-reference)

---

## Prerequisites

### Hardware Requirements

| Scenario | Minimum | Recommended |
|----------|---------|-------------|
| LoRA (rank 128, multi-GPU) | 4x 24 GB (e.g. 4x RTX 4090) | 8x 80 GB (e.g. 8x H100/A100) |
| Full SFT | 8x 40 GB (e.g. 8x A100-40G) | 8x 80 GB (e.g. 8x H100) |
| Preprocessing only | 1x 12 GB | 1x 24 GB |

### Software Requirements

```bash
# Clone ACE-Step 1.5
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5

# Install dependencies
pip install -r requirements.txt

# Ensure Hugging Face CLI is installed
pip install huggingface_hub[cli]
```

### Storage Requirements

| Component | Size |
|-----------|------|
| Muse audio (116K songs, MP3) | ~500 GB |
| Preprocessed .pt tensors | ~800 GB - 1.2 TB |
| Training checkpoints | ~50 GB (LoRA) / ~200 GB (Full SFT) |
| **Total** | **~1.5 - 2 TB** |

---

## Part 1: Dataset Preparation

### 1.1 Download the Muse Dataset

```bash
# Create working directories
mkdir -p muse_dataset/{audio,metadata}
cd muse_dataset

# Download metadata files
huggingface-cli download bolshyC/Muse \
    train_cn.jsonl train_en.jsonl \
    validation_cn.jsonl validation_en.jsonl \
    --local-dir ./metadata --repo-type dataset

# Download Chinese audio archives (25 parts)
for i in $(seq -w 1 25); do
    huggingface-cli download bolshyC/Muse \
        "cn_part${i}_of_025.tar" \
        --local-dir ./audio --repo-type dataset
done

# Download English audio archives (35 parts)
for i in $(seq -w 1 35); do
    huggingface-cli download bolshyC/Muse \
        "en_part${i}_of_035.tar" \
        --local-dir ./audio --repo-type dataset
done
```

### 1.2 Extract Audio Files

```bash
# IMPORTANT: maintain the directory structure that metadata expects
mkdir -p suno_cn_songs suno_en_songs

# Extract Chinese audio
for f in audio/cn_part*.tar; do
    tar -xf "$f" -C suno_cn_songs/
done

# Extract English audio
for f in audio/en_part*.tar; do
    tar -xf "$f" -C suno_en_songs/
done
```

### 1.3 Convert Muse JSONL to ACE-Step Dataset Format

ACE-Step expects a specific directory layout. Create a conversion script:

```python
#!/usr/bin/env python3
"""convert_muse_to_acestep.py -- Convert Muse JSONL to ACE-Step dataset format."""

import json
import os
import shutil
from pathlib import Path
from typing import Optional


def convert_muse_jsonl(
    jsonl_path: str,
    audio_root: str,
    output_dir: str,
    max_samples: Optional[int] = None,
):
    """Convert a Muse JSONL file into ACE-Step's per-song directory layout.

    ACE-Step expects:
        output_dir/
        ├── song_0001.mp3
        ├── song_0001.lyrics.txt
        ├── song_0001.json
        ├── song_0002.mp3
        ...

    Args:
        jsonl_path: Path to train_cn.jsonl or train_en.jsonl
        audio_root: Root directory containing the extracted audio files
        output_dir: Where to write the ACE-Step compatible dataset
        max_samples: Limit number of samples (None = all)
    """
    os.makedirs(output_dir, exist_ok=True)
    count = 0

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if max_samples and count >= max_samples:
                break

            record = json.loads(line.strip())
            song_id = record["song_id"]
            audio_path = os.path.join(audio_root, record["audio_path"])

            # Skip if audio file doesn't exist
            if not os.path.exists(audio_path):
                print(f"[SKIP] Audio not found: {audio_path}")
                continue

            # Build caption from style field
            style = record.get("style", "")
            caption = style  # e.g. "Pop, Rock, Electronic, Male Vocal, Energetic"

            # Extract lyrics from sections
            lyrics_parts = []
            for section in record.get("sections", []):
                section_type = section.get("section", "")
                text = section.get("text", "").strip()
                if text:
                    lyrics_parts.append(f"[{section_type}]")
                    lyrics_parts.append(text)
                elif section_type == "Intro":
                    lyrics_parts.append("[Intro]")
                elif section_type == "Outro":
                    lyrics_parts.append("[Outro]")
                elif section_type in ("Interlude", "Break"):
                    lyrics_parts.append(f"[{section_type}]")

            lyrics = "\n".join(lyrics_parts)
            if not lyrics.strip():
                lyrics = "[Instrumental]"

            # Detect if instrumental (no lyrics text in any section)
            is_instrumental = all(
                not s.get("text", "").strip()
                for s in record.get("sections", [])
            )

            # Determine BPM from style (not directly in Muse metadata,
            # so we leave it for auto-detection or set a reasonable default)
            # You can use a BPM detection library like librosa if needed.

            # Copy audio file
            ext = Path(audio_path).suffix
            base_name = f"{song_id}_{record.get('track_index', 0)}"
            dest_audio = os.path.join(output_dir, f"{base_name}{ext}")
            if not os.path.exists(dest_audio):
                shutil.copy2(audio_path, dest_audio)

            # Write lyrics file
            lyrics_file = os.path.join(output_dir, f"{base_name}.lyrics.txt")
            with open(lyrics_file, "w", encoding="utf-8") as lf:
                lf.write(lyrics)

            # Write metadata JSON
            meta = {
                "caption": caption,
                "is_instrumental": is_instrumental,
            }

            # Add section-level descriptions as custom_tag for extra context
            descs = [
                s.get("desc", "")
                for s in record.get("sections", [])
                if s.get("desc", "").strip()
            ]
            if descs:
                # Use the first section description as additional context
                meta["custom_tag"] = descs[0][:200]

            meta_file = os.path.join(output_dir, f"{base_name}.json")
            with open(meta_file, "w", encoding="utf-8") as mf:
                json.dump(meta, mf, ensure_ascii=False, indent=2)

            count += 1
            if count % 1000 == 0:
                print(f"[INFO] Converted {count} samples...")

    print(f"[DONE] Converted {count} samples to {output_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", required=True, help="Path to Muse JSONL file")
    parser.add_argument("--audio-root", required=True, help="Root dir with extracted audio")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args()

    convert_muse_jsonl(args.jsonl, args.audio_root, args.output, args.max_samples)
```

Run the conversion:

```bash
# Convert Chinese training data
python convert_muse_to_acestep.py \
    --jsonl metadata/train_cn.jsonl \
    --audio-root . \
    --output acestep_dataset_cn

# Convert English training data
python convert_muse_to_acestep.py \
    --jsonl metadata/train_en.jsonl \
    --audio-root . \
    --output acestep_dataset_en

# Merge into a single dataset directory (optional)
mkdir -p acestep_dataset_all
cp -r acestep_dataset_cn/* acestep_dataset_all/
cp -r acestep_dataset_en/* acestep_dataset_all/
```

### 1.4 Preprocess Audio to .pt Tensors

ACE-Step's preprocessing converts raw audio into pre-computed VAE latents and text embeddings. This is a two-pass process:

- **Pass 1 (~3 GB VRAM)**: VAE encoding + text tokenization → `.tmp.pt`
- **Pass 2 (~6 GB VRAM)**: DIT encoder → final `.pt`

```bash
# Preprocess using the SideStep CLI
# Process in batches to manage disk I/O
python -m acestep.training_v2.cli.train_fixed \
    --preprocess \
    --audio-dir ./acestep_dataset_all \
    --tensor-output ./preprocessed_tensors \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --max-duration 240 \
    --device cuda:0

# For very large datasets, you can split and run in parallel:
# GPU 0: Chinese subset
python -m acestep.training_v2.cli.train_fixed \
    --preprocess \
    --audio-dir ./acestep_dataset_cn \
    --tensor-output ./preprocessed_tensors_cn \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --device cuda:0 &

# GPU 1: English subset
python -m acestep.training_v2.cli.train_fixed \
    --preprocess \
    --audio-dir ./acestep_dataset_en \
    --tensor-output ./preprocessed_tensors_en \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --device cuda:1 &

wait
# Then merge the .pt files
mkdir -p preprocessed_tensors_all
cp preprocessed_tensors_cn/*.pt preprocessed_tensors_all/
cp preprocessed_tensors_en/*.pt preprocessed_tensors_all/
```

> **Preprocessing Time Estimate**: ~2-5 minutes per song on a single GPU. For 116K songs, expect 4-10 days on 1 GPU, or ~12-24 hours on 8 GPUs in parallel.

---

## Part 2: Large-Scale LoRA Training

### 2.1 Single-GPU Quick Test

Start with a small subset to verify everything works:

```bash
python -m acestep.training_v2.cli.train_fixed \
    --dataset-dir ./preprocessed_tensors_all \
    --output-dir ./output/lora_test \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --adapter-type lora \
    --r 64 \
    --alpha 128 \
    --batch-size 4 \
    --gradient-accumulation-steps 4 \
    --max-epochs 5 \
    --learning-rate 1e-4 \
    --warmup-steps 100 \
    --device cuda:0 \
    --yes
```

### 2.2 Multi-GPU LoRA Training (Recommended)

For 116K songs, multi-GPU training is essential. With PR #941 merged:

```bash
# 8x GPU DDP training
python -m acestep.training_v2.cli.train_fixed \
    --dataset-dir ./preprocessed_tensors_all \
    --output-dir ./output/lora_muse_full \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --adapter-type lora \
    --r 128 \
    --alpha 256 \
    --dropout 0.05 \
    --batch-size 16 \
    --gradient-accumulation-steps 2 \
    --max-epochs 50 \
    --learning-rate 5e-5 \
    --warmup-steps 500 \
    --weight-decay 0.01 \
    --optimizer-type adamw \
    --scheduler-type cosine \
    --gradient-checkpointing \
    --num-devices 8 \
    --strategy ddp \
    --save-every-n-epochs 5 \
    --log-every 10 \
    --yes
```

### 2.3 Recommended Hyperparameters for Large-Scale LoRA

| Parameter | Small Dataset (<1K) | Medium (1K-10K) | Large (10K-116K) |
|-----------|---------------------|------------------|-------------------|
| LoRA rank (`--r`) | 8-32 | 64 | 128 |
| LoRA alpha (`--alpha`) | 2x rank | 2x rank | 2x rank |
| Dropout | 0.1 | 0.05 | 0.05 |
| Batch size (per GPU) | 1-4 | 8-16 | 16-32 |
| Gradient accumulation | 4-8 | 2-4 | 1-2 |
| Effective batch size | 8-16 | 32-64 | 128-256 |
| Learning rate | 1e-4 | 5e-5 | 2e-5 ~ 5e-5 |
| Warmup steps | 50-100 | 200-500 | 500-1000 |
| Max epochs | 100-500 | 30-100 | 10-50 |
| Optimizer | adamw | adamw | adamw / adamw8bit |

### 2.4 SLURM Job Script Example

For HPC clusters:

```bash
#!/bin/bash
#SBATCH --job-name=acestep-lora-muse
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gpus-per-node=8
#SBATCH --cpus-per-task=64
#SBATCH --mem=512G
#SBATCH --time=72:00:00
#SBATCH --partition=gpu
#SBATCH --output=logs/%j.out

module load cuda/12.1

cd $SLURM_SUBMIT_DIR

python -m acestep.training_v2.cli.train_fixed \
    --dataset-dir /data/preprocessed_tensors_all \
    --output-dir /data/output/lora_muse_$SLURM_JOBID \
    --checkpoint-dir /data/checkpoints \
    --model-variant turbo \
    --adapter-type lora \
    --r 128 \
    --alpha 256 \
    --batch-size 16 \
    --gradient-accumulation-steps 2 \
    --max-epochs 50 \
    --learning-rate 5e-5 \
    --warmup-steps 500 \
    --num-devices 8 \
    --strategy ddp \
    --save-every-n-epochs 5 \
    --yes
```

### 2.5 Monitor Training

```bash
# TensorBoard
tensorboard --logdir ./output/lora_muse_full/runs --port 6006

# Key metrics to watch:
# - train/loss: should decrease steadily, target ~0.45-0.50
# - train/lr: should follow cosine schedule
# - Gradient norms: should be stable, no spikes
```

---

## Part 3: Full-Parameter SFT

> **Warning**: Full-parameter SFT is NOT natively supported by ACE-Step 1.5. This section describes the code modifications required.

### 3.1 Why Full-Parameter SFT?

| Aspect | LoRA | Full SFT |
|--------|------|----------|
| Trainable params | ~50M (rank 128) | ~3.5B (full decoder) |
| VRAM per GPU | 20-30 GB | 60-80 GB |
| Quality ceiling | Good for style transfer | Maximum quality |
| Risk of catastrophic forgetting | Low | High |
| Training time | Hours-days | Days-weeks |

Full SFT makes sense when:
- You have a very large, diverse dataset (like Muse's 116K songs)
- You want to fundamentally change the model's capabilities
- You're creating a new base model for downstream LoRA fine-tuning

### 3.2 Code Modifications Required

#### Step 1: Modify `model_loader.py` — Add full SFT mode

```python
# In acestep/training_v2/model_loader.py
# After the existing load_decoder_for_training() function, add:

def load_decoder_for_full_sft(
    checkpoint_dir: str | Path,
    variant: str = "turbo",
    device: str = "cuda",
    precision: str = "bf16",
) -> Any:
    """Load the decoder with ALL parameters unfrozen for full SFT.

    Unlike load_decoder_for_training() which freezes everything,
    this keeps all decoder parameters trainable.
    """
    model_dir, dtype = _resolve_model_dir(checkpoint_dir, variant, precision)

    model = AutoModel.from_pretrained(
        str(model_dir),
        trust_remote_code=True,
        attn_implementation="sdpa",
        dtype=dtype,
    )

    # Do NOT freeze parameters — keep everything trainable
    # Only freeze non-decoder components (encoder, VAE) if desired
    for name, param in model.named_parameters():
        if "decoder" in name:
            param.requires_grad = True
        else:
            param.requires_grad = False

    model = model.to(device=device, dtype=dtype)
    model.train()

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"[OK] Full SFT mode: {trainable:,} / {total:,} params trainable")

    return model
```

#### Step 2: Add `--full-sft` CLI flag

```python
# In acestep/training_v2/cli/args.py
# In _add_common_training_args(), add:

g.add_argument(
    "--full-sft",
    action="store_true",
    default=False,
    help="Train all decoder parameters instead of just LoRA/LoKR adapters",
)
```

#### Step 3: Modify `configs.py`

```python
# In acestep/training_v2/configs.py, in TrainingConfigV2:

full_sft: bool = False
"""Train all decoder parameters (no adapter injection)."""
```

#### Step 4: Modify `trainer_fixed.py` — Skip LoRA injection in full SFT mode

The key change is in the `train()` method. When `full_sft=True`:
- Skip `inject_lora_into_dit()` / `inject_lokr_into_dit()`
- Keep all decoder parameters trainable
- Save full model checkpoints instead of adapter-only checkpoints

```python
# In FixedLoRATrainer.train(), after model loading:

if cfg.full_sft:
    # Full SFT: unfreeze all decoder parameters
    for param in self.module.model.decoder.parameters():
        param.requires_grad = True
    self.module.model.decoder.train()
else:
    # Adapter mode: inject LoRA/LoKR as before
    inject_lora_into_dit(self.module.model.decoder, adapter_cfg)
```

And modify `_save_final()` / `_save_checkpoint()`:

```python
def _save_final(self, path: str):
    if self.training_config.full_sft:
        # Save full decoder state dict
        os.makedirs(path, exist_ok=True)
        torch.save(
            self.module.model.decoder.state_dict(),
            os.path.join(path, "decoder_state_dict.pt"),
        )
        # Also save in HuggingFace format for easy loading
        self.module.model.save_pretrained(path)
    else:
        # Existing adapter save logic
        save_lora_weights(...)
```

#### Step 5: Use DeepSpeed ZeRO for memory efficiency (recommended)

For full SFT with 3.5B decoder parameters, single-GPU training is impractical.
Replace Lightning Fabric with DeepSpeed ZeRO-2 or ZeRO-3:

```python
# In trainer_fixed.py, modify _train_fabric():

if cfg.full_sft and num_devices > 1:
    # Use DeepSpeed ZeRO-2 for full SFT
    from lightning.fabric.strategies import DeepSpeedStrategy

    ds_config = {
        "zero_optimization": {
            "stage": 2,
            "offload_optimizer": {
                "device": "cpu",
                "pin_memory": True,
            },
            "allgather_partitions": True,
            "allgather_bucket_size": 2e8,
            "reduce_scatter": True,
            "reduce_bucket_size": 2e8,
            "overlap_comm": True,
        },
        "bf16": {"enabled": True},
        "gradient_clipping": cfg.max_grad_norm,
    }

    self.fabric = Fabric(
        accelerator="cuda",
        devices=num_devices,
        strategy=DeepSpeedStrategy(config=ds_config),
        precision="bf16-true",
    )
```

### 3.3 Full SFT Training Command

After applying the code modifications:

```bash
# 8x H100 full SFT
python -m acestep.training_v2.cli.train_fixed \
    --dataset-dir ./preprocessed_tensors_all \
    --output-dir ./output/full_sft_muse \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --full-sft \
    --batch-size 8 \
    --gradient-accumulation-steps 4 \
    --max-epochs 20 \
    --learning-rate 1e-5 \
    --warmup-steps 2000 \
    --weight-decay 0.01 \
    --optimizer-type adamw \
    --scheduler-type cosine \
    --gradient-checkpointing \
    --num-devices 8 \
    --strategy ddp \
    --save-every-n-epochs 2 \
    --yes
```

### 3.4 Recommended Hyperparameters for Full SFT

| Parameter | Conservative | Balanced | Aggressive |
|-----------|-------------|----------|------------|
| Learning rate | 5e-6 | 1e-5 | 2e-5 |
| Warmup steps | 3000 | 2000 | 1000 |
| Weight decay | 0.01 | 0.01 | 0.05 |
| Batch size (per GPU) | 4 | 8 | 16 |
| Gradient accumulation | 8 | 4 | 2 |
| Effective batch size | 256 | 256 | 256 |
| Max epochs | 10-20 | 20-30 | 30-50 |
| Max grad norm | 1.0 | 1.0 | 0.5 |

> **Important**: Use a lower learning rate for full SFT (1e-5) compared to LoRA (5e-5) to avoid catastrophic forgetting. The warmup should be longer.

---

## Part 4: Multi-GPU Training

### 4.1 DDP (Data Distributed Parallel)

DDP replicates the model on each GPU and splits the dataset. Each GPU processes different batches, and gradients are synchronized via all-reduce.

```bash
# Simple DDP (single node, multiple GPUs)
python -m acestep.training_v2.cli.train_fixed \
    --num-devices 8 \
    --strategy ddp \
    ... # other args
```

### 4.2 FSDP / DeepSpeed ZeRO (for Full SFT)

When the model doesn't fit on a single GPU, use model parallelism:

```bash
# DeepSpeed ZeRO-2 (optimizer states sharded across GPUs)
# Requires the code modifications from Part 3

# DeepSpeed ZeRO-3 (model parameters + optimizer states sharded)
# Maximum memory savings, but slower communication
```

### 4.3 Multi-Node Training

For training across multiple machines:

```bash
# Node 0 (master)
export MASTER_ADDR=node0-ip
export MASTER_PORT=29500
export WORLD_SIZE=16
export NODE_RANK=0
python -m acestep.training_v2.cli.train_fixed \
    --num-devices 8 \
    --strategy ddp \
    ... # other args

# Node 1
export MASTER_ADDR=node0-ip
export MASTER_PORT=29500
export WORLD_SIZE=16
export NODE_RANK=1
python -m acestep.training_v2.cli.train_fixed \
    --num-devices 8 \
    --strategy ddp \
    ... # other args
```

---

## Appendix: Architecture Reference

### ACE-Step Training Pipeline

```
Raw Audio (MP3/WAV)
    │
    ▼
[Preprocessing - Pass 1: ~3 GB VRAM]
    ├─ Audio → 48kHz stereo → VAE encoder → target_latents [T, 64]
    ├─ Caption → Text tokenizer + encoder → text_hidden_states [L, 768]
    └─ Lyrics → Lyric tokenizer + encoder → lyric_hidden_states [L, 768]
    │
    ▼
[Preprocessing - Pass 2: ~6 GB VRAM]
    ├─ text_hs + lyric_hs → DIT encoder → encoder_hidden_states [L, 768]
    └─ silence_latent + chunk_mask → context_latents [T, 65]
    │
    ▼
[.pt Tensor File]
    ├─ target_latents: [T, 64]         # ground truth audio latents
    ├─ attention_mask: [T]              # valid audio positions
    ├─ encoder_hidden_states: [L, 768]  # packed text + lyrics embeddings
    ├─ encoder_attention_mask: [L]      # valid condition positions
    ├─ context_latents: [T, 65]         # context audio + chunk mask
    └─ metadata: {...}                  # song info
    │
    ▼
[Training Loop - Flow Matching]
    1. Sample noise x1 ~ N(0, 1) with shape [B, T, 64]
    2. Sample timestep t ~ logit-normal(μ=-0.4, σ=1.0)
    3. Interpolate: xt = t * x1 + (1-t) * x0    (x0 = target_latents)
    4. CFG dropout: replace 15% of conditions with null embedding
    5. Decoder forward: predict_flow = decoder(xt, t, conditions)
    6. Loss = MSE(predict_flow, x1 - x0)         (flow matching loss)
    7. Backprop through LoRA params (or all params in full SFT)
```

### Key Model Dimensions

| Component | Dimension |
|-----------|-----------|
| VAE latent | 64 |
| Context latent (with mask) | 65 |
| Decoder input (concat) | 129 |
| Hidden size | 768 (after patch projection) |
| Decoder layers | 32 |
| Attention heads | 32 |
| Patch size | 4 (reduces sequence length by 4x) |
| Audio sample rate | 48,000 Hz |
| Latent frame rate | ~160 Hz (before patching) |

### Muse Dataset → ACE-Step Mapping

| Muse Field | ACE-Step Usage |
|------------|---------------|
| `style` | `caption` (text conditioning) |
| `sections[].text` | Lyrics file (`.lyrics.txt`) |
| `sections[].section` | Structural tags (`[Verse]`, `[Chorus]`, etc.) |
| `sections[].desc` | `custom_tag` in metadata JSON |
| `audio_path` | Source audio for VAE encoding |
| `style_sim` | Can be used to filter low-quality samples |

### Tips for Best Results

1. **Filter by `style_sim`**: The Muse dataset includes a `style_sim` score. Consider filtering out samples with `style_sim < 0.4` for higher-quality training data.

2. **Balance CN/EN**: If you want bilingual capability, ensure roughly equal representation of Chinese and English samples.

3. **Progressive training**: Start with a smaller subset (e.g., 10K songs) to validate the pipeline, then scale up.

4. **Monitor for mode collapse**: If loss plateaus too early or generated samples lack diversity, reduce learning rate or increase dropout.

5. **Checkpoint frequently**: Save checkpoints every 2-5 epochs. Large-scale training can fail due to hardware issues.

6. **Validate periodically**: Use the validation split (`validation_cn.jsonl`, `validation_en.jsonl`) to monitor generalization. Generate sample audio every N epochs to subjectively evaluate quality.
