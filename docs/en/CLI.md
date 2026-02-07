# ACE-Step 1.5 CLI Guide

This guide explains how to use `cli.py`, the interactive wizard and config-driven CLI for ACE-Step 1.5 inference. It also documents all configuration parameters and how they map to tasks.

The CLI is **wizard/config only**: you either run the wizard to build a config, or load a `.toml` config and generate. There are no direct task flags besides `--config` and `--configure`.

---

## Quick Start

Generate via wizard (interactive):

```bash
python cli.py
```

Create or edit a config without generating:

```bash
python cli.py --configure
python cli.py --configure --config configs/my_run.toml
```

Generate from a saved config:

```bash
python cli.py --config configs/my_run.toml
```

---

## Wizard Flow

1. Choose one of 6 tasks.
2. Provide required parameters for that task.
3. Choose lyrics mode (instrumental / auto / file / paste).
4. Choose whether to configure advanced parameters.
5. Review summary and confirm generation.
6. Save configuration to a `.toml` file.

If you skip advanced parameters, the wizard fills **all optional parameters** with defaults from `GenerationParams` and `GenerationConfig`.

---

## Configure Mode (`--configure`)

`--configure` runs the wizard **without generation** and always saves a config.

Behavior:
- If `--config` is provided, the file is loaded and used as the wizard’s starting values.
- After the wizard, you choose a filename to save (overwriting or new).
- The program exits without generation.

---

## Task Types

ACE-Step supports 6 tasks, aligned with `docs/en/INFERENCE.md`.

1. **Text2Music** (`text2music`)
   - Generate from text/lyrics.
2. **Cover** (`cover`)
   - Transform existing audio to a new style.
3. **Repaint** (`repaint`)
   - Regenerate a time segment of existing audio.
4. **Lego** (`lego`) **Base model only**
   - Generate a specific instrument track in context.
5. **Extract** (`extract`) **Base model only**
   - Extract a specific instrument track from a mix.
6. **Complete** (`complete`) **Base model only**
   - Complete/extend partial tracks with specified instruments.

Base-model-only tasks require a base model config (e.g., `acestep-v15-base`).

---

## Configuration File (`.toml`)

The wizard saves a `.toml` file containing all parameters. These keys map directly to the fields used in `cli.py`.

When you load a config with `--config`, all keys are applied to the runtime settings.

---

## Parameters Reference

Below is a complete list of parameters supported in the config/wizard, with descriptions and defaults. Defaults are the values used by `GenerationParams` and `GenerationConfig`, or auto-detected hardware defaults where noted.

### Core / Runtime

- `project_root` (str, default `"."`)
  - Project root path.
- `config_path` (str, default `None`)
  - DiT model config name or path (e.g., `acestep-v15-turbo`, `acestep-v15-base`).
  - If not set, the CLI auto-selects an available model.
- `checkpoint_dir` (str, default `"checkpoints"`)
  - Directory containing model checkpoints.
- `lm_model_path` (str, default `None`)
  - 5Hz LM model name/path. If not set and `thinking=True`, auto-selects the first available LM.
- `backend` (str, default `"vllm"`)
  - LM backend: `"vllm"` or `"pt"`.
- `device` (str, default `"auto"`)
  - `"auto"`, `"cuda"`, `"mps"`, `"xpu"`, `"cpu"`.
- `use_flash_attention` (bool, default `None`)
  - If `None`, auto-detects.
- `offload_to_cpu` (bool, default auto based on GPU memory)
  - Automatically enabled when GPU VRAM < 16GB.
- `offload_dit_to_cpu` (bool, default `False`)
  - Offload DiT model to CPU.
- `save_dir` (str, default `"output"`)
  - Output directory for generated audio.
- `audio_format` (str, default `"flac"`)
  - `"mp3"`, `"wav"`, or `"flac"`.

### Task Selection

- `task_type` (str, default `"text2music"`)
  - One of: `text2music`, `cover`, `repaint`, `lego`, `extract`, `complete`.
- `instruction` (str, default default DiT instruction)
  - Task instruction. Auto-generated for `lego`, `extract`, `complete` when not provided.
- `reference_audio` (str, default `None`)
  - Optional reference audio for certain tasks.
- `src_audio` (str, default `None`)
  - Source audio file path (required for `cover`, `repaint`, `lego`, `extract`, `complete`).
- `audio_codes` (str, default `""`)
  - Pre-extracted 5Hz semantic codes (advanced).

### Text Inputs

- `caption` (str, default `""`)
  - Music description prompt.
  - Required for `cover`, `repaint`, `lego`, `complete`.
  - For `text2music`, either `caption` or `lyrics` is required.
- `lyrics` (str or path, default `None`)
  - Lyrics text or path to a `.txt` file.
- `instrumental` (bool, default `False`)
  - If true, uses `"[Instrumental]"`.

