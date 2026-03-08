# GPU Compatibility Guide

ACE-Step 1.5 automatically adapts to your GPU's available VRAM, adjusting generation limits and LM model availability accordingly. The system detects GPU memory at startup and configures optimal settings.

## GPU Tier Configuration

| VRAM | Tier | LM Mode | Max Duration | Max Batch Size | LM Memory Allocation |
|------|------|---------|--------------|----------------|---------------------|
| ≤4GB | Tier 1 | Not available | 3 min | 1 | - |
| 4-6GB | Tier 2 | Not available | 6 min | 1 | - |
| 6-8GB | Tier 3 | 0.6B (optional) | With LM: 4 min / Without: 6 min | With LM: 1 / Without: 2 | 3GB |
| 8-12GB | Tier 4 | 0.6B (optional) | With LM: 4 min / Without: 6 min | With LM: 2 / Without: 4 | 3GB |
| 12-16GB | Tier 5 | 0.6B / 1.7B | With LM: 4 min / Without: 6 min | With LM: 2 / Without: 4 | 0.6B: 3GB, 1.7B: 8GB |
| 16-24GB | Tier 6 | 0.6B / 1.7B / 4B | 8 min | With LM: 4 / Without: 8 | 0.6B: 3GB, 1.7B: 8GB, 4B: 12GB |
| ≥24GB | Unlimited | All models | 10 min | 8 | Unrestricted |

## Notes

- **Default settings** are automatically configured based on detected GPU memory
- **LM Mode** refers to the Language Model used for Chain-of-Thought generation and audio understanding
- **Flash Attention**, **CPU Offload**, **Compile**, and **Quantization** are enabled by default for optimal performance
- If you request a duration or batch size exceeding your GPU's limits, a warning will be displayed and values will be clamped
- **Constrained Decoding**: When LM is initialized, the LM's duration generation is also constrained to the GPU tier's maximum duration limit, preventing out-of-memory errors during CoT generation
- For GPUs with ≤6GB VRAM, LM initialization is disabled by default to preserve memory for the DiT model
- You can manually override settings via command-line arguments or the Gradio UI

## Overriding LLM Initialization

By default, LLM is auto-enabled/disabled based on GPU VRAM. You can override this behavior.

**Important:** GPU optimizations (offload, quantization, batch limits) are **always applied** regardless of override. `ACESTEP_INIT_LLM` only controls whether to attempt LLM loading.

### Processing Flow

```
GPU Detection (full)  →  ACESTEP_INIT_LLM Override  →  Model Loading
     │                          │                          │
     ├─ offload settings        ├─ auto: use GPU result    ├─ Download model
     ├─ batch limits            ├─ true: force enable      ├─ Initialize LLM
     ├─ duration limits         └─ false: force disable    └─ (with GPU settings)
     └─ recommended models
```

### Gradio UI

```bash
# Force enable LLM (may cause OOM on low VRAM)
uv run acestep --init_llm true

# Force disable LLM (pure DiT mode)
uv run acestep --init_llm false
```

Or in `start_gradio_ui.bat`:
```batch
set INIT_LLM=--init_llm true
```

### API Server

Using environment variable:
```bash
# Auto mode (recommended)
set ACESTEP_INIT_LLM=auto
uv run acestep-api

# Force enable LLM
set ACESTEP_INIT_LLM=true
uv run acestep-api

# Force disable LLM
set ACESTEP_INIT_LLM=false
uv run acestep-api
```

Or using command line:
```bash
uv run acestep-api --init-llm
```

Or in `start_api_server.bat`:
```batch
set ACESTEP_INIT_LLM=true
```

### When to Override

| Scenario | Setting | Notes |
|----------|---------|-------|
| Low VRAM but need thinking mode | `true` | May cause OOM, use with caution |
| Fast generation without CoT | `false` | Skips LLM, uses pure DiT |
| API server pure DiT mode | `false` | Faster responses, simpler setup |
| High VRAM but want minimal setup | `false` | No LLM model download needed |

### Features Affected by LLM

When LLM is disabled, these features are automatically disabled:
- **Thinking mode** (`thinking=true`)
- **CoT caption/language detection** (`use_cot_caption`, `use_cot_language`)
- **Sample mode** (generate from description)
- **Format mode** (LLM-enhanced input)

The API server will automatically fallback to pure DiT mode when these features are requested but LLM is unavailable.

> **Community Contributions Welcome**: The GPU tier configurations above are based on our testing across common hardware. If you find that your device's actual performance differs from these parameters (e.g., can handle longer durations or larger batch sizes), we welcome you to conduct more thorough testing and submit a PR to optimize these configurations in `acestep/gpu_config.py`. Your contributions help improve the experience for all users!

## Memory Optimization Tips

1. **Low VRAM (<8GB)**: Use DiT-only mode without LM initialization for maximum duration
2. **Medium VRAM (8-16GB)**: Use the 0.6B LM model for best balance of quality and memory
3. **High VRAM (>16GB)**: Enable larger LM models (1.7B/4B) for better audio understanding and generation quality

## Debug Mode: Simulating Different GPU Configurations

For testing and development, you can simulate different GPU memory sizes using the `MAX_CUDA_VRAM` environment variable:

```bash
# Simulate a 4GB GPU (Tier 1)
MAX_CUDA_VRAM=4 uv run acestep

# Simulate an 8GB GPU (Tier 4)
MAX_CUDA_VRAM=8 uv run acestep

# Simulate a 12GB GPU (Tier 5)
MAX_CUDA_VRAM=12 uv run acestep

# Simulate a 16GB GPU (Tier 6)
MAX_CUDA_VRAM=16 uv run acestep
```

This is useful for:
- Testing GPU tier configurations on high-end hardware
- Verifying that warnings and limits work correctly for each tier
- Developing and testing new GPU configuration parameters before submitting a PR
