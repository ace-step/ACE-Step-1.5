# AceFlow UI

AceFlow is a lightweight web UI built on top of the **ACE-Step** backend.

It does not replace ACE-Step and does not reimplement the generation engine.  
Its job is to provide a cleaner interface for the most useful workflows exposed by the backend, including generation modes, LoRA selection, queue-based execution, reference conditioning, and chord-driven harmonic setup.

---

## What AceFlow Does

AceFlow is a thin UI layer that sits in front of ACE-Step.

In practice, the workflow is:

1. the browser collects the user inputs
2. the frontend sends the request to the backend
3. the backend validates the payload
4. the request is added to the queue
5. ACE-Step performs the actual generation
6. outputs, logs, and metadata are saved
7. the UI polls job status and updates the page

So the split is simple:

- **ACE-Step** does the generation
- **AceFlow** manages the workflow

---

## Main Features

AceFlow exposes the most practical generation controls through a web interface.

Main features include:

- **Simple, Custom, Cover and Remix workflows**
- **LoRA selection from a UI catalog**
- **Chord progression tools**
- **Reference audio generation from chords**
- **Audio-code extraction from generated chord references**
- **Queue-based job execution**
- **Prompt example loading**
- **Output and metadata tracking**

---

## Generation Modes

AceFlow supports multiple workflows directly from the UI.

### Simple

A quick workflow for straightforward generation.

### Custom

The most flexible mode.  
This is also the mode where full chord conditioning can inject generated harmonic reference as **audio codes**.

### Cover

Reference-based workflow.  
When full chord conditioning is used in Cover mode, the generated harmonic reference is used as **reference WAV audio**, not as audio codes.

### Remix

A variation workflow for transforming or reworking existing material.

---

## LoRA Management

### Where to Place LoRAs

The `lora` folder must be created in the **root of ACE-Step**.

Example:

    ACE-Step/
    ├─ lora/
    │  ├─ marcocoldplay/
    │  ├─ marcojmj/
    │  └─ marcomj/
    ├─ models/
    ├─ outputs/
    └─ ...

Each LoRA must live inside `ACE-Step/lora`, and each subfolder name must match the corresponding catalog entry `id`.

### How the LoRA Dropdown Works

The UI loads the available LoRAs from:

    aceflow/lora_catalog.json

Each entry uses this structure:

    {
      "id": "marcocoldplay",
      "trigger": "marcocoldplay",
      "label": "Coldplay"
    }

### Field Meaning

- `id`  
  Internal identifier used by the backend.  
  This must match the LoRA folder name inside `ACE-Step/lora`.

- `trigger`  
  Trigger or style token associated with that LoRA.

- `label`  
  Human-readable name shown in the UI.

### How to Edit the LoRA Catalog

Open:

    aceflow/lora_catalog.json

Then add, edit, or remove entries.

Example:

    [
      {
        "id": "",
        "trigger": "",
        "label": "(No LoRA)"
      },
      {
        "id": "my-lora-style",
        "trigger": "my-lora-style",
        "label": "My LoRA Style"
      }
    ]

### Important Notes About LoRAs

- the `id` must exactly match the folder name under `ACE-Step/lora`
- if the selected LoRA folder does not exist, loading fails
- the UI is built around a single-LoRA workflow per job
- the backend also injects the LoRA trigger into the caption when needed

---

## Chord Progression System

AceFlow includes a dedicated chord progression workflow.

This is not just a text helper: the UI can turn a Roman-numeral progression into an actual harmonic reference that can then be used for conditioning.

The chord tools are exposed in the **Chord progression** section of the UI.

### What You Can Enter

The UI lets you define:

- **Chord key**
- **Chord scale** (`major` or `minor`)
- **Roman progression**
- **Optional section map**

Example Roman progression:

    I - vi - IV - V

Example section map:

    Verse=I - vi - IV - V
    Chorus=vi - IV - I - V

This means different lyrics sections can use different harmonic progressions.

### What AceFlow Does With It

The frontend and backend resolve Roman numerals into chord names and use that information in several ways:

- build a harmonic description for the caption
- inject chord hints into lyrics sections
- optionally set key/scale information
- optionally align BPM-related conditioning
- generate an actual reference WAV from the chord sequence
- optionally extract audio codes from that generated reference

This makes the chord workflow useful both as a **semantic hint layer** and as a **real conditioning source**.

---

## Chord Progression Actions

The chord section includes several actions.

### Generate

Resolves the Roman progression into concrete chord names and updates the preview.

### Auto Sections

Builds section-based overrides from the current lyrics structure when possible.

### Apply

Applies the chord setup as a clean harmonic layer to style, lyrics, key and BPM fields.

This is the lightweight harmonic workflow.

### Apply Full

This is the important one.

AceFlow generates a chord-based reference audio file, then uses it as conditioning:

- in **Custom** mode, the generated harmonic reference is converted into **audio codes**
- in **Cover** mode, the generated harmonic reference is used as **pure WAV reference audio**

That is the full harmonic conditioning path.

### Remove

Clears the chord setup from the related UI fields and conditioning state.

---

## Chord Reference Rendering

When full chord conditioning is used, AceFlow generates a temporary reference WAV from the resolved chord progression.

The backend route responsible for this is the chord reference renderer, which creates a WAV file and stores it under the upload area before optional code extraction.

