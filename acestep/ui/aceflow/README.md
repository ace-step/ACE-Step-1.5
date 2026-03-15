# AceFlow UI

A lightweight web UI for **ACE-Step** focused on practical music-generation workflows.

AceFlow does **not** replace ACE-Step and does **not** reimplement the generation engine.  
It is a workflow layer built on top of the ACE-Step backend and APIs: the UI collects inputs, the backend validates them, the queue runs the job, and ACE-Step does the actual generation.

---

## ✨ What AceFlow Is For

AceFlow exists to make the ACE-Step workflow easier to use from a browser.

It brings together the most useful controls in one place:

- multiple generation modes
- LoRA selection from a catalog
- DiT model selection
- reference audio upload
- chord progression tools
- chord-based reference rendering
- JSON import/export
- queue-based execution
- output, metadata, and log tracking

In plain English:

- **ACE-Step is the engine**
- **AceFlow is the dashboard**

---

## 🧭 How the UI Works

The runtime flow is simple:

1. You fill in the UI
2. AceFlow sends the request to the backend
3. The backend validates the payload
4. The request is added to the in-process queue
5. ACE-Step executes the job
6. Audio, metadata, and logs are written to disk
7. The frontend polls the job status and updates the page

Jobs are serialized through a queue, so AceFlow behaves more like a controlled remote frontend than a raw "run everything instantly" page.

---

## 🎛️ Generation Modes

AceFlow exposes four main workflows:

### Simple
A faster and lighter workflow for straightforward prompts.

### Custom
The most flexible mode. This is also the mode where full chord conditioning can inject generated harmonic reference as **audio codes**.

### Cover
Reference-based workflow. When full chord conditioning is used here, the generated harmonic reference is used as **reference WAV audio** rather than audio codes.

### Remix
A source-audio remix workflow. Upload source audio, then guide the remix with your caption and lyrics. Unlike Cover, Remix does not use manual audio-code conditioning.

AceFlow also exposes optional **Source start / Source end** controls for Remix so you can limit the source-audio window used by the request.

---

## 🔐 Optional Authentication

AceFlow supports optional user authentication controlled by environment variables.

### Enable or disable login

- `ACEFLOW_AUTH_ENABLED=1` → login is required
- `ACEFLOW_AUTH_ENABLED=0` → login is disabled, even if `_auth/users.json` and `_auth/access_log.jsonl` already exist

### Auth storage

When authentication is enabled, AceFlow stores auth data under:

    <results_root>/_auth/
    ├─ users.json
    └─ access_log.jsonl

### Auth behavior

- bootstrap admin creation is supported
- first-login password change is supported
- one active session per user is enforced
- session IP mismatch invalidates the session
- admin users can create and delete users
- deleting a user invalidates the deleted user's session and rewrites `users.json`
- access events are appended to `access_log.jsonl`

## 🎚️ DiT Model Behavior in the UI

AceFlow lets you choose the DiT model directly from the UI.

There are two distinct layers involved here:

### Frontend auto-fill and limits
When the model selector changes, AceFlow auto-fills some values for convenience:

- models whose name contains `turbo` → **Shift = 3**, **Inference steps = 8**, **UI max = 20**
- models whose name contains `sft` → **Shift = 1**, **Inference steps = 50**, **UI max = 200**
- other models → **Shift = 3**, **Inference steps = 20**, **UI max = 200**

This is only a UI helper so the form starts from sensible values, but the Turbo UI is intentionally capped at **20**.

### Backend fallback and clamp
When the request reaches the backend, `inference_steps` is normalized again. If the field is missing, backend fallbacks are:

- **8** for turbo models
- **50** for SFT models
- **32** for other non-turbo models

Then the backend clamps the final value to the allowed range used by AceFlow:

- **Turbo** → max **20**
- **Other models** → max **200**

So the frontend suggests defaults, while the backend remains the final safety layer.

---

## 🎸 LoRA Management

### Where to place LoRAs

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

Each LoRA must live inside `ACE-Step/lora`, and each subfolder name must match the matching catalog entry `id`.

