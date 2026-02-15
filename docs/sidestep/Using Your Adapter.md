# Using Your Adapter

After training completes, Side-Step saves your adapter weights to the output directory. This page explains the output layout, how to load adapters in ACE-Step's Gradio UI, and important considerations for inference.

---

## Output Directory Layout

### LoRA Training

```
output/my_lora/
├── final/
│   ├── adapter_config.json         # PEFT adapter configuration
│   └── adapter_model.safetensors   # Trained LoRA weights
├── checkpoints/
│   └── epoch_10/                   # Saved every N epochs (--save-every)
│       ├── adapter_config.json
│       ├── adapter_model.safetensors
│       └── training_state.pt       # Optimizer + scheduler state for resume
└── runs/
    └── [TensorBoard event files]   # Training metrics
```

### LoKR Training

```
output/my_lokr/
├── final/
│   └── lokr_weights.safetensors    # Trained LoKR weights (config in metadata)
├── checkpoints/
│   └── epoch_10/
│       ├── lokr_weights.safetensors
│       └── training_state.pt
└── runs/
    └── [TensorBoard event files]
```

Key differences:

- **LoRA** saves two files: `adapter_config.json` (PEFT configuration) + `adapter_model.safetensors` (weights).
- **LoKR** saves one file: `lokr_weights.safetensors` (weights + configuration stored in safetensors metadata).
- **Checkpoints** include `training_state.pt` for resuming training. The adapter files in each checkpoint are also inference-ready.
- The `final/` directory contains only the adapter weights (no training state) -- this is what you point inference tools at.

---

## Loading LoRA in ACE-Step Gradio

ACE-Step's Gradio UI has a built-in LoRA loading section. Here is how to use it:

1. **Start ACE-Step's Gradio UI** as you normally would.
2. In the **Service Configuration** section, find the **LoRA Adapter** panel.
3. In the **LoRA Path** field, enter the path to your adapter directory:
   ```
   /path/to/Side-Step/output/my_lora/final
   ```
   Point at the directory, not at a specific file. ACE-Step expects to find `adapter_config.json` inside it.
4. Click **Load LoRA**. You should see a success message.
5. Toggle **Use LoRA** to enable the adapter during generation.
6. Adjust the **LoRA Scale** slider to control how strongly the adapter affects output (1.0 = full strength, lower values blend with the base model).
7. Generate audio as usual.

To switch back to the base model, click **Unload** or toggle **Use LoRA** off.

### Requirements

- **Quantization must be disabled.** LoRA loading is not supported when INT8 quantization is active. If you see an error about quantization, re-initialize the ACE-Step service with quantization set to `None`.
- The adapter was trained with PEFT, so ACE-Step's standard LoRA loading path works directly.

### Using Checkpoints for Inference

Every checkpoint directory (`checkpoints/epoch_N/`) also contains inference-ready adapter files. You can point the Gradio LoRA path at any checkpoint to test intermediate training results:

```
/path/to/Side-Step/output/my_lora/checkpoints/epoch_50
```

---

## LoKR Limitation

ACE-Step's Gradio UI currently **only supports PEFT LoRA adapters**. The loading code checks for `adapter_config.json`, which LoKR does not produce (LoKR uses LyCORIS format with `lokr_weights.safetensors`).

**LoKR adapters cannot be loaded in the standard ACE-Step Gradio UI at this time.** If you trained a LoKR adapter and want to use it for inference, you will need to write custom inference code using the LyCORIS library, or wait for LoKR support to be added to ACE-Step.

If you are unsure which adapter type to use, **LoRA is the safe choice** for both training and inference compatibility.

---

## Shift and Inference Steps

When generating audio with your trained adapter, use the correct `shift` and inference step values for your model variant:

| Model Variant | Shift | Inference Steps |
| :--- | :--- | :--- |
| Turbo | `3.0` | `8` |
| Base | `1.0` | `50` |
| SFT | `1.0` | `50` |

These values were saved as metadata during training (via `--shift` and `--num-inference-steps`) but **do not affect the training loop itself**. They tell you what to use at inference time. See [[Shift and Timestep Sampling]] for the full explanation.

Using the wrong shift value at inference will produce degraded audio quality, even if the adapter was trained correctly.

---

## Viewing TensorBoard Logs

Side-Step writes TensorBoard logs to the `runs/` subdirectory of your output directory (or to `--log-dir` if you specified one). To view them:

```bash
tensorboard --logdir ./output/my_lora/runs
```

Then open `http://localhost:6006` in your browser. Key metrics:

- **loss** -- Training loss over time. Should decrease and stabilize.
- **lr** -- Learning rate schedule. Verify warmup and decay look correct.
- **grad_norm** -- Gradient magnitudes. Spikes may indicate training instability.

---

## Resuming Training

To continue training from a checkpoint:

```bash
uv run train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --dataset-dir ./my_tensors \
    --output-dir ./output/my_lora \
    --resume-from ./output/my_lora/checkpoints/epoch_50 \
    --epochs 200
```

This restores the adapter weights, optimizer state, and learning rate scheduler from the checkpoint. Training continues from where it left off.

You can also point `--resume-from` at a file inside the checkpoint directory (e.g., `training_state.pt`) -- Side-Step will automatically use the parent directory.

---

## See Also

- [[End-to-End Tutorial]] -- Full walkthrough from raw audio to generation
- [[Shift and Timestep Sampling]] -- Why shift matters for inference
- [[Training Guide]] -- Training options and hyperparameters
- [[VRAM Optimization Guide]] -- GPU memory management
