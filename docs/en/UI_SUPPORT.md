# UI Support Baseline

This document defines the current ACE-Step UI surface area before work begins on a new
beginner-friendly UI. It separates product UI, experimental UI, command-line workflows, and
API-only integration surfaces so future UI work can preserve capability coverage without keeping
multiple overlapping frontends alive.

## Support Boundary

| Surface | Entry point | Status | Notes |
|---------|-------------|--------|-------|
| Gradio Web UI | `acestep/acestep_v15_pipeline.py`, `acestep.ui.gradio` | Primary supported UI | Main interactive product surface for generation, editing, training, dataset building, model setup, help, and i18n. |
| Gradio-mounted REST API | `--enable-api`, `acestep/ui/gradio/api/api_routes.py` | Supported integration surface | Optional API routes hosted alongside Gradio. Keep behavior stable for local integrations. |
| Standalone REST API server | `acestep-api`, `acestep/api_server.py` | Supported API-only surface | Service/integration interface. Not a UI, but a likely backend dependency for future UIs. |
| OpenRouter-compatible API server | `acestep-openrouter`, `openrouter/openrouter_api_server.py` | Supported API-only surface | OpenAI/OpenRouter-compatible integration path. Not a UI. |
| Generation CLI | `cli.py`, `acestep` console script | Supported command-line workflow | Useful for scripting, configuration, and non-browser generation. Not a replacement for the web UI. |
| Side-Step training CLI/wizard | `train.py`, `acestep/training_v2/ui` | Supported or separately scoped training workflow | Rich terminal workflow for training. Do not remove until Gradio training parity and Side-Step ownership are explicitly reviewed. |
| Static Studio HTML UI | `ui/studio.html` | Removed | The experimental frontend-only prototype was removed to avoid duplicating product UI surface area before new UI work. |
| Streamlit UI | `acestep/ui/streamlit` | Removed | The experimental prototype was removed because it duplicated product UI responsibilities with its own model cache, navigation, settings, project storage, and docs. |

## Near-Term Cleanup Plan

1. Keep Gradio as the supported product UI while the next UI is designed.
2. Keep API servers as integration surfaces, not as UI cleanup targets.
3. Defer any CLI or Side-Step training wizard decisions until feature parity is reviewed.

## Gradio Feature Coverage Matrix

Any future UI should preserve the functional coverage below, even if it presents the workflow with
friendlier defaults and progressive disclosure.