### How the LoRA dropdown works

The UI loads LoRA entries from:

    aceflow/lora_catalog.json

Each entry uses a structure like this:

    {
      "id": "marcocoldplay",
      "trigger": "marcocoldplay",
      "label": "Coldplay"
    }

### Field meaning

- `id`  
  Internal identifier used by the backend. It must match the LoRA folder name inside `ACE-Step/lora`.

- `trigger`  
  Trigger or style token associated with that LoRA.

- `label`  
  Human-readable name shown in the UI.

### How to edit the LoRA catalog

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

### Practical behavior

- the UI supports a **single-LoRA workflow per job**
- if a LoRA is selected, the backend can also inject the LoRA trigger into the caption when needed
- if the selected folder does not exist under `ACE-Step/lora`, loading fails

---

## 🎼 Chord Progression Workflow

AceFlow includes a dedicated chord progression system.

This is not just decorative text glue. The chord section can turn a Roman-numeral progression into a real harmonic reference and then use that reference for generation conditioning.

### What you can define

The UI lets you work with:

- **Chord key**
- **Chord scale** (`major` or `minor`)
- **Roman progression**
- **Optional section map**

Example progression:

    I - vi - IV - V

Example section map:

    Verse=I - vi - IV - V
    Chorus=vi - IV - I - V
    Bridge=ii - IV - I - V

This allows different song sections to follow different harmonic patterns.

### What AceFlow does with it

The frontend and backend resolve Roman numerals into concrete chord names and can use them to:

- build harmonic hints for the caption
- inject chord hints into lyric sections
- optionally populate key/scale
- optionally align BPM-related conditioning
- generate a real reference WAV from the chord sequence
- optionally extract audio codes from that generated reference

So the chord system is useful in **two ways**:

1. as a **semantic harmonic hint layer**
2. as a **real conditioning source**

---

## 🎹 Chord Actions in the UI

The chord section includes multiple actions.

### Generate
Resolves the Roman progression into concrete chords and updates the preview.

### Auto Sections
Builds section-based overrides from the current lyrics structure when possible.

### Apply
Applies the chord setup as a lightweight harmonic layer to the related UI fields.

### Apply Full
This is the important one.

AceFlow generates a chord-based reference WAV, then uses it as conditioning:

- in **Custom** mode, the generated harmonic reference is converted into **audio codes**
- in **Cover** mode, the generated harmonic reference is used as **reference WAV audio**

### Remove
Clears chord-related UI state and removes the generated full-conditioning state.

---

## 🔊 SoundFont (`.sf2`) Support

AceFlow supports two renderers for chord/reference audio:

- **SoundFont (.sf2)**
- **Internal synth**

### Where to put the `.sf2`

If you want SoundFont-based chord/reference rendering, place **one optional General MIDI compatible `.sf2` file** in:

    aceflow/soundfonts/

There is also support for:

    aceflow/soundfont/

but `soundfonts/` is the intended location in this project.

### Why it goes there

The SoundFont lookup is resolved **relative to the AceFlow package directory**, not relative to the ACE-Step root.

That means the `.sf2` is part of the **AceFlow chord-reference renderer**, not part of ACE-Step core model loading.

### What happens if no `.sf2` is present

AceFlow automatically falls back to the internal synth renderer.

Behavior is:

- **0 `.sf2` files** → internal synth fallback
- **1 `.sf2` file** → that file is used
- **2 or more `.sf2` files** → the first alphabetical match is used

### Why use a SoundFont at all

The SoundFont renderer produces a more instrument-like harmonic reference before extraction or Cover conditioning. In practice, that can make the reference easier to hear and sometimes more useful than the built-in internal synth.

### Practical advice

Use a **small or medium General MIDI `.sf2`** with decent piano and bass sounds.

Do not go berserk with gigantic SoundFonts unless you have a real reason. Huge `.sf2` files can make chord reference rendering slower for very little practical gain.

---

## 🧪 Full Chord Conditioning Path

When full chord conditioning is used, the flow is:

