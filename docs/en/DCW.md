# Differential Correction in Wavelet Domain (DCW)

ACE-Step-1.5 supports an **opt-in sampler-side correction** from:

> **Elucidating the SNR-t Bias of Diffusion Probabilistic Models**
> Meng Yu, Lei Sun, Jianhao Zeng, Xiangxiang Chu, Kun Zhan. **CVPR 2026**.
> arXiv:[2604.16044](https://arxiv.org/abs/2604.16044) · Reference code: [AMAP-ML/DCW](https://github.com/AMAP-ML/DCW)

DCW is training-free, adds negligible compute, and has been validated across a
wide range of diffusion models — including **FLUX**, which shares ACE-Step's
flow-matching formulation.

## What it does

During **training**, every noised sample `x_t` has an SNR that is strictly
coupled to its timestep `t`. At **inference** the sampler steps through a
*predicted* trajectory, so the actual SNR of `x_t` drifts away from what the
network was trained to see at that `t`. This *SNR-t bias* accumulates along
the denoising chain and hurts quality — most visibly at intermediate / high
timesteps.

The authors' key observation is that diffusion models reconstruct
**low-frequency content before high-frequency content** during the reverse
process. Therefore the SNR-t drift affects different frequency bands
differently, and the correction should be applied **per-band** (wavelet
domain) rather than directly on the latent.

### Per-step update

Given the current latent `x`, velocity prediction `v`, and timestep `t_curr`:

```text
x_next   = sampler_step(x, v, t_curr)      # normal Euler / Heun / flow-matching
denoised = x - v * t_curr                  # predicted clean sample x_0

xL, xH   = DWT(x_next)
yL, yH   = DWT(denoised)

xL       = xL + λ_low  * (xL - yL)         # "low" mode   (Eq. 18 / 20)
xH[j]    = xH[j] + λ_high * (xH[j] - yH[j])  # "high" mode (Eq. 18 / 21)
x_next   = IDWT(xL, xH)
```

**Per-band schedule** (matches the paper's Eq. 20 / 21, following the
EDM reference in `AMAP-ML/DCW/generate.py`):

- `λ_low  = t_curr * dcw_scaler` — strongest at high noise / early
  steps, decays to 0 as `t → 0`.  Matches the intuition that low-frequency
  content is painted first in the reverse process.
- `λ_high = (1 − t_curr) * dcw_scaler` — **complementary** schedule,
  strongest at low noise / late steps when the network is actually
  painting high-frequency detail.
- `double` mode: low band uses `t_curr * dcw_scaler`, high band uses
  `(1 − t_curr) * dcw_high_scaler` independently.
- `pix` mode: raw `dcw_scaler` with no `t` modulation, matching the
  reference FLUX scheduler's pixel-space baseline.

ACE-Step latents are 1-D temporal tensors of shape `[B, T, 64]` at 25 Hz,
so DCW uses a 1-D DWT along the `T` axis.

## Installation

DCW's PyTorch-path wavelet transforms use `pytorch_wavelets` + `PyWavelets`.
Both are declared in `pyproject.toml`, so a normal `uv sync` already
installs them — nothing extra to do. On the MLX path, `haar` runs natively
in MLX (no Python wavelet deps needed); non-Haar bases bridge to the same
`pytorch_wavelets` modules.

If, for some reason, `pytorch_wavelets` is missing from the environment
when DCW is enabled, the pipeline logs a clear warning and falls back to
the normal sampler — no crash.

## Parameters

All DCW parameters live on `GenerationParams` in `acestep/inference.py` and
are forwarded through the generation handler chain into the base model's
`generate_audio`.

| Field | Type | Default | Description |
|---|---|---|---|
| `dcw_enabled` | `bool` | `True` | Master switch. Set to `False` for a clean A/B against the uncorrected sampler. |
| `dcw_mode` | `str` | `"double"` | One of `"low"`, `"high"`, `"double"`, `"pix"`. |
| `dcw_scaler` | `float` | `0.05` | Low-band correction strength (or the single scaler for `"high"` / `"pix"`). Usable range `0–0.1`. |
| `dcw_high_scaler` | `float` | `0.02` | High-band correction strength (used only when `dcw_mode == "double"`). Usable range `0–0.1`. |
| `dcw_wavelet` | `str` | `"haar"` | PyWavelets basis name — e.g. `"haar"`, `"db4"`, `"sym8"`. |

### Mode reference

- **`low`** — Correct only the low-frequency band.  Schedule
  `t_curr * dcw_scaler` — strongest at high noise, decays to 0 near
  `t=0`.  Matches the paper's `dcw_low` example and is the recommended
  starting point for ACE-Step.  (Note: the FLUX scheduler in
  AMAP-ML/DCW ships with `pix` as the *active* line and `dcw_low` /
  `dcw_high` commented out — so treat `low` as a sensible default, not
  a canonical one.)
- **`high`** — Correct only the high-frequency detail band.  Schedule
  `(1 - t_curr) * dcw_scaler` — **complementary** to `low`: near-zero
  at high noise, strongest as `t → 0`, because high-frequency content
  is painted later in the reverse process.
- **`double`** — Correct both bands, with independent `dcw_scaler`
  (applied to low with `t` schedule) and `dcw_high_scaler` (applied
  to high with `(1-t)` schedule).  ACE-Step extension; the reference
  implementation does not expose a separate high-band scaler.
- **`pix`** — No wavelet transform; correction is applied directly in
  latent space with the **raw** `dcw_scaler` (no `t` modulation),
  matching the reference FLUX scheduler.  Useful both as an ablation
  and as a "closest-to-reference" baseline.

## Usage example (Python API)

```python
from acestep.inference import GenerationConfig, GenerationParams, generate_music

# `dit_handler` and `llm_handler` come from the standard ACE-Step setup;
# see docs/en/INFERENCE.md for how they're constructed.

params = GenerationParams(
    caption="mellow lo-fi hiphop with jazzy piano",
    duration=30.0,
    inference_steps=32,
    guidance_scale=7.5,
    # Enable DCW:
    dcw_enabled=True,
    dcw_mode="double",
    dcw_scaler=0.05,
    dcw_high_scaler=0.02,
    dcw_wavelet="haar",
)
config = GenerationConfig(batch_size=1)
result = generate_music(
    dit_handler=dit_handler,
    llm_handler=llm_handler,
    params=params,
    config=config,
)
```

### Usage example (Gradio UI)

Open the standard Gradio UI, expand **Advanced DiT** → **🧪 DCW – Differential
Correction in Wavelet domain (experimental)**, and tune the four
sliders/dropdowns inside. **Enable DCW** is on by default with
`mode="double"` and `wavelet="haar"` — uncheck it to A/B against the
uncorrected sampler.  The default strengths follow the current Think state:
non-Think uses `scaler=0.05`, `high_scaler=0.02`, while Think uses
`scaler=0.02`, `high_scaler=0.06`.

## Recommended starting values

The defaults come from a grid search on the pure-DiT path (no LLM
think-CoT): `dcw_mode="double"`, `dcw_scaler=0.05`,
`dcw_high_scaler=0.02`, `dcw_wavelet="haar"`.  In LLM-think mode the
overall DCW gain is small and the optimum band drifts slightly, so Gradio
switches to `dcw_scaler=0.02` and `dcw_high_scaler=0.06` when Think is
enabled.  Direct Python callers can override these values on
`GenerationParams`; the HTTP generation routes currently use the
`GenerationParams` defaults and do not expose per-request `dcw_*` fields.

- `"low"` alone (`dcw_scaler=0.02`) is a safer, more conservative
  setting if `"double"` sounds too aggressive for a given track.
- Usable scaler range is `0–0.1`; going above that tends to introduce
  audible artefacts.
- Try different wavelet bases (`db4`, `sym8`) for smoother low-band
  extraction; `haar` is the default and fastest, with a blocky low-pass
  response.

## Scope

DCW is wired into every ACE-Step sampler path:

- **PyTorch**: `base`, `sft`, `turbo`, `xl_base`, `xl_sft`, `xl_turbo`.
- **MLX** (Apple Silicon): native Haar plus a `pytorch_wavelets` bridge
  for non-Haar bases — same `dcw_*` kwargs produce the same output.
- **Gradio UI**: all four controls live under **Advanced DiT → 🧪 DCW**.

## Citation

```bibtex
@article{yu2026eluci,
  title   = {Elucidating the SNR-t Bias of Diffusion Probabilistic Models},
  author  = {Meng Yu and Lei Sun and Jianhao Zeng and Xiangxiang Chu and Kun Zhan},
  journal = {arXiv preprint arXiv:2604.16044},
  year    = {2026}
}
```