| Area | Current capability | Current location | Audience tier | Future UI requirement |
|------|--------------------|------------------|---------------|-----------------------|
| Launch and runtime setup | Port, share, debug, server name, allowed paths, authentication | `acestep/acestep_v15_pipeline.py` | Admin | Preserve as launch/configuration options, not first-run clutter. |
| Hardware adaptation | GPU detection, VRAM tiers, duration/batch limits, LM defaults, offload defaults, quantization defaults | `acestep/acestep_v15_pipeline.py`, `acestep/gpu_config.py` | Beginner/Admin | Show a clear readiness summary and hide unsafe options by default. |
| Model initialization | DiT model selection, device, flash attention, compile, offload, quantization, download source | Gradio service configuration | Admin | Keep full control, but provide an obvious recommended path. |
| LM initialization | LM model selection, backend, init toggle, CPU offload | Gradio service configuration | Advanced/Admin | Explain optional vs required LM behavior in plain language. |
| LoRA inference | LoRA path, load/unload, use toggle | Gradio advanced settings | Advanced | Preserve adapter loading and clear compatibility warnings. |
| Simple generation | Natural-language song request, random sample, instrumental toggle, language hint, LM sample creation | Generation tab, Simple mode | Beginner | Make this the primary first-run path. |
| Custom generation | Caption, lyrics, reference audio, sample creation, caption/lyrics formatting | Generation tab, Custom mode | Beginner/Advanced | Keep manual control while guiding users through required inputs. |
| Remix | Source audio, target caption/lyrics, source codes, remix/code strength, no-FSQ option | Generation tab, Remix mode | Intermediate | Explain that Remix performs cover-style transformation. |
| Repaint | Source audio, time range, repaint mode, repaint strength, caption/lyrics | Generation tab, Repaint mode | Intermediate | Provide timeline-oriented controls when possible. |
| Extract | Source audio and target track selection | Generation tab, Extract mode | Advanced | Preserve base-model-only gating. |
| Lego | Source audio, target track, caption/lyrics | Generation tab, Lego mode | Advanced | Preserve base-model-only gating and track guidance. |
| Complete | Source audio, track selection, caption/lyrics | Generation tab, Complete mode | Advanced | Preserve base-model-only gating and arrangement-oriented help. |
| Audio codes | Source audio code extraction, code hints, transcription/analysis hooks | Generation tab source/code controls | Expert | Keep available behind an expert section. |
| Metadata controls | Duration, BPM, key/scale, time signature, vocal language, seed, inference steps | Generation tab optional controls | Beginner/Advanced | Offer auto defaults first, then explicit controls. |
| Diffusion controls | Guidance, shift, CFG interval, ADG, inference method, scheduler/timesteps, DCW | Advanced DiT settings | Expert | Keep out of the default path; preserve exact parameter access. |
| LM controls | Thinking, temperature, CFG scale, top-k, top-p, CoT toggles, constrained decoding | Advanced LM settings | Expert | Preserve with concise help and safe defaults. |
| Batch generation | Batch size, random seeds, explicit seed lists, background next-batch generation | Generation controls and results events | Advanced | Preserve efficient repeated generation and seed reproducibility. |
| Results playback | Up to eight audio slots, batch file download, status output | Results section | Beginner | Make listening, comparing, and saving simpler. |
| Result reuse | Send to Remix, send to Repaint, restore params to UI | Results section and event handlers | Intermediate | Preserve one-click iteration from a good result. |
| Result details | Audio codes, quality score, LRC generation, LRC save/download, generation metadata | Results details accordions | Advanced | Keep discoverable without overwhelming first-time users. |
| Dataset builder | Scan/load audio folder, preview samples, label/edit/save dataset metadata | Training tab dataset builder | Advanced | Preserve as a guided training preparation flow. |
| Dataset preprocessing | Tensor preprocessing and status updates | Training tab dataset builder | Advanced | Preserve clear status and failure recovery. |
| LoRA training | Dataset path, LoRA settings, run/stop training, logs, plots, export | Training tab LoRA | Advanced | Preserve complete Gradio training path. |
| LoKr training | Dataset path, LoKr settings, run/stop training, logs, export | Training tab LoKr | Expert | Preserve experimental/advanced positioning. |
| Help content | Inline help buttons, modal markdown, field tooltips | `acestep/ui/gradio/help_content.py`, i18n JSON | Beginner/Advanced | Expand into task-level help, examples, and recovery guidance. |
| i18n | English, Chinese, Japanese, Hebrew, Portuguese UI strings | `acestep/ui/gradio/i18n` | Beginner | Preserve language switching and avoid hard-coded UI text. |
| Service mode | Restricted UI defaults and hidden training tab | Gradio init params and interface composition | Admin | Preserve deployment-friendly mode. |
| API mode | Optional Gradio-hosted endpoints for health, models, release task, query result, sample creation, formatting | `acestep/ui/gradio/api/api_routes.py` | Integration | Preserve API behavior even if UI code changes. |

## Design Implications For The Next UI

- The first screen should prioritize one successful generation over exposing every parameter.
- Advanced controls should remain complete, but grouped by intent: model setup, song structure,
  generation quality, LM behavior, source audio editing, and expert code controls.
- Editing modes should be explained as user tasks rather than internal task names.
- Results should support an iteration loop: listen, compare, save, reuse settings, remix, repaint.
- Training should remain available, but separated from first-run generation.
- API services should remain framework-neutral so future UI experiments do not duplicate model
  loading, generation, dataset, or training logic.
