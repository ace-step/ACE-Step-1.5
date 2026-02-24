# ACE-Step Gradio Demo User Guide

**Language / 语言 / 言語:** [English](GRADIO_GUIDE.md) | [中文](../zh/GRADIO_GUIDE.md) | [日本語](../ja/GRADIO_GUIDE.md)

---

This guide provides comprehensive documentation for using the ACE-Step Gradio web interface for music generation, including all features and settings.

## Table of Contents

- [Getting Started](#getting-started)
- [Service Configuration](#service-configuration)
- [Generation Modes](#generation-modes)
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

The Gradio interface is organized as follows:

1. **Settings** (collapsed accordion) - Service configuration, DiT/LM parameters, output options
2. **Generation Tab** - The main workspace with a **Generation Mode** radio selector:
   - Turbo/SFT models: Simple, Custom, Remix, Repaint
   - Base model: Simple, Custom, Remix, Repaint, Extract, Lego, Complete
3. **Results Section** - Generated audio playback, scoring, batch navigation
4. **Training Tab** - Dataset builder and LoRA training

---

## Service Configuration

### Model Selection

| Setting | Description |
|---------|-------------|
| **Checkpoint File** | Select a trained model checkpoint (if available) |
| **Main Model Path** | Choose the DiT model configuration (e.g., `acestep-v15-turbo`, `acestep-v15-turbo-shift3`) |
| **Device** | Processing device: `auto` (recommended), `cuda`, or `cpu` |

### 5Hz LM Configuration

| Setting | Description |
|---------|-------------|
| **5Hz LM Model Path** | Select the language model. **Available models are filtered by your GPU tier** — e.g., 6-8GB GPUs only show 0.6B, while 24GB+ GPUs show all sizes (0.6B, 1.7B, 4B). |
| **5Hz LM Backend** | `vllm` (faster, recommended for NVIDIA with ≥8GB VRAM), `pt` (PyTorch, universal fallback), or `mlx` (Apple Silicon). **On GPUs <8GB, the backend is restricted to `pt`/`mlx`** because vllm's KV cache is too memory-hungry. |
| **Initialize 5Hz LM** | Check to load the LM during initialization (required for thinking mode). **Automatically unchecked and disabled on GPUs ≤6GB** (Tier 1-2). |

> **Adaptive Defaults**: All LM settings are automatically configured based on your GPU's VRAM tier. The recommended LM model, backend, and initialization state are pre-set for optimal performance. You can manually override these, but the system will warn you if your selection is incompatible with your GPU.

### Performance Options

| Setting | Description |
|---------|-------------|
| **Use Flash Attention** | Enable for faster inference (requires flash_attn package) |
| **Offload to CPU** | Offload models to CPU when idle to save GPU memory. **Automatically enabled on GPUs <20GB.** |
| **Offload DiT to CPU** | Specifically offload the DiT model to CPU. **Automatically enabled on GPUs <12GB.** |
| **INT8 Quantization** | Reduce model VRAM footprint with INT8 weight quantization. **Automatically enabled on GPUs <20GB.** |
| **Compile Model** | Enable `torch.compile` for optimized inference. **Enabled by default on all tiers** (required when quantization is active). |

> **Tier-Aware Settings**: Offload, quantization, and compile options are automatically set based on your GPU tier. See [GPU_COMPATIBILITY.md](GPU_COMPATIBILITY.md) for the full tier table.

### LoRA Adapter

| Setting | Description |
|---------|-------------|
| **LoRA Path** | Path to trained LoRA adapter directory |
| **Load LoRA** | Load the specified LoRA adapter |
| **Unload** | Remove the currently loaded LoRA |
| **Use LoRA** | Enable/disable the loaded LoRA for inference |

> **⚠️ Note:** LoRA adapters cannot be loaded on quantized models due to a compatibility issue between PEFT and TorchAO. If you need to use LoRA, set **INT8 Quantization** to **None** before loading the adapter.

### Initialization

Click **Initialize Service** to load the models. The status box will show progress and confirmation, including:
- The detected GPU tier and VRAM
- Maximum allowed duration and batch size (adjusted dynamically based on whether LM was initialized)
- Any warnings about incompatible settings that were automatically corrected

After initialization, the **Audio Duration** and **Batch Size** sliders are automatically updated to reflect the tier's limits.

---

## Generation Modes

The **Generation Mode** radio selector at the top of the Generation tab determines your workflow. Turbo and SFT models offer four modes; Base models add three more.

### Simple Mode

Designed for quick, natural language-based music generation.

**How to use:**
1. Select **Simple** in the Generation Mode radio
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

Full control over all generation parameters (text2music).

**How to use:**
1. Select **Custom** in the Generation Mode radio
2. Manually fill in the Caption and Lyrics fields
3. Optionally upload Reference Audio for style guidance
4. Set optional metadata (BPM, Key, Duration, etc.)
5. Optionally click **Format** to enhance your input using the LM
6. Configure advanced settings as needed
7. Click **Generate Music** to create the audio

### Remix Mode

Transform existing audio while maintaining its melodic structure but changing style.

**How to use:**
1. Select **Remix** in the Generation Mode radio
2. Upload Source Audio (the song to remix)
3. Write a Caption describing the target style
4. Optionally modify Lyrics
5. Adjust **Remix Strength** (0.0-1.0): higher = closer to original structure
6. Click **Generate Music**

**Use cases:** Creating cover versions, style transfer, generating variants of a song.

### Repaint Mode

Regenerate a specific time segment of audio while keeping the rest intact.

**How to use:**
1. Select **Repaint** in the Generation Mode radio
2. Upload Source Audio
3. Set **Repainting Start** and **Repainting End** (seconds; -1 for end of file)
4. Write a Caption describing the desired content for the repainted section
5. Click **Generate Music**

**Use cases:** Fixing problematic sections, changing lyrics in a segment, extending songs.

### Extract Mode (Base Model Only)

Extract/isolate a specific instrument track from mixed audio.

**How to use:**
1. Select **Extract** in the Generation Mode radio
2. Upload Source Audio
3. Select the **Track Name** to extract from the dropdown
4. Click **Generate Music**

**Available tracks:** vocals, backing_vocals, drums, bass, guitar, keyboard, percussion, strings, synth, fx, brass, woodwinds

### Lego Mode (Base Model Only)

Add a new instrument track to existing audio.

**How to use:**
1. Select **Lego** in the Generation Mode radio
2. Upload Source Audio
3. Select the **Track Name** to add from the dropdown
4. Write a Caption describing the track characteristics
5. Click **Generate Music**

### Complete Mode (Base Model Only)

Complete partial tracks with specified instruments (auto-arrangement).

**How to use:**
1. Select **Complete** in the Generation Mode radio
2. Upload Source Audio
3. Select multiple **Track Names** to add
4. Write a Caption describing the desired style
5. Click **Generate Music**

---

## Input Parameters

### Audio Inputs

| Field | Description |
|-------|-------------|
| **Reference Audio** | Optional audio for style/timbre guidance (visible in Custom mode) |
| **Source Audio** | Required for Remix, Repaint, Extract, Lego, Complete modes |
| **Convert to Codes** | Extract 5Hz semantic codes from source audio |

#### LM Codes Hints (Custom Mode)

Pre-computed audio semantic codes can be pasted here to guide generation. Use the **Transcribe** button to analyze codes and extract metadata. This is an advanced feature for controlling melodic structure without uploading source audio.

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
| **Batch Size** | 2 | Number of audio variations to generate (1-8). **Value persists across mode changes and enhancement actions**. Can be set via `--batch_size` CLI argument |

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

> 📖 **For a comprehensive step-by-step walkthrough** (data preparation, annotation, preprocessing, training, and export), see the [LoRA Training Tutorial](./LoRA_Training_Tutorial.md).

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

#### Performance notes (Windows / low VRAM)

On Windows or systems with limited VRAM, training and preprocessing can stall or use more memory than expected. The following can help:

- **Persistent workers** – Epoch-boundary worker reinitialization on Windows can cause long pauses; the default behavior has been improved (see related fixes) so stalls are less common out of the box.
- **Offload unused models** – During preprocessing, offloading models that are not needed for the current step (e.g. via **Offload to CPU** in Service Configuration) can greatly reduce VRAM use and avoid spikes that slow or block preprocessing.
- **Tiled encode** – Using tiled encoding for preprocessing reduces peak VRAM and can turn multi-minute preprocessing into much shorter runs when VRAM is tight.
- **Batch size** – Lower batch size during training reduces memory use at the cost of longer training; gradient accumulation can keep effective batch size while staying within VRAM limits.

These options are especially useful when preprocessing takes a long time or you see out-of-memory or long pauses between epochs.

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
- The system includes automatic VRAM management (VRAM guard, adaptive VAE decode, auto batch reduction). If OOM still occurs:
- Reduce batch size manually
- Enable CPU offloading (should be auto-enabled for GPUs <20GB)
- Enable INT8 quantization (should be auto-enabled for GPUs <20GB)
- Reduce LM batch chunk size
- See [GPU_COMPATIBILITY.md](GPU_COMPATIBILITY.md) for recommended settings per tier

**LM not working:**
- Ensure "Initialize 5Hz LM" was checked during initialization (disabled by default on GPUs ≤6GB)
- Check that a valid LM model path is selected (only tier-compatible models are shown)
- Verify vllm or PyTorch backend is available (vllm restricted on GPUs <8GB)
- If the LM checkbox is grayed out, your GPU tier does not support LM — use DiT-only mode

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