### Music Metadata

- `bpm` (int, default `None`)
  - Beats per minute. If `None`, LM auto-detects when enabled.
- `keyscale` (str, default `""`)
  - Musical key/scale (e.g., `"C Major"`).
- `timesignature` (str, default `""`)
  - Time signature (e.g., `"4/4"`).
- `vocal_language` (str, default `"unknown"`)
  - ISO 639-1 code or `"unknown"` for auto-detect.
- `duration` (float, default `-1.0`)
  - Target length in seconds. If <= 0, model auto-chooses.

### Task-Specific Parameters

- `repainting_start` (float, default `0.0`)
  - Repaint start time in seconds.
- `repainting_end` (float, default `-1`)
  - Repaint end time in seconds (`-1` = end of audio).
- `audio_cover_strength` (float, default `1.0`)
  - Cover strength from 0.0 to 1.0.
- `lego_track` (str, default `""`)
  - Track to generate (e.g., `guitar`, `drums`).
- `extract_track` (str, default `""`)
  - Track to extract.
- `complete_tracks` (str, default `""`)
  - Comma-separated tracks to complete (e.g., `"drums,bass,guitar"`).

Available tracks for `lego` / `extract` / `complete`:
`vocals`, `backing_vocals`, `drums`, `bass`, `guitar`, `keyboard`, `percussion`,
`strings`, `synth`, `fx`, `brass`, `woodwinds`.

### DiT Inference Parameters

- `inference_steps` (int, default `8`)
  - Number of denoising steps.
- `seed` (int, default `-1`)
  - `-1` for random, otherwise fixed seed.
- `guidance_scale` (float, default `7.0`)
  - CFG scale (primarily for base model).
- `use_adg` (bool, default `False`)
  - Adaptive Dual Guidance (base model only).
- `cfg_interval_start` (float, default `0.0`)
  - CFG start ratio (0.0–1.0).
- `cfg_interval_end` (float, default `1.0`)
  - CFG end ratio (0.0–1.0).
- `shift` (float, default `1.0`)
  - Timestep shift factor (1.0–5.0).
- `infer_method` (str, default `"ode"`)
  - `"ode"` or `"sde"`.
- `timesteps` (list of float or string, default `None`)
  - Custom timesteps list (overrides `inference_steps`).

### 5Hz LM Parameters

- `thinking` (bool, default auto based on GPU)
  - Enable LM reasoning and semantic code generation.
- `lm_temperature` (float, default `0.85`)
  - LM sampling temperature.
- `lm_cfg_scale` (float, default `2.0`)
  - LM CFG scale.
- `lm_top_k` (int, default `0`)
  - Top-k sampling (0 disables).
- `lm_top_p` (float, default `0.9`)
  - Nucleus sampling.
- `lm_negative_prompt` (str, default `"NO USER INPUT"`)
  - LM negative prompt.
- `use_cot_metas` (bool, default `True`)
  - Use LM CoT for metadata.
- `use_cot_caption` (bool, default `True`)
  - Use LM CoT to refine caption.
- `use_cot_lyrics` (bool, default `False`)
  - Auto-generate lyrics (wizard also supports this).
- `use_cot_language` (bool, default `True`)
  - Use LM to detect vocal language.
- `use_constrained_decoding` (bool, default `True`)
  - Structured decoding for LM.

### Batch / Output Parameters

- `batch_size` (int, default `2`)
  - Number of audio variations.
- `seeds` (list[int] or `None`, default `None`)
  - Optional fixed seeds (overrides `batch_size` and random seed usage).
- `use_random_seed` (bool, default `True`)
  - If `False`, uses provided seeds.
- `allow_lm_batch` (bool, default `False`)
  - Allow LM batching when `thinking=True`.
- `lm_batch_chunk_size` (int, default `8`)
  - Max LM batch size per chunk.
- `constrained_decoding_debug` (bool, default `False`)
  - LM constrained decoding debug logs.

---

## Required Parameters by Task

**text2music**
- Required: `caption` or `lyrics`.

**cover**
- Required: `src_audio`, `caption`.

**repaint**
- Required: `src_audio`, `caption`, `repainting_start`, `repainting_end`.

**lego** (base model only)
- Required: `src_audio`, `instruction` or `lego_track`, `caption`.

**extract** (base model only)
- Required: `src_audio`, `instruction` or `extract_track`.

**complete** (base model only)
- Required: `src_audio`, `instruction` or `complete_tracks`, `caption`.

---

## Notes

- If `use_cot_lyrics=True`, the CLI uses `create_sample()` to auto-generate lyrics and metadata.
- When `timesteps` are provided, they override `inference_steps` and `shift`.
- For base-only tasks, `config_path` must include `"base"` (e.g., `acestep-v15-base`).
- When `seeds` is set, `batch_size` is set to the number of seeds and `use_random_seed` is forced to `False`.
