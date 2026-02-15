
## Wizard Settings Reference

The wizard has two modes: **Basic** (fewer questions, good defaults) and **Advanced** (all settings exposed). Basic mode settings are shown to everyone. Advanced settings appear only when you select "Advanced" at the start.

### Basic Mode Settings

These are always shown regardless of mode.

#### Required Settings

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Checkpoint directory | From settings or `./checkpoints` | Where model weights live | Point to your ACE-Step checkout or custom weights |
| Model | Interactive picker | Which model variant to train on | Pick base, turbo, sft, or a community fine-tune |
| Dataset directory | *(none)* | Folder with preprocessed `.pt` files | Always required -- your training data |
| Output directory | *(none)* | Where adapter weights and logs are saved | Always required -- pick a descriptive name |

#### LoRA Settings

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Rank | `64` | Number of low-rank dimensions. Higher = more capacity, more VRAM | Lower for quick tests (16), higher for max quality (128). See [[Training Guide]] |
| Alpha | `128` | Scaling factor (usually 2x rank). Controls adapter strength | Keep at 2x rank unless experimenting |
| Dropout | `0.1` | Dropout on LoRA layers. Prevents overfitting | Increase (0.2-0.3) for very small datasets, decrease (0.05) for large ones |
| Attention type | `both` | Which attention layers get adapters: self, cross, or both | `self` = audio patterns only, `cross` = text conditioning only. See [[Estimation Guide]] to decide |
| Target projections | `q_proj k_proj v_proj o_proj` | Which projections inside each attention block | Use [[Estimation Guide]] results to narrow this down |

#### LoKR Settings (when training LoKR)

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Linear dimension | `64` | Analogous to LoRA rank | Same guidance as LoRA rank |
| Linear alpha | `128` | Scaling factor | Keep at 2x linear dim |
| Factor | `-1` | Kronecker factorization factor (-1 = auto) | Leave at auto unless you understand Kronecker factorization |
| Decompose both | `no` | Decompose both Kronecker factors | May improve compression at the cost of capacity |
| Tucker decomposition | `no` | Use Tucker decomposition | Alternative factorization -- experimental |
| Scalar scaling | `no` | Use scalar scaling | Experimental |
| DoRA weight decompose | `no` | DoRA-style weight decomposition | Can improve quality in some cases |
| Attention type | `both` | Same as LoRA | Same guidance |
| Target projections | `q_proj k_proj v_proj o_proj` | Same as LoRA | Same guidance |

#### Training Settings

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Learning rate | `1e-4` | How fast the optimizer moves. **For Prodigy, set to 1.0** | Lower (5e-5) for stability, higher (2e-4) for faster convergence |
| Batch size | `1` | Samples per step | Increase only if you have VRAM to spare |
| Gradient accumulation | `4` | Steps before weight update. Effective batch = batch_size x this | Higher for smoother gradients, lower for faster updates |
| Max epochs | `100` | Full passes through the dataset | More for small datasets (200-500), fewer for large (50-100) |
| Warmup steps | `100` | LR ramps from 10% to 100% over this many steps | Longer warmup (200+) for stability with large LR |
| Seed | `42` | Random seed for reproducibility | Change to get different training runs |

#### CFG Settings (corrected mode only)

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| CFG dropout ratio | `0.15` | Probability of replacing conditions with null embeddings | The base model was trained with 0.15 -- match it. Lower values reduce CFG effectiveness |

#### Logging & Checkpoints

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Save every N epochs | `10` | Full checkpoint (adapter + optimizer + scheduler) | Lower for safety on long runs, higher to save disk space |
| Log every N steps | `10` | TensorBoard loss/LR logging | Lower for more granular curves, higher to reduce overhead |
| Resume from | *(empty)* | Path to a checkpoint to resume from | Use after interrupted training. Points to a `checkpoint-epoch-N` folder |

---

### Advanced Mode Settings

These appear only when "Advanced" is selected at the start of the wizard.

#### Device & Precision

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Device | `auto` | GPU selection. Auto picks: CUDA > MPS > XPU > CPU | Multi-GPU: pick `cuda:0` or `cuda:1`. Force CPU for debugging |
| Precision | `auto` | Float format. Auto picks: bf16 (CUDA), fp16 (MPS), fp32 (CPU) | Force `fp32` for debugging NaN issues. `fp16` if your GPU lacks bf16 |

#### Optimizer & Scheduler

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Optimizer | `adamw` | Weight update algorithm | `adamw8bit` saves VRAM. `prodigy` auto-tunes LR (set LR to 1.0). `adafactor` for minimal state |
| Scheduler | `cosine` | LR decay curve after warmup | `constant` for Prodigy. `linear` for steady decay. `constant_with_warmup` for flat after ramp |

> **Prodigy note:** When you select Prodigy, set the learning rate to `1.0` and the scheduler to `constant`. Prodigy auto-tunes the actual learning rate internally.

#### VRAM Savings

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Gradient checkpointing | `yes` | Recompute activations to save VRAM (~40-60% less, ~10-30% slower) | Disable only if you have abundant VRAM and want max speed |
| Offload encoder | `no` | Move encoder/VAE to CPU after setup (~2-4 GB saved) | Enable on tight VRAM budgets (10-16 GB GPUs) |

#### Advanced Training

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Weight decay | `0.01` | L2 regularization. Prevents overfitting | Increase (0.05) for very small datasets, decrease (0.001) for large |
| Max grad norm | `1.0` | Gradient clipping threshold | Increase if you see "gradient clipping" warnings everywhere; decrease for stability |
| Bias mode | `none` | Train bias parameters: `none`, `all`, `lora_only` | `lora_only` may marginally improve quality; `all` trains all biases |

#### Data Loading

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| Workers | `4` (Linux), `0` (Windows) | Parallel data loading processes | More workers = faster loading. Windows forces 0 (multiprocessing limitation) |
| Pin memory | `yes` | Pin loaded tensors in CPU for faster GPU transfer | Disable if low on system RAM |
| Prefetch factor | `2` | Batches each worker prefetches ahead | Higher for faster GPUs that consume data quickly |
| Persistent workers | `yes` | Keep workers alive between epochs | Disable if you see memory leaks from data loading |

#### Advanced Logging

| Setting | Default | What it does | Why you'd change it |
|---|---|---|---|
| TensorBoard dir | `{output}/runs` | Where TensorBoard logs go | Custom path if you want all runs in one place |
| Heavy log every N steps | `50` | Per-layer gradient norm logging | Lower for debugging training dynamics, higher to reduce overhead |
| Sample every N epochs | `0` (disabled) | Generate audio samples during training | Not yet implemented |
