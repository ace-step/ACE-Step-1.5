# Multi-GPU Inference Guide

ACE-Step 1.5 can spread DiT, VAE, text encoder, and 5Hz LM components across multiple CUDA GPUs. This is useful when a single card cannot hold both an XL DiT checkpoint and a large LM (for example, 4× RTX 3090 with `acestep-v15-xl-sft` + `acestep-5Hz-lm-4B`).

## Quick start

```bash
# Automatic VRAM-aware layout (recommended on 2+ CUDA GPUs)
ACESTEP_GPU_MAPPING=auto ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-4B \
  uv run acestep --config-path acestep-v15-xl-sft --init-llm true

# Explicit layout: DiT stack on GPU 0, LM on GPU 1
ACESTEP_GPU_MAPPING=dit:0,vae:0,text_encoder:0,lm:1 \
  uv run acestep --config-path acestep-v15-xl-sft --init-llm true

# List visible CUDA devices
uv run acestep --list-gpus
```

The same mapping can be passed on the CLI instead of the environment variable:

```bash
uv run acestep --gpu-mapping auto --config-path acestep-v15-xl-sft --init-llm true
```

## Mapping formats

| Format | Example | Behavior |
|--------|---------|----------|
| `auto` | `ACESTEP_GPU_MAPPING=auto` | VRAM-aware layout when 2+ CUDA GPUs are visible; otherwise single-GPU fallback |
| `single:N` | `single:1` | All components on `cuda:N` |
| Explicit | `dit:0,vae:0,text_encoder:0,lm:1` | Per-component placement (`dit` is required) |

### Auto layout

With `gpu_mapping=auto`, ACE-Step:

1. Estimates DiT + VAE + text encoder peak VRAM from the selected checkpoint and batch size.
2. Places that stack on the GPU with the most free VRAM.
3. Places the LM on the next best GPU (preferring a different card when possible).

If auto layout cannot fit all components, startup falls back to single-device placement and logs suggestions (smaller models, explicit mapping, CPU offload).

## Environment variables

| Variable | Description |
|----------|-------------|
| `ACESTEP_GPU_MAPPING` | Component layout (`auto`, `single:N`, or explicit map) |
| `ACESTEP_DEVICE` | Base device when no mapping is set (legacy single-GPU path) |
| `ACESTEP_LM_DEVICE` | **Deprecated** — use `ACESTEP_GPU_MAPPING` with `lm:N` instead |

CLI flags `--gpu-mapping` and `--list-gpus` mirror the Gradio/API surface. When both CLI and env are set, the CLI value wins and is written to `ACESTEP_GPU_MAPPING`.

## API status fields

`/health`, `/v1/models`, and `/v1/model_inventory` include:

- `gpus` — visible CUDA devices with free/total VRAM
- `gpu_mapping` — active `ACESTEP_GPU_MAPPING` value (if any)
- `device_map` — resolved component layout after initialization (`dit`, `vae`, `text_encoder`, `lm`, `summary`, `multi_device`)

Example `device_map` payload:

```json
{
  "dit": "cuda:0",
  "vae": "cuda:0",
  "text_encoder": "cuda:0",
  "lm": "cuda:1",
  "summary": "dit:0, vae:0, text_encoder:0, lm:1",
  "multi_device": true
}
```

## Cross-GPU inference

When components run on different GPUs, ACE-Step routes tensors at stage boundaries (conditioning → DiT, latents → VAE, audio codes, etc.). No extra configuration is required beyond the mapping.

## Hardware examples

### 4× RTX 3090 (24 GB each)

Typical auto layout for XL SFT + 4B LM:

```
dit:0, vae:0, text_encoder:0, lm:1
```

GPUs 2–3 remain available for future batch-serving work.

### Single GPU

Leave `ACESTEP_GPU_MAPPING` unset, or use `single:0`. Behavior matches pre–multi-GPU releases.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| LM still on same GPU as DiT | Confirm `ACESTEP_GPU_MAPPING=auto` and 2+ visible GPUs (`--list-gpus`) |
| OOM during auto layout | Try explicit `lm:1`, smaller LM, or CPU offload |
| `ACESTEP_LM_DEVICE` ignored | Expected when `ACESTEP_GPU_MAPPING` assigns `lm`; use `lm:N` in the mapping |

See also: [GPU Compatibility Guide](GPU_COMPATIBILITY.md) for per-tier VRAM limits and UI defaults.
