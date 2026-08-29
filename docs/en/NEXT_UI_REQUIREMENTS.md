# Next UI Requirements

This document defines product requirements and information architecture for a future
beginner-friendly ACE-Step UI. It is intentionally framework-neutral: implementation should not
begin until the supported workflows, feature parity expectations, and help model are agreed.

## Goals

- Help a new user generate a first useful song without understanding model internals.
- Preserve the full capability coverage documented in [UI Support Baseline](UI_SUPPORT.md).
- Keep expert controls available without making them part of the default path.
- Make model readiness, hardware limits, errors, and recovery steps understandable.
- Avoid reintroducing multiple competing product UIs.

## Non-Goals

- Do not replace the supported Gradio UI in this planning step.
- Do not choose a frontend framework in this document.
- Do not remove API, CLI, or Side-Step training workflows as part of new UI planning.
- Do not expose unfinished flows as default-ready user features.

## User Tiers

| Tier | User intent | UI posture |
|------|-------------|------------|
| Beginner | Generate a song from a plain-language idea. | Guided defaults, minimal required choices, clear examples. |
| Intermediate | Reuse a result, remix audio, repaint a section, control lyrics and structure. | Task-based flows with contextual controls. |
| Advanced | Tune metadata, seeds, batch generation, adapters, source audio, and training data. | Collapsible expert sections with safe defaults. |
| Expert | Control diffusion, LM behavior, audio codes, diagnostics, and edge workflows. | Complete access, but separated from beginner workflows. |
| Admin | Configure models, devices, service mode, auth, ports, API mode, storage, and paths. | Settings-focused interface with explicit risk warnings. |

## Primary Navigation

| Area | Purpose | Default audience |
|------|---------|------------------|
| Create | First-run and everyday text-to-music generation. | Beginner |
| Refine | Lyrics, metadata, seed, duration, language, and style iteration. | Beginner/Intermediate |
| Edit Audio | Remix, repaint, extract, lego, and complete workflows. | Intermediate/Advanced |
| Results | Listen, compare, save, download, restore params, score, LRC, and reuse outputs. | Beginner/Intermediate |
| Train | Dataset builder, preprocessing, LoRA, and LoKr training. | Advanced |
| Settings | Model readiness, hardware, API/service mode, auth, storage, and expert runtime options. | Admin |
| Help | Task guides, examples, glossary, troubleshooting, and recovery steps. | All users |

## First-Run Experience

The first screen should answer four questions before asking for creative input:

1. Is the required model available?
2. Is the current hardware ready?
3. What generation limits apply on this machine?
4. What is the simplest safe action the user can take next?

Requirements:

- Show a plain-language readiness state: ready, loading, needs download, needs setup, or unsupported.
- Explain whether the LM is optional, unavailable, or required for the selected action.
- Prefer recommended hardware/model defaults and hide risky overrides.
- Provide a single primary action, such as "Generate a Song", once the system is ready.
- Surface OOM risk before generation when duration, batch size, LM choice, or model choice is unsafe.

## Create Flow

The default generation flow should be:

1. Describe the song.
2. Choose vocals or instrumental.
3. Optionally add lyrics.
4. Pick duration with an auto-safe default.
5. Generate.
6. Listen, save, or refine.

Requirements:

- The caption field should support examples and structured suggestions.
- Lyrics should be optional and clearly separated from style description.
- Metadata should default to auto unless the user opens refinement controls.
- Simple mode should remain the default beginner path.
- Custom mode capabilities should be available without requiring users to know the word "Custom".

## Edit Audio Flow

Editing should be presented as user tasks instead of internal task names.

| User task | Current Gradio capability | UI requirement |
|-----------|---------------------------|----------------|
| Change the style of an existing song | Remix / cover | Explain structure preservation and strength. |
| Regenerate part of a song | Repaint | Provide clear start/end controls and recovery if the range is invalid. |
| Isolate an instrument or vocal | Extract | Gate by model support and explain source audio requirements. |
| Add an instrument layer | Lego | Gate by model support and show track choices clearly. |
| Complete a partial arrangement | Complete | Gate by model support and frame as arrangement completion. |

The UI should disable unsupported tasks for the loaded model while explaining which model family
enables them.

## Results Flow

Results should support iteration, not just playback.

Requirements:

- Show generated audio in a comparison-friendly layout.
- Keep batch navigation understandable when more than one batch exists.
- Make save/download actions obvious.
- Preserve restore-params, send-to-remix, and send-to-repaint actions.
- Keep scores, LRC, audio codes, and generation metadata discoverable in details.
- Clearly show seed and key generation parameters for reproducibility.

## Training Flow

Training should not be part of the beginner first screen, but it must remain available.

Requirements:

- Separate dataset preparation from training execution.
- Preserve dataset scan, preview, label, edit, save, and preprocessing steps.
- Preserve LoRA and LoKr training flows with clear experimental labeling for LoKr.
- Provide status, logs, and error recovery for missing files, invalid datasets, and interrupted runs.
- Avoid hiding training behind unrelated generation settings.

## Progressive Disclosure Rules

- Beginner default: idea, vocals/instrumental, lyrics, duration, generate.
- Refine: BPM, key, language, seed, batch size, audio format, metadata restore.
- Advanced: model choices, LoRA, reference audio, source audio, repaint/remix strength.
- Expert: audio codes, diffusion controls, LM controls, constrained decoding, DCW, timesteps.
- Admin: service mode, API mode, auth, ports, allowed paths, download source, hardware overrides.

Every advanced or expert section should include a short explanation of when to use it.

## Help And Recovery

Help content should be task-level, not only field-level.

Required help coverage:

- First generation walkthrough.
- Caption vs lyrics explanation.
- Instrumental and vocal-language guidance.
- Remix vs repaint distinction.
- Base-only mode explanation for Extract, Lego, and Complete.
- LoRA and LoKr training prerequisites.
- OOM recovery and safe hardware defaults.
- Missing model/download recovery.
- Invalid audio, invalid repaint range, and unsupported format recovery.
- Seed and reproducibility explanation.

## Implementation Constraints

- Preserve Gradio feature parity unless a feature is explicitly deprecated in a separate issue.
- Keep APIs framework-neutral so future UIs do not duplicate model loading or generation logic.
- Do not expose unfinished UI routes by default.
- Keep the supported Gradio UI stable while new UI work is experimental.
- Treat any reusable service extraction as a separate implementation PR.