1. define key, scale, and Roman progression
2. optionally define section overrides
3. resolve the chord plan
4. generate a temporary chord reference WAV
5. store that WAV in the upload area
6. optionally extract audio codes from it
7. inject the result into the selected generation mode

Behavior depends on the mode:

### In Custom mode
The generated chord reference WAV is converted into **audio codes** and used for conditioning.

### In Cover mode
The generated chord reference WAV is used directly as **reference audio**.

That distinction is important. Same progression, different routing.

---

## 📦 Output Folder Structure

By default, AceFlow writes everything under:

    <ACE-Step root>/aceflow_outputs

This default can be overridden through:

    ACESTEP_REMOTE_RESULTS_DIR

### Main folders inside `aceflow_outputs`

AceFlow creates and uses:

- per-job folders
- `_uploads/`
- `_logs/`
- `_songs_generated.json`

### Per-job folders

Each generation job gets its own folder named with a UUID-style job id.

Example shape:

    aceflow_outputs/
    ├─ 9b58b2d9-2f0e-4e0f-b7f3-2a1d2f6f8abc/
    │  └─ metadata.json
    ├─ _uploads/
    ├─ _logs/
    └─ _songs_generated.json

The exact generated audio files are associated with the job result and downloadable from the UI.

### Upload area

Uploaded audio files are stored in:

    aceflow_outputs/_uploads/

These files are saved with a generated safe name based on a UUID.

Chord full-conditioning also writes its generated temporary reference WAV here, using a name like:

    chord_reference_<timestamp>_<id>.wav

### Log area

Job logs are written under:

    aceflow_outputs/_logs/

### Counter file

AceFlow also stores a persistent generation counter in:

    aceflow_outputs/_songs_generated.json

---

## 🧾 Metadata and Log Generation

AceFlow writes structured metadata and captures runtime logs.

### `metadata.json`

Each job folder contains a:

    metadata.json

This file stores the core request and result information, including things like:

- selected model
- caption and lyrics
- generation mode
- LoRA information
- conditioning values
- chord-related state
- inference parameters
- result audio paths
- resolved seeds
- timing information

So `metadata.json` is the backend-side factual record of the job.

### Job log capture

When a job starts, AceFlow opens a temporary live capture file in `_logs` and tees into:

- loguru logs
- Python logging for uvicorn-related loggers
- `stdout`
- `stderr`

During execution, everything is captured into a temporary log file.

When the job ends, that temporary capture is copied into one or more final log files inside `_logs`.

Typical final naming is:

- `<audio_basename>_log.txt`
- or `<job_id>_log.txt` if no audio basename is available

Then the temporary live capture file is removed.

This is useful for debugging model routing, LoRA loading, conditioning, backend warnings, and the occasional machine-spirit tantrum.

---

## 🧹 Auto-Cleanup TTL

AceFlow cleanup is now controlled by the environment variable `ACEFLOW_CLEANUP_TTL_SECONDS`.

Default behavior:

- default value: `3600` seconds
- that means **60 minutes**
- `0` disables auto-cleanup completely

This cleanup covers:

- old per-job output folders
- old uploaded files in `_uploads`
- old log files in `_logs`

### Important behavior

This cleanup is **not** a separate daemon or scheduled background service.

It is triggered when a new generation request is submitted.

So the practical rule is:

- files older than the configured TTL are eligible for cleanup
- cleanup actually runs on the **next job submission**

### What gets deleted

- job directories older than the configured TTL, if they look like real AceFlow job folders
- uploaded audio files older than the configured TTL
- log files older than the configured TTL

### Examples

- `ACEFLOW_CLEANUP_TTL_SECONDS=3600` → keep current 60-minute behavior
- `ACEFLOW_CLEANUP_TTL_SECONDS=7200` → keep files for 2 hours
- `ACEFLOW_CLEANUP_TTL_SECONDS=0` → disable cleanup

### What this means in practice

AceFlow is intentionally not designed as a permanent archival system.

