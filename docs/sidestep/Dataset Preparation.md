# Dataset Preparation

Side-Step supports two ways to prepare your audio dataset for training: **folder-only mode** (zero configuration) and **JSON mode** (full metadata control).

Side-Step is **fully compatible** with ACE-Step's dataset JSON format. If you built your dataset using ACE-Step's Dataset Builder (Gradio UI), the resulting JSON works directly with Side-Step -- all fields are recognized.

Both modes produce the same preprocessed `.pt` tensors. The only difference is how much information you provide about each audio file.

---

## Supported Audio Formats

`.wav`, `.mp3`, `.flac`, `.ogg`, `.opus`, `.m4a`

Side-Step recursively scans directories, so you can organize files into subfolders.

---

## Folder-Only Mode (No JSON)

The simplest approach. Point Side-Step at a folder of audio files:

```bash
uv run train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --preprocess \
    --audio-dir ./my_audio \
    --tensor-output ./my_tensors
```

Side-Step auto-generates metadata for each file:

| Field | Auto-generated value |
| :--- | :--- |
| Caption | Filename with `_` and `-` replaced by spaces (e.g., `heavy_metal_riff.wav` becomes `heavy metal riff`) |
| Lyrics | `[Instrumental]` |
| Genre | *(empty)* |
| BPM / Key / Time Signature | `N/A` |
| Is Instrumental | `True` |

This is fine for quick experiments but you will get better training results by providing proper metadata.

---

## JSON Mode (Full Metadata)

Create a JSON file describing your dataset, then pass it alongside `--audio-dir`:

```bash
uv run train.py fixed \
    --checkpoint-dir ./checkpoints \
    --model-variant turbo \
    --preprocess \
    --audio-dir ./my_audio \
    --dataset-json ./my_dataset.json \
    --tensor-output ./my_tensors
```

### JSON Structure

Three formats are accepted:

**Array format** (simplest -- just a list of samples):

```json
[
  { "audio_path": "./song1.wav", "caption": "Upbeat pop track" },
  { "audio_path": "./song2.wav", "caption": "Slow jazz ballad" }
]
```

**Object format with samples only:**

```json
{
  "samples": [
    { "audio_path": "./song1.wav", "caption": "Upbeat pop track" },
    { "audio_path": "./song2.wav", "caption": "Slow jazz ballad" }
  ]
}
```

