# GPU Compatibility Guide

ACE-Step 1.5 automatically adapts to your GPU's available VRAM, adjusting generation limits, LM model availability, offloading strategies, and UI defaults accordingly. The system detects GPU memory at startup and configures optimal settings for your hardware.

## GPU Tier Configuration

| VRAM | Tier | XL (4B) DiT | LM Models | Recommended LM | Backend | Max Duration (LM / No LM) | Max Batch (LM / No LM) | Offload | Quantization |
|------|------|:-----------:|-----------|-----------------|---------|----------------------------|-------------------------|---------|--------------|
| ≤4GB | Tier 1 | ❌ | None | — | pt | 4 min / 6 min | 1 / 1 | CPU + DiT | INT8 |
| 4-6GB | Tier 2 | ❌ | None | — | pt | 8 min / 10 min | 1 / 1 | CPU + DiT | INT8 |
| 6-8GB | Tier 3 | ❌ | 0.6B | 0.6B | pt | 8 min / 10 min | 2 / 2 | CPU + DiT | INT8 |
| 8-12GB | Tier 4 | ❌ | 0.6B | 0.6B | vllm | 8 min / 10 min | 2 / 4 | CPU + DiT | INT8 |
| 12-16GB | Tier 5 | ⚠️ | 0.6B, 1.7B | 1.7B | vllm | 8 min / 10 min | 4 / 4 | CPU | INT8 |
| 16-20GB | Tier 6a | ✅ (offload) | 0.6B, 1.7B | 1.7B | vllm | 8 min / 10 min | 4 / 8 | CPU | INT8 |
| 20-24GB | Tier 6b | ✅ | 0.6B, 1.7B, 4B | 1.7B | vllm | 8 min / 8 min | 8 / 8 | None | None |
| ≥24GB | Unlimited | ✅ | All (0.6B, 1.7B, 4B) | 4B | vllm | 10 min / 10 min | 8 / 8 | None | None |

> **XL (4B) DiT column**: ❌ = not supported, ⚠️ = marginal (offload + quantization required, reduced batch; works on 12-16GB with aggressive offload), ✅ (offload) = supported with CPU offload, ✅ = fully supported. XL models use ~9GB VRAM for weights (vs ~4.7GB for 2B). All LM models are compatible with XL.

### Column Descriptions

- **LM Models**: Which 5Hz Language Model sizes can be loaded on this tier
- **Recommended LM**: The default LM model selected in the UI for this tier
- **Backend**: LM inference backend (`vllm` for NVIDIA GPUs with sufficient VRAM, `pt` for PyTorch fallback, `mlx` for Apple Silicon)
- **Offload**: Memory offloading strategy
  - **CPU + DiT**: All models (DiT, VAE, Text Encoder) offloaded to CPU when not in use; DiT also offloaded between steps
  - **CPU**: VAE and Text Encoder offloaded to CPU; DiT stays on GPU
  - **None**: All models remain on GPU
- **Quantization**: Whether INT8 weight quantization is enabled by default to reduce VRAM usage

## Adaptive UI Defaults

The Gradio UI automatically configures itself based on the detected GPU tier:

- **LM Initialization Checkbox**: Checked by default for tiers that support LM (Tier 3+), unchecked and disabled for Tier 1-2
- **LM Model Path**: Pre-populated with the recommended model for your tier; dropdown only shows compatible models
- **Backend Dropdown**: Restricted to `pt`/`mlx` on Tier 1-3 (vllm KV cache is too memory-hungry); all backends available on Tier 4+
- **CPU Offload / DiT Offload**: Enabled by default on lower tiers, disabled on higher tiers
- **Quantization**: Enabled by default on Tier 1-6a, disabled on Tier 6b+ (sufficient VRAM)
- **Compile Model**: Enabled by default on all tiers (required for quantization)

If you manually select an incompatible option (e.g., trying to use vllm on a 6GB GPU), the system will warn you and automatically fall back to a compatible configuration.

## Runtime Safety Features

- **VRAM Guard**: Before each inference, the system estimates VRAM requirements and automatically reduces batch size if needed
- **Adaptive VAE Decode**: Three-tier fallback: GPU tiled decode → GPU decode with CPU offload → full CPU decode
- **Auto Chunk Size**: VAE decode chunk size adapts to available free VRAM (64/128/256/512/1024/1536)
- **Duration/Batch Clamping**: If you request values exceeding your tier's limits, they are clamped with a warning

## Legacy CUDA GPU Backend Selection

GPUs with a CUDA compute capability below 7.0 (pre-Volta architecture) automatically use the PyTorch (`pt`) backend for the 5Hz Language Model instead of vLLM. This affects cards such as the GTX 1080, GTX 1080 Ti, TITAN Xp, Tesla P100, and all older NVIDIA GPUs.

The detection happens at startup in `acestep/gpu_config.py` (`is_legacy_cuda_gpu` at line 135). When `torch.cuda.get_device_capability()` returns a major version less than 7, the system sets `lm_backend_restriction` to `"pt_only"` and `recommended_backend` to `"pt"`, overriding the tier-level default regardless of VRAM tier.

**Key points:**

- **No user action required** -- the fallback is fully automatic and transparent.
- **Which GPUs**: Any NVIDIA CUDA GPU with compute capability < 7.0 (Maxwell, Pascal, and earlier architectures). Volta (7.0) and newer GPUs are unaffected.
- **Why**: vLLM's nano-vllm engine relies on Triton kernels and features that require Volta-class hardware or later. The PyTorch backend provides full compatibility at the cost of somewhat slower LM inference.
- **ROCm GPUs are excluded** from this check -- the legacy detection only applies to CUDA devices.

