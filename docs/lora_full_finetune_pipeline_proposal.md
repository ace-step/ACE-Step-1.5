# Proposal: Improve ACE-Step LoRA Training Execution Pipeline and Add Full Fine-Tuning Capability

## 1) Current-state findings (from code walk)

### What is already good
- The training loops (`vanilla` and `fixed`) consume **preprocessed `.pt` tensors** via `PreprocessedDataModule`, not raw audio.
- The v2 preprocessing path already runs a **two-pass offline pipeline**:
  - Pass 1: audio decode + VAE encode + text/lyrics encode into temporary tensors.
  - Pass 2: DIT encoder + context latent construction into final training tensors.

### Where inefficiency/risk still exists
- Each sample is stored as a separate `.pt` file; the dataset loader does `torch.load` per sample at runtime. This avoids real-time VAE decode but can still bottleneck on filesystem seeks + Python deserialization for large datasets.
- Pass 2 currently re-loads each temporary file independently and repeatedly transfers multiple tensors to GPU; this is functional but not optimized for throughput.
- The training stack is adapter-centric (LoRA/LoKR) and does not expose a first-class, safe “full fine-tune” mode with optimizer/parameter-group controls, freezing policies, and checkpoint strategy.

---

## 2) Proposal A — Better LoRA execution pipeline (precompute-first, throughput-oriented)

## A1. Introduce a packed latent dataset format (v3)
Create a new optional preprocessing output format:
- `shard-xxxxx.safetensors` (or `.pt` if needed) with contiguous arrays.
- `index.jsonl` containing sample metadata + byte/range mapping.

Benefits:
- Fewer file opens/seeks vs one-file-per-sample.
- Faster startup and epoch iteration.
- Easier weighted sampling and bucketing using index metadata only.

Backward compatibility:
- Keep existing `.pt`-per-sample format as default for compatibility.
- Add `--dataset-format {pt,v3_sharded}` and auto-detect in loader.

## A2. Add duration/latent-length bucketing in dataloader
- Precompute latent length in manifest/index.
- Build bucketed batches (near-equal lengths) to reduce padding waste.
- Keep deterministic shuffling by bucket + epoch seed.

Expected gain:
- Better GPU utilization and lower wasted FLOPs for variable-length audio.

## A3. Add optional in-memory or mmap cache layer
- New runtime flag: `--cache-policy {none,mmap,ram_lru}`.
- `mmap`: avoid repeated deserialization cost.
- `ram_lru`: cache hottest tensors with memory cap (`--cache-max-gb`).

Expected gain:
- Less CPU overhead and reduced storage I/O jitter.

## A4. Precompute and persist all conditioning tensors once
The current two-pass preprocessing already computes major tensors. Extend this by:
- Persisting any variant-dependent conditioning expansions that remain deterministic.
- Recording preprocessing fingerprint (`model variant`, `checkpoint hash`, `tokenizer hash`) to enforce dataset/model compatibility before training starts.

## A5. Add asynchronous prefetch + pinned staging buffer
- A small CUDA prefetcher can move next batch to device while current batch trains.
- Expose `--device-prefetch` with safe fallback.

## A6. Add preprocessing QA command
New CLI check command before training:
- Verifies tensor shapes/dtypes/masks.
- Checks for NaNs/infs.
- Reports padding efficiency estimate and bucket distribution.

---

## 3) Proposal B — Full model fine-tuning mode (beyond LoRA)

## B1. Add `adapter_type=full` (or `training_mode=full`)
- Reuse existing trainer shell and UI flow.
- Skip adapter injection and mark selected modules trainable.

Initial scope (safe):
- Fine-tune **decoder-only** first.
- Keep encoder/VAE frozen by default.

Advanced scope:
- Optional staged unfreezing (decoder → encoder).
- Optional text encoder unfreezing for domain transfer.

## B2. Parameter-group and LR policy
Provide explicit parameter groups:
- `decoder.attn`, `decoder.ffn`, `norm`, `embeddings` (as applicable).
- Distinct LR multipliers (`--lr-mult-attn`, etc.).
- Weight decay exclusions for norms/biases.

## B3. Memory-safe full FT path
- Mandatory gradient checkpointing path validation.
- bf16/fp16 mixed precision with fp32 master weights where needed.
- Optional 8-bit optimizer support where stable.
- Optional FSDP/ZeRO integration behind explicit flag.

## B4. Checkpointing and resume semantics for full FT
- Save full model state (or sharded states) + optimizer + scheduler + scaler.
- Add periodic EMA checkpoint option for stability.
- Add strict compatibility validation on resume.

## B5. Safety controls
- Require explicit opt-in (`--training-mode full --i-understand-vram-risk`).
- Preflight VRAM estimator for model variant + seq length + batch size.
- Auto-suggest fallback to LoRA when estimate exceeds threshold.

## B6. Evaluation and regression hooks
- Add minimal validation hooks (loss-only + optional sample generation every N epochs).
- Track train/val divergence and expose early-stop patience.

---

## 4) Suggested implementation plan (low-risk phases)

### Phase 1: Data throughput
1. Add packed dataset writer + loader (behind flags).
2. Add bucketed sampler.
3. Add preprocessing QA validator.

### Phase 2: Runtime pipeline polish
1. Add mmap/LRU cache policy.
2. Add optional device prefetch.
3. Benchmark and publish defaults by GPU class.

### Phase 3: Full fine-tuning MVP
1. Add `training_mode=full` with decoder-only unfreeze.
2. Add parameter groups + LR multipliers.
3. Add full-state checkpoint/resume.

### Phase 4: Advanced scaling
1. Add distributed/sharded optimizer options.
2. Add staged unfreeze profiles.
3. Add stronger eval/early-stop controls.

---

## 5) Acceptance criteria (measurable)

For LoRA pipeline improvements:
- >=20% faster step time on medium dataset vs current `.pt` baseline.
- >=15% reduction in data-loader stall time.
- No regression in final training loss curve over fixed seed smoke run.

For full fine-tuning MVP:
- Successfully trains decoder-only full FT for at least one epoch on supported GPU setup.
- Resume from checkpoint reproduces optimizer/scheduler state correctly.
- CLI safety checks prevent accidental OOM-prone config starts.

---

## 6) Immediate next patch candidates
1. Add `DatasetBackend` abstraction and a sharded backend implementation.
2. Add `BucketedBatchSampler` keyed by latent length.
3. Add `train.py validate-dataset --dataset-dir ...` command.
4. Add `training_mode` enum + `full` branch in config/trainer with decoder-only unfreeze.
