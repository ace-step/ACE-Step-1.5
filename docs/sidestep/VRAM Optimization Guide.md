# VRAM Optimization Guide

This page documents every VRAM optimization Side-Step applies and the VRAM profiles for different GPU tiers.

---

## VRAM Optimizations

Side-Step applies several layers of VRAM optimization. Some are automatic; others are user-configurable. They are listed here from most impactful to least.

### Gradient Checkpointing (automatic, on by default)

**What it does:** During the backward pass, PyTorch normally stores all intermediate activations from the forward pass so it can compute gradients. Gradient checkpointing discards those activations and recomputes them on-the-fly during backpropagation.

**VRAM savings:** ~40-60% reduction in activation memory. For ACE-Step's decoder this is easily 10-15 GB on large batches.

**Trade-off:** ~10-30% slower training (recomputation cost).

**Default:** ON. This matches what the original ACE-Step trainer always did silently. Side-Step exposes it as a toggle so power users can disable it if they have VRAM to spare and want maximum speed.

**How to disable:** In the wizard (Advanced mode), answer "no" to "Enable gradient checkpointing?". Via CLI: `--no-gradient-checkpointing`.

> Side-Step also disables `use_cache` on the decoder (frees KV-cache memory) and enables `input_require_grads` (needed for PEFT + checkpointing compatibility). These happen automatically when gradient checkpointing is on.

### Flash Attention 2 (automatic, no user action needed)

**What it does:** Replaces the standard attention implementation with a fused CUDA kernel that is both faster and more memory-efficient. Instead of materializing the full N x N attention matrix, Flash Attention computes attention in tiles.

**VRAM savings:** Reduces attention memory from O(N^2) to O(N). In practice, this translates to lower peak VRAM during the forward pass, especially for long audio sequences.

**Speed benefit:** 10-30% faster training steps on supported hardware due to better GPU utilization (100% compute occupancy vs ~70-80% with SDPA).

**Requirements:** NVIDIA Ampere or newer GPU (RTX 30xx, RTX 40xx, A100, H100, etc. -- compute capability >= 8.0).

**How it works:** Side-Step installs Flash Attention 2 from prebuilt wheels (no compilation needed) as part of `uv sync`. At runtime, the model loader auto-detects whether Flash Attention is available and falls back to SDPA (Scaled Dot-Product Attention) if it is not. You do not need to configure anything.

**Fallback:** On older GPUs (RTX 20xx, GTX 16xx, etc.) or macOS, SDPA is used automatically.

### 8-bit Optimizer (optional, Advanced mode)

**What it does:** Replaces the standard 32-bit AdamW optimizer with an 8-bit quantized version. AdamW stores two state tensors (momentum and variance) per trainable parameter. Quantizing these to 8-bit halves their memory footprint.

**VRAM savings:** ~30% reduction in optimizer state memory. For a rank-64 LoRA with ~10M trainable parameters, this saves ~2-3 GB.

**Trade-off:** Negligible quality difference in practice. The quantization is applied to optimizer state, not to the model weights or gradients.

**How to enable:** In the wizard (Advanced > Optimizer & Scheduler), select "AdamW 8-bit". Via CLI: `--optimizer-type adamw8bit`. The `bitsandbytes` package is included automatically by `uv sync`.

### Encoder Offloading (optional, Advanced mode)

**What it does:** After the model is set up for training, moves non-decoder submodules (VAE, text encoder, condition encoders) from GPU to CPU. These components are only needed during preprocessing -- during the training loop itself, only the decoder runs on GPU.

**VRAM savings:** ~2-4 GB, depending on the model.

**Trade-off:** Minimal. These components are not used during the training loop, so offloading them has no speed impact.

**How to enable:** In the wizard (Advanced > VRAM Savings), answer "yes" to "Offload encoder/VAE to CPU?". Via CLI: `--offload-encoder`.

### Lower Rank

**What it does:** Reduces the number of trainable parameters in the LoRA/LoKR adapter. Fewer parameters means less memory for gradients, optimizer state, and activation storage.

**VRAM savings:** Roughly proportional. Rank 16 uses ~4x less adapter VRAM than rank 64.

**Trade-off:** Lower capacity. The adapter can capture less of your dataset's style. See the rank guide in [[Training Guide]].

### Gradient Accumulation

**What it does:** Instead of updating weights after every batch, accumulates gradients over N batches before applying a single optimizer step. This gives the same effective batch size as `batch_size x gradient_accumulation` without the VRAM cost of a larger batch.

**VRAM savings:** Keeps per-step VRAM at `batch_size=1` levels while achieving the training dynamics of a larger effective batch.

**Default:** 4 steps of accumulation with batch size 1 (effective batch size = 4).

---

## VRAM Profiles

| Profile | GPU VRAM | Automatic | Recommended Settings |
|---|---|---|---|
| **Comfortable** | 24 GB+ | Grad checkpointing ON, Flash Attention | Batch 2+, AdamW, Rank 64-128 |
| **Standard** | 16-24 GB | Grad checkpointing ON, Flash Attention | Batch 1, AdamW, Rank 64, Grad accumulation 4 |
| **Tight** | 10-16 GB | Grad checkpointing ON, Flash Attention | Batch 1, **AdamW8bit**, Encoder offloading, Rank 32-64 |
| **Minimal** | <10 GB | Grad checkpointing ON, Flash Attention | Batch 1, **AdamW8bit** or **Adafactor**, Encoder offloading, Rank 16, High grad accumulation |

> Gradient checkpointing and Flash Attention are always active (when supported). The profiles differ in optimizer choice, rank, and optional offloading.
> 
---

## See Also

- [[Training Guide]] -- Full training workflow, hyperparameter guide, LoRA vs LoKR
- [[Estimation Guide]] -- Gradient sensitivity analysis for targeted training
- [[Getting Started]] -- Installation and first-run setup
- [[Model Management]] -- Checkpoint structure and fine-tune support
