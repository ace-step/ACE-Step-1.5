# Preset Management

Presets are named JSON files containing training hyperparameters. They let you save, share, and reuse training configurations without re-entering every setting.

---

## What a Preset Contains

A preset stores **38 training fields** covering adapter type, LoRA/LoKR settings, training hyperparameters, and VRAM-related options. It does **not** store:

- File paths (checkpoint dir, dataset dir, output dir)
- Device settings (GPU, precision)
- Model-derived timestep parameters (`timestep_mu`, `timestep_sigma`)

This means presets are portable between machines and projects. When you load a preset, missing fields fall back to wizard defaults. Unknown fields are silently ignored.

### Fields Included in Presets

| Category | Fields |
| :--- | :--- |
| Adapter | `adapter_type` |
| LoRA | `rank`, `alpha`, `dropout`, `target_modules_str`, `attention_type`, `bias` |
| LoKR | `lokr_linear_dim`, `lokr_linear_alpha`, `lokr_factor`, `lokr_decompose_both`, `lokr_use_tucker`, `lokr_use_scalar`, `lokr_weight_decompose` |
| Training | `learning_rate`, `batch_size`, `gradient_accumulation`, `epochs`, `warmup_steps`, `weight_decay`, `max_grad_norm`, `seed`, `shift`, `num_inference_steps`, `optimizer_type`, `scheduler_type`, `cfg_ratio` |
| Checkpointing / Logging | `save_every`, `log_every`, `log_heavy_every`, `sample_every_n_epochs` |
| VRAM | `gradient_checkpointing`, `offload_encoder` |

---

## Storage Locations

Presets are stored in three locations, searched in this priority order:

| Priority | Location | Platform | Purpose |
| :--- | :--- | :--- | :--- |
| 1 (highest) | `./presets/` | All | Project-local user presets. New saves go here. |
| 2 | `~/.config/sidestep/presets/` | Linux/macOS | Global user presets (fallback). |
| 2 | `%APPDATA%\sidestep\presets\` | Windows | Global user presets (fallback). |
| 3 (lowest) | `acestep/training_v2/presets/` | All | Built-in presets shipped with Side-Step. Read-only. |

**Key behaviors:**

- **Loading** searches local first, then global, then built-in. The first match wins.
- **Saving** always writes to the local directory (`./presets/`).
- **Deleting** can remove local or global presets. Built-in presets cannot be deleted.
- A local preset with the same name as a built-in effectively overrides it.

The local directory is anchored to the Side-Step project root (found by looking for `train.py` or `pyproject.toml` + `acestep/`), so presets are always found regardless of your current working directory.

---

## Built-in Presets

Side-Step ships with seven built-in presets:

| Preset | Description | Key Settings |
| :--- | :--- | :--- |
| `recommended` | Balanced defaults for most LoRA fine-tuning tasks | Rank 64, alpha 128, 100 epochs, AdamW, cosine LR |
| `quick_test` | Fast iteration for testing | Rank 16, alpha 32, 10 epochs |
| `high_quality` | High capacity, long training | Rank 128, alpha 256, 1000 epochs |
| `vram_24gb_plus` | Comfortable tier (RTX 3090, 4090, A100) | Rank 128, batch 2, grad accumulation 2, AdamW |
| `vram_16gb` | Standard tier (RTX 4080, 3080 Ti) | Rank 64, batch 1, AdamW |
| `vram_12gb` | Tight tier (RTX 3060 12GB, 4070) | Rank 32, AdamW8bit, encoder offloading |
| `vram_8gb` | Minimal tier (RTX 4060 8GB, 3050, GTX 1080) | Rank 16, AdamW8bit, encoder offloading, high grad accumulation |

All built-in presets are configured for **turbo** models (`shift=3.0`, `num_inference_steps=8`). If training on a base or sft model, adjust these after loading the preset.

---

## Using Presets in the Wizard

### Loading a Preset

When starting a training flow in the wizard, Side-Step offers to load a preset before asking configuration questions. The preset values pre-fill the wizard prompts so you can accept defaults or modify individual settings.

### Saving a Preset

After configuring training, the wizard offers to save your current settings as a named preset. Enter a name and optional description. The preset is saved to `./presets/` as a JSON file.

### Managing Presets

From the wizard's main menu, select **Manage presets** to access the preset management submenu:

- **List** -- Show all available presets (local, global, and built-in) with descriptions.
- **View** -- Display the full contents of a preset.
- **Delete** -- Remove a user preset (local or global). Built-in presets cannot be deleted.
- **Import** -- Import a preset from an external JSON file into your local presets directory.
- **Export** -- Export any preset (including built-ins) to a file path of your choice.

---

## Import and Export

### Importing

Import copies an external JSON file into your local presets directory (`./presets/`):

- The file must be valid JSON and under 1 MB.
- The preset name is taken from the `"name"` field in the JSON, or from the filename if no name field exists.
- The name is sanitized for filesystem safety (see naming rules below).

### Exporting

Export copies any preset (local, global, or built-in) to a specified file path. This is useful for sharing presets with others or backing them up.

### Naming Rules

Preset names are sanitized to be safe filenames on all platforms:

- Spaces are replaced with underscores.
- The following characters are removed: `/\:*?"<>|`
- Path traversal (`..`, leading `/` or `\`) is rejected.
- Windows reserved names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`) are rejected.

---

## Preset JSON Format

If you want to create a preset by hand, here is the format:

```json
{
  "name": "my_preset",
  "description": "My custom training configuration",
  "adapter_type": "lora",
  "rank": 64,
  "alpha": 128,
  "dropout": 0.1,
  "target_modules_str": "q_proj k_proj v_proj o_proj",
  "attention_type": "both",
  "bias": "none",
  "learning_rate": 0.0001,
  "batch_size": 1,
  "gradient_accumulation": 4,
  "epochs": 100,
  "warmup_steps": 100,
  "weight_decay": 0.01,
  "max_grad_norm": 1.0,
  "seed": 42,
  "shift": 3.0,
  "num_inference_steps": 8,
  "optimizer_type": "adamw",
  "scheduler_type": "cosine",
  "cfg_ratio": 0.15,
  "save_every": 10,
  "log_every": 10,
  "log_heavy_every": 50,
  "gradient_checkpointing": true,
  "offload_encoder": false,
  "sample_every_n_epochs": 0
}
```

You do not need to include every field. Missing fields use wizard defaults. The `name` and `description` fields are metadata and not used during training.

---

## See Also

- [[The Settings Wizard]] -- Full wizard settings reference
- [[VRAM Optimization Guide]] -- GPU memory profiles and trade-offs
- [[Training Guide]] -- Training options and hyperparameters