The rendering pipeline supports two modes:

- **SoundFont (.sf2) renderer**
- **Internal synth renderer**

---

## Where to Put the `.sf2` SoundFont

If you want chord/reference audio to be rendered with a SoundFont instrument, place **one optional General MIDI compatible `.sf2` file** in:

    aceflow/soundfonts/

There is also support for:

    aceflow/soundfont/

But the packaged project already includes the `soundfonts` folder, so that is the intended location.

### Why the `.sf2` Goes There

AceFlow searches for SoundFonts relative to the **aceflow package directory**, not relative to the ACE-Step root.

In code terms, the SoundFont lookup starts from the folder where the AceFlow Python package lives and scans:

- `soundfonts`
- `soundfont`

So the `.sf2` belongs inside the AceFlow package because it is used by the **AceFlow chord reference renderer**, not by ACE-Step’s core model loader.

### What Happens If No `.sf2` Is Present

If no compatible `.sf2` file is found, AceFlow automatically falls back to the built-in internal chord renderer.

So:

- **0 `.sf2` files** -> internal renderer fallback
- **1 `.sf2` file** -> that file is used
- **2 or more `.sf2` files** -> the first alphabetical match is used

### Why Use an `.sf2` At All

The SoundFont renderer produces a more instrument-like harmonic reference before extraction or conditioning.

By default, AceFlow uses a simple setup based on:

- piano layer
- bass layer

This gives a cleaner musical reference than the internal synth in some cases, especially when you want a more recognisable harmonic guide for extraction or Cover conditioning.

### Practical Advice for the SoundFont

Use a **small or medium General MIDI `.sf2`** with decent piano and bass sounds.

Do not go wild with giant SoundFonts unless there is a real reason. Huge `.sf2` files tend to make rendering slower with very little practical benefit for this workflow.

---

## Chord Reference Renderer Selection

The UI exposes a renderer selector for chord/reference audio.

Available choices are:

- **SoundFont (.sf2)**
- **Internal synth**

If a valid `.sf2` is detected in `aceflow/soundfonts`, the SoundFont option is available and the UI can also show its name.

If no `.sf2` is found, the UI falls back to the internal renderer.

---

## How Full Chord Conditioning Works

The full harmonic workflow is:

1. define the Roman progression
2. optionally define section overrides
3. resolve the chord plan
4. generate a temporary reference WAV from the chord sequence
5. upload/store that generated WAV
6. optionally extract audio codes from it
7. inject the result into the active generation mode

Behavior depends on the selected mode:

### In Custom Mode

The generated chord reference WAV is converted into **audio codes** and those codes are used for conditioning.

### In Cover Mode

The generated chord reference WAV is used directly as **reference audio**.

This distinction matters because the UI is not doing the same thing in both modes, even if the starting chord progression is identical.

---

## Chord Section Mapping

AceFlow supports optional per-section chord overrides.

This allows lyrics sections such as Verse, Chorus, Bridge, Outro and similar blocks to follow different progressions.

Example:

    Verse=I - vi - IV - V
    Chorus=vi - IV - I - V
    Bridge=ii - IV - I - V

When section rules are present, matching lyrics sections use their own progression instead of the global one.

This is especially useful for more structured songs where a single repeating loop would be too crude.

---

## Examples Catalog

AceFlow can load prompt examples from:

    aceflow/examples.json

This file is meant to provide ready-made examples or preset ideas in the UI.

You can edit it to add your own internal prompt templates or preferred starting points.

---

## Queue and Job System

AceFlow uses a queued job system instead of running every request directly in the HTTP request thread.

This improves:

- stability
- multi-job handling
- remote use
- status tracking

Each request becomes a job, gets processed by the backend, and then reports its outputs back to the UI.

---

## Outputs

Generated results are written to the configured output area.

Typical saved data includes:

- generated audio
- metadata
- logs
- request snapshot information

This makes debugging and reproducibility easier.

For chord full-conditioning, the generated temporary reference WAV is also created during the workflow and used before the final generation step.

---

## Editing Summary

### To add a new LoRA

1. create or copy the LoRA folder into `ACE-Step/lora`
2. add the matching entry in `aceflow/lora_catalog.json`

### To use SoundFont-based chord rendering

1. place one compatible `.sf2` file into `aceflow/soundfonts`
2. use the chord/reference renderer selector in the UI
3. choose **SoundFont (.sf2)**

### To use chord full conditioning

1. define key, scale and Roman progression
2. optionally define section overrides
3. click the full chord apply action
4. let AceFlow generate the harmonic reference
5. let the backend extract audio codes when needed
6. run generation in the selected mode

### To edit example presets

1. update `aceflow/examples.json`

---

## Notes

AceFlow is intentionally a UI and workflow layer, not a fork of ACE-Step internals.

If the UI loads correctly but generation fails, the issue is usually in the backend environment, configuration, model paths, runtime state, or missing assets.

Typical causes include:

- missing dependencies
- invalid paths
- missing LoRA folders
- missing or invalid reference files
- no valid `.sf2` file when SoundFont rendering is expected
- runtime or GPU issues

In other words:

- AceFlow is the dashboard
- ACE-Step is the engine

---

## License

Follow the same license and usage terms as the ACE-Step environment, models, LoRAs, and assets used behind this UI.