## Notes

- **Default settings** are automatically configured based on detected GPU memory
- **LM Mode** refers to the Language Model used for Chain-of-Thought generation and audio understanding
- **Flash Attention** is auto-detected and enabled when available
- **Constrained Decoding**: When LM is initialized, the LM's duration generation is also constrained to the GPU tier's maximum duration limit, preventing out-of-memory errors during CoT generation
- For GPUs with ≤6GB VRAM (Tier 1-2), LM initialization is disabled by default to preserve memory for the DiT model
- You can manually override settings via command-line arguments or the Gradio UI

> **Community Contributions Welcome**: The GPU tier configurations above are based on our testing across common hardware. If you find that your device's actual performance differs from these parameters (e.g., can handle longer durations or larger batch sizes), we welcome you to conduct more thorough testing and submit a PR to optimize these configurations in `acestep/gpu_config.py`. Your contributions help improve the experience for all users!

## Memory Optimization Tips

1. **Very Low VRAM (≤6GB)**: Use DiT-only mode without LM initialization. INT8 quantization and full CPU offload are mandatory. VAE decode may fall back to CPU automatically.
2. **Low VRAM (6-8GB)**: The 0.6B LM model can be used with `pt` backend. Keep offload enabled.
3. **Medium VRAM (8-16GB)**: Use the 0.6B or 1.7B LM model. `vllm` backend works well on Tier 4+.
4. **High VRAM (16-24GB)**: Enable larger LM models (1.7B recommended). Quantization becomes optional on 20GB+. XL (4B) DiT models are supported — with offload on 16GB, without offload on 20GB+.
5. **Very High VRAM (≥24GB)**: All models fit without offloading or quantization. Use XL DiT + 4B LM for best quality.

## Debug Mode: Simulating Different GPU Configurations

For testing and development, you can simulate different GPU memory sizes using the `MAX_CUDA_VRAM` environment variable:

```bash
# Simulate a 4GB GPU (Tier 1)
MAX_CUDA_VRAM=4 uv run acestep

# Simulate a 6GB GPU (Tier 2)
MAX_CUDA_VRAM=6 uv run acestep

# Simulate an 8GB GPU (Tier 4)
MAX_CUDA_VRAM=8 uv run acestep

# Simulate a 12GB GPU (Tier 5)
MAX_CUDA_VRAM=12 uv run acestep

# Simulate a 16GB GPU (Tier 6a)
MAX_CUDA_VRAM=16 uv run acestep
```

When `MAX_CUDA_VRAM` is set, the system also calls `torch.cuda.set_per_process_memory_fraction()` to enforce a hard VRAM cap, making the simulation realistic even on high-end GPUs.

### Automated Tier Testing

Instead of manually testing each tier through the UI, use the `tier-test` mode of `profile_inference.py`:

```bash
# Test all tiers automatically
python profile_inference.py --mode tier-test

# Test specific tiers
python profile_inference.py --mode tier-test --tiers 6 8 16

# Test with LM enabled (where supported)
python profile_inference.py --mode tier-test --tier-with-lm

# Quick test (skip torch.compile for non-quantized tiers)
python profile_inference.py --mode tier-test --tier-skip-compile
```

See [BENCHMARK.md](BENCHMARK.md) for full documentation of the profiling tool.

This is useful for:
- Testing GPU tier configurations on high-end hardware
- Verifying that warnings and limits work correctly for each tier
- Automated regression testing after modifying `acestep/gpu_config.py`
- CI/CD validation of VRAM compatibility

### Boundary Testing (Finding Minimum Tiers)

Use `--tier-boundary` to empirically determine the minimum VRAM tier at which INT8 quantization and CPU offload can be safely disabled. For each tier, this runs up to three configurations:

1. **default** — tier's standard settings (quantization + offload as configured)
2. **no-quant** — same offload settings, but quantization disabled
3. **no-offload** — no quantization AND no CPU offload (all models on GPU)

```bash
# Run boundary tests across all tiers
python profile_inference.py --mode tier-test --tier-boundary

# Test specific tiers with boundary testing
python profile_inference.py --mode tier-test --tier-boundary --tiers 8 12 16 20 24

# Boundary test with LM enabled (where supported)
python profile_inference.py --mode tier-test --tier-boundary --tier-with-lm

# Save results to JSON for further analysis
python profile_inference.py --mode tier-test --tier-boundary --benchmark-output boundary_results.json
```

The output includes a **Boundary Analysis** section showing the minimum tier for each capability:

```
BOUNDARY ANALYSIS
=================
  Capability                                    Min Tier   VRAM
  ------------------------------------------------------------
  No INT8 Quantization                          tier6b      20GB
  No CPU Offload (all models on GPU)            tier6b      20GB
  ------------------------------------------------------------
```

> **Note:** Boundary results are empirical and may vary based on DiT model variant (turbo vs base), whether LM is enabled, generation duration, and flash attention availability. Community contributions to refine these boundaries are welcome!

### Batch Size Boundary Testing

Use `--tier-batch-boundary` to find the maximum safe batch size for each tier by progressively testing batch sizes 1, 2, 4, 8:

```bash
# Run batch boundary tests with LM enabled
python profile_inference.py --mode tier-test --tier-batch-boundary --tier-with-lm

# Test specific tiers
python profile_inference.py --mode tier-test --tier-batch-boundary --tier-with-lm --tiers 8 12 16 24
```

This tests both with-LM and without-LM configurations and reports the maximum successful batch size per tier.
