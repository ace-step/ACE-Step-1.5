
This page explains how timestep sampling works during training, what the `shift` parameter actually does, and why Side-Step's approach differs from the upstream community trainer.

> **TL;DR:** `shift` is an **inference-only** parameter. It does not affect the training loop. Side-Step's corrected training uses the same continuous timestep sampling as the model's own `forward()` method. The `--shift` and `--num-inference-steps` settings are stored as metadata so you know what values to use when generating audio with your trained adapter.

---

## What shift does (inference only)

During **inference** (audio generation), `shift` warps the timestep schedule used by the diffusion ODE/SDE solver:

```
t_shifted = shift * t / (1 + (shift - 1) * t)
```

This formula appears in `generate_audio()` inside each model variant. It controls how denoising steps are distributed:

- **shift=1.0** -- Uniform linear schedule. Steps are evenly spaced from 1.0 to 0.0. This is the standard schedule and requires more steps (typically 50) for good quality. Used by **base** and **sft** models.
- **shift=3.0** -- Compressed schedule. More denoising happens at the high end (near t=1.0), less at the low end. This allows fewer steps (typically 8) with minimal quality loss. Used by **turbo** models.

The turbo model also has pre-computed discrete timestep tables for each shift value:

| Shift | 8-step schedule |
|-------|----------------|
| 1.0 | `[1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125]` |
| 2.0 | `[1.0, 0.933, 0.857, 0.769, 0.667, 0.545, 0.4, 0.222]` |
| 3.0 | `[1.0, 0.955, 0.9, 0.833, 0.75, 0.643, 0.5, 0.3]` |

---

## What controls training timesteps

During **training**, timesteps are sampled from a continuous distribution. All three ACE-Step model variants (turbo, base, sft) define the same `sample_t_r()` function in their model code:

```python
def sample_t_r(batch_size, device, dtype, data_proportion, timestep_mu, timestep_sigma, use_meanflow):
    t = torch.sigmoid(torch.randn((batch_size,)) * timestep_sigma + timestep_mu)
    r = torch.sigmoid(torch.randn((batch_size,)) * timestep_sigma + timestep_mu)
    t, r = torch.maximum(t, r), torch.minimum(t, r)
    # use_meanflow=False during training -> r = t for all samples
    ...
    return t, r
```

This is **logit-normal sampling**: draw from a normal distribution, then pass through a sigmoid to get values in (0, 1). The shape of this distribution is controlled by two parameters from the model's `config.json`:

| Parameter | Typical value | Effect |
|-----------|--------------|--------|
| `timestep_mu` | `-0.4` | Shifts the distribution center. Negative values bias toward lower timesteps |
| `timestep_sigma` | `1.0` | Controls spread. Larger values give a wider range of timesteps |

Side-Step reads these automatically from each model's `config.json` at startup. You never need to set them manually.

---

## Side-Step vs upstream (vanilla) trainer

### Side-Step corrected training (fixed mode)

Side-Step's `sample_timesteps()` function (in `timestep_sampling.py`) is a **line-for-line reimplementation** of the model's own `sample_t_r()`:

```python
# Side-Step (timestep_sampling.py)
t = torch.sigmoid(
    torch.randn((batch_size,), device=device, dtype=dtype) * timestep_sigma + timestep_mu
)
```

This matches the model's native training `forward()` method exactly, for all three variants. The parameters come from each model's `config.json`.

**Result:** Side-Step can correctly train adapters for turbo, base, and sft models because it uses the same timestep distribution the models were originally trained with.

### Upstream community trainer

The original ACE-Step community trainer (`acestep/training/trainer.py`) uses a **different approach** -- discrete timesteps hardcoded from `shift=3.0`:

```python
# Upstream trainer (trainer.py)
TURBO_SHIFT3_TIMESTEPS = [1.0, 0.955, 0.9, 0.833, 0.75, 0.643, 0.5, 0.3]

def sample_discrete_timestep(bsz, timesteps_tensor):
    indices = torch.randint(0, timesteps_tensor.shape[0], (bsz,))
    t = timesteps_tensor[indices]
    return t, t
```

Each training step uniformly picks one of those 8 discrete values. This approach:

1. **Does not match how the models were actually trained.** The models use continuous logit-normal sampling, not discrete uniform sampling.
2. **Is hardcoded for turbo.** Those specific timestep values come from `shift=3.0` with 8 steps. For base or sft models (which use `shift=1.0` and more steps), this schedule is incorrect.
3. **Samples from a fundamentally different distribution.** Uniform over 8 points vs. continuous logit-normal over the full (0, 1) range.

---

## What the shift setting does in Side-Step

When you set `--shift` or configure shift in the wizard, Side-Step:

1. **Saves it to the training config JSON** alongside your adapter weights
2. **Does NOT use it during training** -- the training timestep distribution is entirely controlled by `timestep_mu` and `timestep_sigma` from the model config

The value is stored so that you (and anyone you share your adapter with) know what shift value to use at **inference time** when generating audio with the trained LoRA/LoKR.

### Recommended values

| Model variant | `--shift` | `--num-inference-steps` |
|--------------|-----------|------------------------|
| Turbo | `3.0` | `8` |
| Base | `1.0` | `50` |
| SFT | `1.0` | `50` |

The wizard auto-detects these from the model you select.

---

## FAQ

**Q: I changed `--shift` and my training results didn't change. Is this a bug?**
No. Shift does not affect training. The training timestep distribution comes from the model's own `timestep_mu`/`timestep_sigma` parameters, which Side-Step reads automatically.

**Q: If shift doesn't affect training, why is it a setting?**
It's metadata. When you finish training and want to generate audio with your LoRA, you need to know the correct shift value. Storing it with the adapter config prevents guesswork.

**Q: Can I train a turbo model and use it with shift=1.0 at inference?**
Technically yes, but the quality will differ from what the model expects. Also, i don't think it is fully supported by upstream. Use the shift value that matches the model variant you trained on.

**Q: Why does the upstream trainer use discrete timesteps?**
The upstream community trainer was written specifically for the turbo model. It takes the 8 discrete timestep values from the turbo inference schedule and samples uniformly from them. This is a reasonable approximation for turbo but does not match the model's actual training distribution, and it does not work for base or sft models.

---

## Source references

These are the relevant source locations for anyone who wants to verify:

- **Model's native training sampling:** `sample_t_r()` in `modeling_acestep_v15_turbo.py` (lines 169-194), `modeling_acestep_v15_base.py` (same), `sft/modeling_acestep_v15_base.py` (same)
- **Model's inference shift warp:** `generate_audio()` in each model file, applies `t = shift * t / (1 + (shift - 1) * t)`
- **Side-Step's corrected sampling:** `sample_timesteps()` in `acestep/training_v2/timestep_sampling.py`
- **Upstream discrete sampling:** `sample_discrete_timestep()` in `acestep/training/trainer.py` (lines 302-323)

---

## See Also

- [[Training Guide]] -- Training modes, hyperparameters, and monitoring
- [[The Settings Wizard]] -- All wizard settings explained
- [[VRAM Optimization Guide]] -- GPU tiers and memory management
