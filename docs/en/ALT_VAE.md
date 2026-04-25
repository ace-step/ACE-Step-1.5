# Alternative VAEs

ACE-Step-1.5 ships with the official Oobleck VAE inside the main model
repo.  Since the architecture (`AutoencoderOobleck`) is fixed, any
community-finetuned VAE that publishes the same `config.json` +
`diffusion_pytorch_model.safetensors` pair is a drop-in replacement —
useful for A/B comparisons of timbre, transient handling, and vocal
grain.

## Built-in registry

Currently the following community VAE is shipped in the registry:

| Variant id | Repo | License | Author |
|---|---|---|---|
| `official` | bundled in `ACE-Step/Ace-Step1.5` | (project license) | ACE-Step |
| `scragvae` | [`scragnog/Ace-Step-1.5-ScragVAE`](https://huggingface.co/scragnog/Ace-Step-1.5-ScragVAE) | MIT | [@scragnog](https://huggingface.co/scragnog) |

ScragVAE is a finetune of
`ACE-Step/ace-step-v1.5-1d-vae-stable-audio-format`. Weights are
**not** vendored — they're pulled from HuggingFace (or ModelScope as
fallback) on first use into `<checkpoints>/scragvae/`.

## Selecting a VAE

There are three ways to pick which VAE the model loads. Resolution
order: explicit parameter > environment variable > `"official"`.

### 1. Gradio UI

Open the **Service Configuration** accordion. Next to the model
variant selector, the **VAE** dropdown now lets you pick `official`
or `scragvae`. Click **Initialize Service**; on first use the chosen
VAE is auto-downloaded.

### 2. Environment variable

```bash
export ACESTEP_VAE_CHECKPOINT=scragvae
acestep                    # any entry point — Gradio, CLI, API
```

In Gradio, the env var **seeds the dropdown's initial value** on first
launch. Once initialized, the dropdown is the source of truth — change
it and click **Initialize Service** to switch.

You can also pass an absolute path to a directory containing a valid
Oobleck VAE checkpoint (CLI / Python API only — the Gradio dropdown
only lists registered variant ids):

```bash
export ACESTEP_VAE_CHECKPOINT=/path/to/my/local/vae
```

If the absolute path doesn't exist or doesn't contain a
`diffusion_pytorch_model.safetensors`, init fails with a clear
diagnostic — we never try to "download" an absolute path.

### 3. Python API

```python
from acestep.handler import ACEStepDiTHandler

dit = ACEStepDiTHandler()
dit.initialize_service(
    project_root="./",
    config_path="acestep-v15-xl-turbo",
    vae_checkpoint="scragvae",      # or "official", or an abs path
)
```

## What the integration does — and does not — do

- **Architecture stays fixed** at `AutoencoderOobleck`. Variants must
  ship a compatible config; we don't auto-detect alternative
  architectures.
- **MLX path is automatic.** On Apple Silicon,
  `MLXAutoEncoderOobleck.from_pytorch_config(self.vae)` rebuilds the
  MLX VAE from whatever PyTorch VAE was just loaded, so the alternate
  VAE is used end-to-end without extra wiring.
- **Training is not affected.** `acestep/training_v2/` continues to
  load the bundled `<checkpoints>/vae/` directory. This integration is
  inference-only for now.
- **Quantized GGUF (`scragvae-BF16.gguf`) is not yet supported.**
  Loading will use the `safetensors` weights regardless. GGUF support
  is a separate feature.

## Adding a new community VAE

1. Confirm the VAE checkpoint contains `config.json` and
   `diffusion_pytorch_model.safetensors`, and that loading with
   `diffusers.AutoencoderOobleck.from_pretrained(...)` succeeds.
2. Add an entry to `VAE_REGISTRY` in `acestep/model_downloader.py`:
   ```python
   VAE_REGISTRY: Dict[str, str] = {
       "scragvae": "scragnog/Ace-Step-1.5-ScragVAE",
       "myvae": "<hf-org>/<repo-id>",
   }
   ```
3. (Optional) Add credit in this document and in the next release notes.

That's it — the dropdown, env var, downloader, and PyTorch/MLX
loaders all pick up the new entry automatically.

## Credits

ScragVAE is published under the MIT license by **@scragnog** and
explicitly credits ACE-Step as the base model.
