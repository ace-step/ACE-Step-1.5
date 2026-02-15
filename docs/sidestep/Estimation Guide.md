
## What Is Gradient Estimation?

Gradient estimation (also called sensitivity analysis) ranks the attention modules inside the ACE-Step decoder by how much they respond to **your specific dataset**. Instead of blindly training every `q_proj`, `k_proj`, `v_proj`, and `o_proj` layer equally, estimation tells you which ones matter most.

Think of it like an X-ray of the model: it shows where the gradients concentrate when your audio is passed through the network.

---

## Why It Matters

- **Targeted training**: Focus the adapter on the layers that actually learn from your data.
- **Fewer wasted parameters**: If layer 22 barely responds to your dataset, you don't need to train it.
- **Better results at lower rank**: By selecting only the top-K most sensitive modules, a rank-32 adapter trained on 16 carefully chosen modules can outperform a rank-64 adapter spread across all 80+ modules.
- **Dataset comparison**: Run estimation on two different datasets and compare -- you'll see where they differ.

---

## How To Run Estimation

### Via the Wizard (Recommended)

```bash
uv run python train.py
```

1. From the main menu, select **Estimate gradient sensitivity**
2. Point it to your checkpoint directory and preprocessed dataset
3. Adjust the parameters (or press Enter for defaults)
4. Review the results and save the JSON

### Via CLI

```bash
uv run python train.py estimate \
    --checkpoint-dir ../ACE-Step-1.5/checkpoints \
    --model-variant base \
    --dataset-dir ./my_tensors \
    --estimate-batches 5 \
    --top-k 16 \
    --granularity module \
    --estimate-output ./estimate_results.json
```

---

## Reading the Output

Estimation produces a JSON file with a ranked list:

```json
[
  {"module": "decoder.layers.22.self_attn.q_proj", "sensitivity": 0.04231},
  {"module": "decoder.layers.22.self_attn.v_proj", "sensitivity": 0.03894},
  {"module": "decoder.layers.18.cross_attn.k_proj", "sensitivity": 0.03512},
  ...
]
```

### What Each Field Means

| Field | Meaning |
|-------|---------|
| `module` | Full dot-path name of the attention projection inside the decoder |
| `sensitivity` | Average gradient norm across estimation batches (higher = more responsive) |

**Higher sensitivity = more important for your dataset.** The modules at the top of the list are where the model "wants" to change the most when it sees your audio.

---

## Understanding Module Names

ACE-Step's decoder is a stack of transformer layers. Each layer has attention blocks, and each attention block has four linear projections:

| Projection | Role |
|------------|------|
| `q_proj` | **Query** -- what the model is looking for |
| `k_proj` | **Key** -- what each position offers |
| `v_proj` | **Value** -- the actual content to read |
| `o_proj` | **Output** -- projects the attention result back |

### Self-Attention vs Cross-Attention

| Type | Path Pattern | What It Does |
|------|-------------|--------------|
| Self-attention | `decoder.layers.N.self_attn.*` | Relates audio positions to each other (rhythm, structure, patterns) |
| Cross-attention | `decoder.layers.N.cross_attn.*` | Connects audio to text conditioning (lyrics, genre, prompt) |

**Interpretation tips:**

- If **self-attention** modules rank high, your dataset has distinctive audio patterns (rhythms, timbres, structures) the model wants to learn.
- If **cross-attention** modules rank high, the text/lyrics conditioning is strongly tied to the audio -- the model is learning text-to-audio alignment.
- If a specific **layer number** dominates (e.g., layers 18-22), those are the layers where your dataset diverges most from the pre-trained weights.

---

## Module-Level vs Layer-Level Granularity

| Granularity | `--granularity` | What It Ranks | When To Use |
|-------------|-----------------|---------------|-------------|
| Module | `module` (default) | Individual projections (`q_proj`, `k_proj`, etc.) | Fine-grained selection, small datasets, precise control |
| Layer | `layer` | Entire attention blocks (`self_attn`, `cross_attn`) | Quick overview, large datasets, coarse selection |

**Module-level** is almost always the better choice. It lets you pick exactly which projections to target. Layer-level is useful as a quick first pass to see which depth regions of the decoder are most active.

---

## Using Results for Training

### Selecting Target Modules

After estimation, the top-K modules tell you which projections to target. For example, if the top 8 modules are all `q_proj` and `v_proj` in layers 18-24:

- You might set `--target-modules "q_proj v_proj"` (skip `k_proj` and `o_proj`)
- Or focus rank on those specific layers

### Practical Example

Suppose estimation returns:

```
#1  decoder.layers.22.self_attn.q_proj   0.042
#2  decoder.layers.22.self_attn.v_proj   0.039
#3  decoder.layers.18.cross_attn.k_proj  0.035
#4  decoder.layers.18.cross_attn.v_proj  0.033
#5  decoder.layers.20.self_attn.q_proj   0.031
...
#12 decoder.layers.5.self_attn.o_proj    0.008
#16 decoder.layers.2.cross_attn.k_proj   0.002
```

**What this tells you:**
- Layers 18-22 are the most sensitive -- your dataset is "different" from the pre-trained model at those depths
- Self-attention dominates -- the model wants to learn audio patterns more than text alignment
- Layer 2 barely responds -- it's already general enough and doesn't need fine-tuning
- `q_proj` and `v_proj` rank higher than `k_proj` and `o_proj` -- queries and values carry the signal

**Action:** You could train with `--target-modules "q_proj v_proj"` and expect strong results even at lower rank, since you're focusing on what matters.

---

## Parameter Guide

| Parameter | Default | Guidance |
|-----------|---------|----------|
| `--estimate-batches` | 5 | More batches = more stable ranking. 3-5 is enough for small datasets; 10+ for large/diverse ones. |
| `--top-k` | 16 | How many modules to highlight. 8-16 is a good range. Beyond 32 you're training most of the model anyway. |
| `--granularity` | `module` | Use `module` unless you want a quick layer-level overview first. |

### VRAM Considerations

Estimation loads the full model and runs forward + backward passes, similar to training. Budget the same VRAM you would for training:

| GPU VRAM | Recommended `--estimate-batches` |
|----------|----------------------------------|
| 8 GB | 3 |
| 12 GB | 5 |
| 24 GB | 10 |
| 48 GB | 10-20 |

Estimation is fast -- typically 1-3 minutes regardless of batch count.

---

## See Also

- [[Training Guide]] -- Full training workflow and hyperparameter guide
- [[Model Management]] -- Checkpoint structure and model selection