If you want to keep outputs, logs, or temporary uploads for longer, copy them somewhere else or raise the TTL. Tiny goblin with a configurable broom.

### Optional turbo clamp bypass from AceFlow only

AceFlow also supports an **optional runtime patch** for the core turbo DiT steps clamp:

- `ACEFLOW_BYPASS_CORE_TURBO_STEP_CLAMP=0` → default behavior, no bypass
- `ACEFLOW_BYPASS_CORE_TURBO_STEP_CLAMP=1` → AceFlow applies process-local runtime patches before handler creation

When enabled, AceFlow does two things for Turbo models:

1. it bypasses the core normalization clamp that would otherwise force `infer_steps` back to **8**
2. if Turbo is asked to use more than **8** steps and no explicit `timesteps` were supplied, AceFlow injects an explicit Turbo timestep schedule so the request actually runs with the requested step count

Important limits:

- this is still **AceFlow-only** and does **not** modify ACE-Step core files on disk
- Turbo remains capped to **20** steps in AceFlow
- the runtime patch is process-local and only affects the AceFlow process that started with the environment variable enabled

---

## 📤 JSON Export

AceFlow supports JSON export directly from the result player area.

Each generated result exposes a **Download JSON** action.

### What gets exported

The exported JSON is not just the raw backend `metadata.json`.

The frontend builds a **merged export** that can include:

- backend metadata
- the original request sent from the UI
- a frontend UI snapshot (`ui_state`)

That means the exported JSON is designed to be more useful for round-tripping back into the UI.

### File naming

Generated audio files use the backend-generated output name, typically something like:

    bba5aef8-43c6-5e1d-b736-c7b0db74550e.flac

When downloading the JSON export, AceFlow uses the same basename as the generated audio file and only changes the extension:

    bba5aef8-43c6-5e1d-b736-c7b0db74550e.json

---

## 📥 JSON Import

AceFlow also supports JSON import from the dedicated **Import JSON** section in the UI.

You can import either by:

- pasting JSON text
- selecting a `.json` file

### What import does

The importer tries to reconstruct UI state from multiple possible JSON shapes, including:

- exported merged JSONs from AceFlow
- backend metadata-style JSONs
- request/payload-centered JSONs

When successful, it restores the relevant UI fields such as:

- generation mode
- selected model
- caption and lyrics
- LoRA id and weight
- inference values
- conditioning values
- chord settings
- imported reference paths and chord-derived state

This makes it practical to reload a previous setup, tweak it, and run it again without manually rebuilding the whole prompt state by hand like a medieval scribe.

---

## 🧠 Prompt Examples

AceFlow can load example prompts from:

    aceflow/examples.json

This file powers the example / random-example workflow in the UI.

You can edit it to provide:

- internal presets
- preferred prompt starters
- demo examples
- house-style templates

So if you want the UI to stop suggesting generic stuff and start suggesting your own flavor of chaos, this is where you do it.

---

## ⚙️ Queue, Limits, and Practical Behavior

AceFlow uses an in-process single-worker queue.

That gives you:

- serialized execution
- predictable job tracking
- safer remote usage
- less chaos when multiple requests pile up

### Built-in limits visible in the code

Some relevant practical limits are:

- maximum duration: **600 seconds**
- minimum duration in the UI: **10 seconds**
- queue active cap: **30 jobs**
- basic per-IP request interval guard: **5 seconds**

So yes, it is a web UI, but it still keeps a club bouncer at the door.

---

## 📝 Notes

AceFlow is intentionally a UI/workflow layer, not a fork of ACE-Step internals.

If the page loads correctly but generation fails, the problem is usually in one of these areas:

- missing dependencies
- invalid model/config paths
- missing LoRA folders
- invalid reference audio paths
- no valid `.sf2` when SoundFont rendering is expected
- backend runtime issues
- GPU or memory problems

In other words:

- if the dashboard lights up, the UI is alive
- if the engine coughs blood, that is usually somewhere deeper

---

## License

Follow the same license and usage terms as the ACE-Step environment, models, LoRAs, and other assets used behind this UI.