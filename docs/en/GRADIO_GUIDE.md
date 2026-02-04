# ACE-Step Gradio Demo User Guide

**Language / 语言 / 言語:** [English](GRADIO_GUIDE.md) | [中文](../zh/GRADIO_GUIDE.md) | [日本語](../ja/GRADIO_GUIDE.md)

---

This guide provides comprehensive documentation for using the ACE-Step Gradio web interface for music generation, including all features and settings.

## Table of Contents

- [Getting Started](#getting-started)
- [Service Configuration](#service-configuration)
- [Generation Modes](#generation-modes)
- [Task Types](#task-types)
- [Input Parameters](#input-parameters)
- [Advanced Settings](#advanced-settings)
- [Results Section](#results-section)
- [LoRA Training](#lora-training)
- [Tips and Best Practices](#tips-and-best-practices)

---

## Getting Started

### Launching the Demo

```bash
# Basic launch
python app.py

# With pre-initialization
python app.py --config acestep-v15-turbo --init-llm

# With specific port
python app.py --port 7860
```

### Interface Overview

The Gradio interface consists of several main sections:

1. **Service Configuration** - Model loading and initialization
2. **Required Inputs** - Task type, audio uploads, and generation mode
3. **Music Caption & Lyrics** - Text inputs for generation
4. **Optional Parameters** - Metadata like BPM, key, duration
5. **Advanced Settings** - Fine-grained control over generation
6. **Results** - Generated audio playback and management

---

## Service Configuration

### Model Selection

| Setting | Description |
|---------|-------------|
| **Checkpoint File** | Select a trained model checkpoint (if available) |
| **Main Model Path** | Choose the DiT model configuration (e.g., `acestep-v15-turbo`, `acestep-v15-turbo-shift3`) |
| **Device** | Processing device: `auto` (recommended), `cuda`, `mps`, or `cpu` |

### 5Hz LM Configuration

| Setting | Description |
|---------|-------------|
| **5Hz LM Model Path** | Select the language model (e.g., `acestep-5Hz-lm-0.6B`, `acestep-5Hz-lm-1.7B`) |
| **5Hz LM Backend** | `vllm` (faster, recommended) or `pt` (PyTorch, more compatible) |
| **Initialize 5Hz LM** | Check to load the LM during initialization (required for thinking mode) |

### Performance Options

| Setting | Description |
|---------|-------------|
| **Use Flash Attention** | Enable for faster inference (requires flash_attn package) |
| **Offload to CPU** | Offload models to CPU when idle to save GPU memory |
| **Offload DiT to CPU** | Specifically offload the DiT model to CPU |

### LoRA Adapter

| Setting | Description |
|---------|-------------|
| **LoRA Path** | Path to trained LoRA adapter directory |
| **Load LoRA** | Load the specified LoRA adapter |
| **Unload** | Remove the currently loaded LoRA |
| **Use LoRA** | Enable/disable the loaded LoRA for inference |

### Initialization

Click **Initialize Service** to load the models. The status box will show progress and confirmation.

---

## Generation Modes

### Simple Mode

Simple mode is designed for quick, natural language-based music generation.

**How to use:**
1. Select "Simple" in the Generation Mode radio button
2. Enter a natural language description in the "Song Description" field
3. Optionally check "Instrumental" if you don't want vocals
4. Optionally select a preferred vocal language
5. Click **Create Sample** to generate caption, lyrics, and metadata
6. Review the generated content in the expanded sections
7. Click **Generate Music** to create the audio

**Example descriptions:**
- "a soft Bengali love song for a quiet evening"
- "upbeat electronic dance music with heavy bass drops"
- "melancholic indie folk with acoustic guitar"
- "jazz trio playing in a smoky bar"

**Random Sample:** Click the 🎲 button to load a random example description.

### Custom Mode

Custom mode provides full control over all generation parameters.

**How to use:**
1. Select "Custom" in the Generation Mode radio button
2. Manually fill in the Caption and Lyrics fields
3. Set optional metadata (BPM, Key, Duration, etc.)
4. Optionally click **Format** to enhance your input using the LM
5. Configure advanced settings as needed
6. Click **Generate Music** to create the audio

---

## Task Types

### text2music (Default)

Generate music from text descriptions and/or lyrics.

**Use case:** Creating new music from scratch based on prompts.

**Required inputs:** Caption or Lyrics (at least one)

### cover

Transform existing audio while maintaining structure but changing style.

**Use case:** Creating cover versions in different styles.

**Required inputs:**
- Source Audio (upload in Audio Uploads section)
- Caption describing the target style

**Key parameter:** `Audio Cover Strength` (0.0-1.0)
- Higher values maintain more of the original structure
- Lower values allow more creative freedom

### repaint

Regenerate a specific time segment of audio.

**Use case:** Fixing or modifying specific sections of generated music.

**Required inputs:**
- Source Audio
- Repainting Start (seconds)
- Repainting End (seconds, -1 for end of file)
- Caption describing the desired content

### lego (Base Model Only)

Generate a specific instrument track in context of existing audio.

**Use case:** Adding instrument layers to backing tracks.

**Required inputs:**
- Source Audio
- Track Name (select from dropdown)
- Caption describing the track characteristics

**Available tracks:** vocals, backing_vocals, drums, bass, guitar, keyboard, percussion, strings, synth, fx, brass, woodwinds

### extract (Base Model Only)

Extract/isolate a specific instrument track from mixed audio.

**Use case:** Stem separation, isolating instruments.

**Required inputs:**
- Source Audio
- Track Name to extract

### complete (Base Model Only)

Complete partial tracks with specified instruments.

**Use case:** Auto-arranging incomplete compositions.

**Required inputs:**
- Source Audio
- Track Names (multiple selection)
- Caption describing the desired style

---

## Input Parameters

### Required Inputs

#### Task Type
Select the generation task from the dropdown. The instruction field updates automatically based on the selected task.

#### Audio Uploads

| Field | Description |
|-------|-------------|
| **Reference Audio** | Optional audio for style reference |
| **Source Audio** | Required for cover, repaint, lego, extract, complete tasks |
| **Convert to Codes** | Extract 5Hz semantic codes from source audio |

#### LM Codes Hints

Pre-computed audio semantic codes can be pasted here to guide generation. Use the **Transcribe** button to analyze codes and extract metadata.

### Music Caption

The text description of the desired music. Be specific about:
- Genre and style
- Instruments
- Mood and atmosphere
- Tempo feel (if not specifying BPM)

**Example:** "upbeat pop rock with electric guitars, driving drums, and catchy synth hooks"

Click 🎲 to load a random example caption.

### Lyrics

Enter lyrics with structure tags:

```
[Verse 1]
Walking down the street today
Thinking of the words you used to say

[Chorus]
I'm moving on, I'm staying strong
This is where I belong

[Verse 2]
...
```

**Instrumental checkbox:** Check this to generate instrumental music regardless of lyrics content.

**Vocal Language:** Select the language for vocals. Use "unknown" for auto-detection or instrumental tracks.

**Format button:** Click to enhance caption and lyrics using the 5Hz LM.

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| **BPM** | Auto | Tempo in beats per minute (30-300) |
| **Key Scale** | Auto | Musical key (e.g., "C Major", "Am", "F# minor") |
| **Time Signature** | Auto | Time signature: 2 (2/4), 3 (3/4), 4 (4/4), 6 (6/8) |
| **Audio Duration** | Auto/-1 | Target length in seconds (10-600). -1 for automatic |
| **Batch Size** | 2 | Number of audio variations to generate (1-8) |

---

## Advanced Settings

### DiT Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| **Inference Steps** | 8 | Denoising steps. Turbo: 1-20, Base: 1-200 |
| **Guidance Scale** | 7.0 | CFG strength (base model only). Higher = follows prompt more |
| **Seed** | -1 | Random seed. Use comma-separated values for batches |
| **Random Seed** | ✓ | When checked, generates random seeds |
| **Audio Format** | mp3 | Output format: mp3, flac |
| **Shift** | 3.0 | Timestep shift factor (1.0-5.0). Recommended 3.0 for turbo |
| **Inference Method** | ode | ode (Euler, faster) or sde (stochastic) |
| **Custom Timesteps** | - | Override timesteps (e.g., "0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0") |

### Base Model Only Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| **Use ADG** | ✗ | Enable Adaptive Dual Guidance for better quality |
| **CFG Interval Start** | 0.0 | When to start applying CFG (0.0-1.0) |
| **CFG Interval End** | 1.0 | When to stop applying CFG (0.0-1.0) |

### LM Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| **LM Temperature** | 0.85 | Sampling temperature (0.0-2.0). Higher = more creative |
| **LM CFG Scale** | 2.0 | LM guidance strength (1.0-3.0) |
| **LM Top-K** | 0 | Top-K sampling. 0 disables |
| **LM Top-P** | 0.9 | Nucleus sampling (0.0-1.0) |
| **LM Negative Prompt** | "NO USER INPUT" | Negative prompt for CFG |

### CoT (Chain-of-Thought) Options

| Option | Default | Description |
|--------|---------|-------------|
| **CoT Metas** | ✓ | Generate metadata via LM reasoning |
| **CoT Language** | ✓ | Detect vocal language via LM |
| **Constrained Decoding Debug** | ✗ | Enable debug logging |

### Generation Options

| Option | Default | Description |
|--------|---------|-------------|
| **LM Codes Strength** | 1.0 | How strongly LM codes influence generation (0.0-1.0) |
| **Auto Score** | ✗ | Automatically calculate quality scores |
| **Auto LRC** | ✗ | Automatically generate lyrics timestamps |
| **LM Batch Chunk Size** | 8 | Max items per LM batch (GPU memory) |

### Main Generation Controls

| Control | Description |
|---------|-------------|
| **Think** | Enable 5Hz LM for code generation and metadata |
| **ParallelThinking** | Enable parallel LM batch processing |
| **CaptionRewrite** | Let LM enhance the input caption |
| **AutoGen** | Automatically start next batch after completion |

---

## Results Section

### Generated Audio

Up to 8 audio samples are displayed based on batch size. Each sample includes:

- **Audio Player** - Play, pause, and download the generated audio
- **Send To Src** - Send this audio to the Source Audio input for further processing
- **Save** - Save audio and metadata to a JSON file
- **Score** - Calculate perplexity-based quality score
- **LRC** - Generate lyrics timestamps (LRC format)

### Details Accordion

Click "Score & LRC & LM Codes" to expand and view:
- **LM Codes** - The 5Hz semantic codes for this sample
- **Quality Score** - Perplexity-based quality metric
- **Lyrics Timestamps** - LRC format timing data

### Batch Navigation

| Control | Description |
|---------|-------------|
| **◀ Previous** | View the previous batch |
| **Batch Indicator** | Shows current batch position (e.g., "Batch 1 / 3") |
| **Next Batch Status** | Shows background generation progress |
| **Next ▶** | View the next batch (triggers generation if AutoGen is on) |

### Restore Parameters

Click **Apply These Settings to UI** to restore all generation parameters from the current batch back to the input fields. Useful for iterating on a good result.

### Batch Results

The "Batch Results & Generation Details" accordion contains:
- **All Generated Files** - Download all files from all batches
- **Generation Details** - Detailed information about the generation process

---

## LoRA Training

The LoRA Training tab provides tools for creating custom LoRA adapters.

### Dataset Builder Tab

#### Step 1: Load or Scan

**Option A: Load Existing Dataset**
1. Enter the path to a previously saved dataset JSON
2. Click **Load**

**Option B: Scan New Directory**
1. Enter the path to your audio folder
2. Click **Scan** to find audio files (wav, mp3, flac, ogg, opus)

#### Step 2: Configure Dataset

| Setting | Description |
|---------|-------------|
| **Dataset Name** | Name for your dataset |
| **All Instrumental** | Check if all tracks have no vocals |
| **Custom Activation Tag** | Unique tag to activate this LoRA's style |
| **Tag Position** | Where to place the tag: Prepend, Append, or Replace caption |

#### Step 3: Auto-Label

Click **Auto-Label All** to generate metadata for all audio files:
- Caption (music description)
- BPM
- Key
- Time Signature

**Skip Metas** option will skip LLM labeling and use N/A values.

#### Step 4: Preview & Edit

Use the slider to select samples and manually edit:
- Caption
- Lyrics
- BPM, Key, Time Signature
- Language
- Instrumental flag

Click **Save Changes** to update the sample.

#### Step 5: Save Dataset

Enter a save path and click **Save Dataset** to export as JSON.

#### Step 6: Preprocess

Convert the dataset to pre-computed tensors for fast training:
1. Optionally load an existing dataset JSON
2. Set the tensor output directory
3. Click **Preprocess**

This encodes audio to VAE latents, text to embeddings, and runs the condition encoder.

### Train LoRA Tab

#### Dataset Selection

Enter the path to preprocessed tensors directory and click **Load Dataset**.

#### LoRA Settings

| Setting | Default | Description |
|---------|---------|-------------|
| **LoRA Rank (r)** | 64 | Capacity of LoRA. Higher = more capacity, more memory |
| **LoRA Alpha** | 128 | Scaling factor (typically 2x rank) |
| **LoRA Dropout** | 0.1 | Dropout rate for regularization |

#### Training Parameters

| Setting | Default | Description |
|---------|---------|-------------|
| **Learning Rate** | 1e-4 | Optimization learning rate |
| **Max Epochs** | 500 | Maximum training epochs |
| **Batch Size** | 1 | Training batch size |
| **Gradient Accumulation** | 1 | Effective batch = batch_size × accumulation |
| **Save Every N Epochs** | 200 | Checkpoint save frequency |
| **Shift** | 3.0 | Timestep shift for turbo model |
| **Seed** | 42 | Random seed for reproducibility |

#### Training Controls

- **Start Training** - Begin the training process
- **Stop Training** - Interrupt training
- **Training Progress** - Shows current epoch and loss
- **Training Log** - Detailed training output
- **Training Loss Plot** - Visual loss curve

#### Export LoRA

After training, export the final adapter:
1. Enter the export path
2. Click **Export LoRA**

---

## Tips and Best Practices

### For Best Quality

1. **Use thinking mode** - Keep "Think" checkbox enabled for LM-enhanced generation
2. **Be specific in captions** - Include genre, instruments, mood, and style details
3. **Let LM detect metadata** - Leave BPM/Key/Duration empty for auto-detection
4. **Use batch generation** - Generate 2-4 variations and pick the best

### For Faster Generation

1. **Use turbo model** - Select `acestep-v15-turbo` or `acestep-v15-turbo-shift3`
2. **Keep inference steps at 8** - Default is optimal for turbo
3. **Reduce batch size** - Lower batch size if you need quick results
4. **Disable AutoGen** - Manual control over batch generation

### For Consistent Results

1. **Set a specific seed** - Uncheck "Random Seed" and enter a seed value
2. **Save good results** - Use "Save" to export parameters for reproduction
3. **Use "Apply These Settings"** - Restore parameters from a good batch

### For Long-form Music

1. **Set explicit duration** - Specify duration in seconds
2. **Use repaint task** - Fix problematic sections after initial generation
3. **Chain generations** - Use "Send To Src" to build upon previous results

### For Style Consistency

1. **Train a LoRA** - Create a custom adapter for your style
2. **Use reference audio** - Upload style reference in Audio Uploads
3. **Use consistent captions** - Maintain similar descriptive language

### Troubleshooting

**No audio generated:**
- Check that the model is initialized (green status message)
- Ensure 5Hz LM is initialized if using thinking mode
- Check the status output for error messages

**Poor quality results:**
- Increase inference steps (for base model)
- Adjust guidance scale
- Try different seeds
- Make caption more specific

**Out of memory:**
- Reduce batch size
- Enable CPU offloading
- Reduce LM batch chunk size

**LM not working:**
- Ensure "Initialize 5Hz LM" was checked during initialization
- Check that a valid LM model path is selected
- Verify vllm or PyTorch backend is available

---

## Keyboard Shortcuts

The Gradio interface supports standard web shortcuts:
- **Tab** - Move between input fields
- **Enter** - Submit text inputs
- **Space** - Toggle checkboxes

---

## Language Support

The interface supports multiple UI languages:
- **English** (en)
- **Chinese** (zh)
- **Japanese** (ja)

Select your preferred language in the Service Configuration section.

---

For more information, see:
- Main README: [`../../README.md`](../../README.md)
- REST API Documentation: [`API.md`](API.md)
- Python Inference API: [`INFERENCE.md`](INFERENCE.md)