**Full ACE-Step format** (with dataset-level metadata -- this is what ACE-Step's Dataset Builder produces):

```json
{
  "metadata": {
    "name": "my_dataset",
    "custom_tag": "mytrigger",
    "tag_position": "prepend",
    "created_at": "2026-02-12T00:28:25.419505",
    "num_samples": 2,
    "all_instrumental": false,
    "genre_ratio": 90
  },
  "samples": [
    {
      "id": "00edb2c3",
      "audio_path": "./songs/track1.mp3",
      "filename": "track1.mp3",
      "caption": "An energetic rock track with electric guitar and driving drums",
      "genre": "Rock",
      "lyrics": "[Verse 1]\nRising up from the ashes tonight\n[Chorus]\nWe're on fire, burning bright",
      "raw_lyrics": "",
      "formatted_lyrics": "[Verse 1]\nRising up...",
      "bpm": 140,
      "keyscale": "E minor",
      "timesignature": "4",
      "duration": 180,
      "language": "en",
      "is_instrumental": false,
      "custom_tag": "mytrigger",
      "labeled": true,
      "prompt_override": null
    }
  ]
}
```

### Path Resolution

Relative paths in `audio_path` are resolved **from the JSON file's directory**, not from where you run the command. For example, if your JSON is at `./data/my_dataset.json` and contains `"audio_path": "./songs/track1.wav"`, Side-Step looks for `./data/songs/track1.wav`.

---

## Dataset-Level Metadata Block

When using the full ACE-Step format, the top-level `metadata` block controls dataset-wide behavior:

| Field | Default | Description |
| :--- | :--- | :--- |
| `name` | `"untitled_dataset"` | Dataset name (informational) |
| `custom_tag` | *(empty)* | Default trigger word applied to all samples that don't define their own `custom_tag` |
| `tag_position` | `"prepend"` | Where to place the `custom_tag` relative to the caption: `"prepend"`, `"append"`, or `"replace"` |
| `genre_ratio` | `0` | Percentage (0-100) of samples that use `genre` instead of `caption` as the text prompt. For example, `90` means 90% of samples use genre, 10% use caption |
| `all_instrumental` | `true` | Whether all tracks are instrumental (informational) |
| `created_at` | *(auto)* | Creation timestamp (informational) |
| `num_samples` | `0` | Sample count (informational) |

**How `genre_ratio` works:** At preprocessing time, Side-Step randomly selects the specified percentage of samples (seeded for reproducibility) and uses their `genre` field instead of `caption` for the text prompt. This adds variety to training -- the model learns to respond to both detailed captions and genre tags. With `genre_ratio=0` (default), all samples use caption. With `genre_ratio=90`, 90% use genre.

**How `custom_tag` works:** The dataset-level `custom_tag` is applied as a fallback to any sample that doesn't have its own. In ACE-Step's Dataset Builder, `set_custom_tag()` copies the tag to every sample, so typically all samples already have it. Side-Step respects both the per-sample and dataset-level values.

---

## Per-Sample Field Reference

| Field | Required | Default | Used by Side-Step | Description |
| :--- | :--- | :--- | :--- | :--- |
| `audio_path` | Yes* | -- | Yes | Path to the audio file. Relative paths resolve from the JSON file's directory |
| `filename` | Fallback* | -- | Yes | Alternative to `audio_path`. Also used as the metadata lookup key |
| `caption` | No | Derived from filename | Yes | Text description of the audio. Primary prompt text |
| `genre` | No | *(empty)* | Yes | Genre description (e.g., `"Rock"`, `"Electronic ambient"`). Used as prompt when `genre_ratio > 0` or `prompt_override = "genre"` |
| `lyrics` | No | `[Instrumental]` | Yes | Song lyrics with section markers (`[Verse]`, `[Chorus]`, etc.) |
| `bpm` | No | `N/A` | Yes | Beats per minute |
| `keyscale` | No | `N/A` | Yes | Musical key (e.g., `"C major"`, `"Bb minor"`) |
| `timesignature` | No | `N/A` | Yes | Time signature (e.g., `"4"`, `"4/4"`, `"3/4"`) |
| `duration` | No | `0` | Yes | Duration in seconds. Informational; actual duration comes from the audio file |
| `is_instrumental` | No | `True` | Yes | Whether the track is instrumental |
| `custom_tag` | No | *(from dataset metadata)* | Yes | Trigger word for this sample. Falls back to dataset-level `custom_tag` if empty |
| `prompt_override` | No | `null` | Yes | Per-sample override: `"caption"` or `"genre"`. Overrides `genre_ratio` for this sample |
| `id` | No | *(auto)* | Accepted | Sample identifier. Passed through in metadata |
| `raw_lyrics` | No | *(empty)* | Accepted | Original user-provided lyrics (pre-formatting). Passed through |
| `formatted_lyrics` | No | *(empty)* | Accepted | LM-formatted lyrics. Passed through |
| `language` | No | `"unknown"` | Accepted | Language code (e.g., `"en"`). Passed through |
| `labeled` | No | `false` | Accepted | Whether the sample has been labeled. Passed through |

\*At least one of `audio_path` or `filename` is required for Side-Step to find the audio file.

**"Accepted"** means Side-Step reads and preserves the field in preprocessed tensor metadata but does not use it to modify the training prompt. These fields exist for compatibility with ACE-Step's Dataset Builder.

---

## Custom Tags (Trigger Words)

The `custom_tag` field lets you train a LoRA that activates with a specific trigger word. For example:

```json
{
  "metadata": {
    "custom_tag": "myguitarstyle",
    "tag_position": "prepend"
  },
  "samples": [
    {
      "audio_path": "./guitar_solo_1.wav",
      "caption": "Electric guitar solo with heavy distortion",
      "custom_tag": "myguitarstyle"
    }
  ]
}
```

During training, the prompt becomes `"myguitarstyle, Electric guitar solo with heavy distortion"`. At inference time, include `myguitarstyle` in your prompt to activate the trained style.

The `tag_position` field controls placement:

- `"prepend"` (default): `"myguitarstyle, Electric guitar solo..."` -- tag comes first
- `"append"`: `"Electric guitar solo..., myguitarstyle"` -- tag comes last
- `"replace"`: `"myguitarstyle"` -- tag replaces the entire caption

---

## Complete Examples

### Minimal (two vocal tracks, array format)

```json
[
  {
    "audio_path": "./vocals/track1.wav",
    "caption": "Female vocals over acoustic guitar"
  },
  {
    "audio_path": "./vocals/track2.wav",
    "caption": "Male vocals with piano accompaniment"
  }
]
```

### Full ACE-Step format (as produced by the Dataset Builder)

```json
{
  "metadata": {
    "name": "my_artist_dataset",
    "custom_tag": "myartist",
    "tag_position": "prepend",
    "created_at": "2026-02-14T12:00:00.000000",
    "num_samples": 2,
    "all_instrumental": false,
    "genre_ratio": 90
  },
  "samples": [
    {
      "id": "a1b2c3d4",
      "audio_path": "./songs/energetic_rock.wav",
      "filename": "energetic_rock.wav",
      "caption": "Energetic rock track with electric guitar and driving drums",
      "genre": "Rock",
      "lyrics": "[Verse 1]\nRising up from the ashes tonight\n[Chorus]\nWe're on fire, burning bright",
      "raw_lyrics": "",
      "formatted_lyrics": "[Verse 1]\nRising up from the ashes tonight\n[Chorus]\nWe're on fire, burning bright",
      "bpm": 140,
      "keyscale": "E minor",
      "timesignature": "4",
      "duration": 180,
      "language": "en",
      "is_instrumental": false,
      "custom_tag": "myartist",
      "labeled": true,
      "prompt_override": null
    },
    {
      "id": "e5f6g7h8",
      "audio_path": "./songs/ambient_pad.wav",
      "filename": "ambient_pad.wav",
      "caption": "Ethereal ambient pad with slow evolving textures",
      "genre": "Ambient",
      "lyrics": "[Instrumental]",
      "raw_lyrics": "",
      "formatted_lyrics": "[Instrumental]",
      "bpm": 70,
      "keyscale": "C major",
      "timesignature": "4",
      "duration": 240,
      "language": "unknown",
      "is_instrumental": true,
      "custom_tag": "myartist",
      "labeled": true,
      "prompt_override": null
    }
  ]
}
```

With `genre_ratio: 90`, about 90% of these samples will use their `genre` field (e.g., "Rock", "Ambient") as the training prompt instead of the full `caption`. This matches ACE-Step's upstream behavior.

---

## Tips

- **Minimum dataset size:** 5+ audio files is recommended. Fewer samples may lead to overfitting (the model memorizes rather than generalizes).
- **Consistent quality:** Keep audio quality consistent across your dataset. Mixing high and low quality recordings confuses training.
- **Duration range:** Audio should be between 30 and 240 seconds. Longer files are truncated to `--max-duration` (default: 240s). Very short clips may not provide enough context.
- **Preprocessing is adapter-agnostic:** The same preprocessed tensors work for both LoRA and LoKR training. You only need to preprocess once.
- **Captions matter:** Descriptive captions give the model more to learn from. "Energetic rock with distorted guitars" is better than "song1".
- **Lyrics format:** Use section markers like `[Verse 1]`, `[Chorus]`, `[Bridge]` for structure. Use `[Instrumental]` for tracks without vocals.
- **Genre ratio:** If you have both `caption` and `genre` filled out, use `genre_ratio` to add prompt variety during training.
- **ACE-Step compatibility:** JSONs created by ACE-Step's Dataset Builder work directly. All fields are recognized.

---

## See Also

- [[Training Guide]] -- Full training walkthrough
- [[End-to-End Tutorial]] -- Step-by-step from raw audio to generation
- [[The Settings Wizard]] -- Wizard settings reference
