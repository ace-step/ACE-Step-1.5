# Migration Guide: Using Refactored Handler Modules

This guide explains how to use the newly extracted handler modules in your code.

## Overview

We've begun extracting utilities from the large `handler.py` file into smaller, focused modules in the `acestep/handler_modules/` package. This guide shows you how to use them.

## Available Modules

### 1. Audio Utilities (`audio_utils`)

Functions for audio processing and normalization.

#### Import

```python
from acestep.handler_modules.audio_utils import (
    is_silence,
    normalize_audio_to_stereo_48k,
    normalize_audio_code_hints,
    normalize_instructions,
    pad_sequences
)
```

#### Examples

**Check if audio is silent:**
```python
import torch
from acestep.handler_modules.audio_utils import is_silence

audio = torch.randn(2, 1000) * 1e-5
if is_silence(audio):
    print("Audio is silent")
```

**Normalize audio to stereo 48kHz:**
```python
import torch
from acestep.handler_modules.audio_utils import normalize_audio_to_stereo_48k

# Mono audio at 24kHz
mono_audio = torch.randn(1, 24000)

# Convert to stereo 48kHz
stereo_audio = normalize_audio_to_stereo_48k(mono_audio, sr=24000)
print(stereo_audio.shape)  # torch.Size([2, 48000])
```

**Normalize batch parameters:**
```python
from acestep.handler_modules.audio_utils import normalize_instructions

# Single instruction for batch of 4
instructions = normalize_instructions("Generate upbeat music", batch_size=4)
# Result: ["Generate upbeat music", "Generate upbeat music", "Generate upbeat music", "Generate upbeat music"]

# Multiple instructions
instructions = normalize_instructions(
    ["Rock song", "Jazz tune", "Pop hit", "Classical piece"],
    batch_size=4
)
# Result: ["Rock song", "Jazz tune", "Pop hit", "Classical piece"]
```

**Pad sequences:**
```python
import torch
from acestep.handler_modules.audio_utils import pad_sequences

sequences = [
    torch.tensor([1, 2, 3]),
    torch.tensor([4, 5]),
    torch.tensor([6, 7, 8, 9])
]

padded = pad_sequences(sequences, max_length=5, pad_value=0)
print(padded)
# tensor([[1, 2, 3, 0, 0],
#         [4, 5, 0, 0, 0],
#         [6, 7, 8, 9, 0]])
```

### 2. Metadata Builder (`metadata_builder`)

Functions for constructing and parsing music metadata.

#### Import

```python
from acestep.handler_modules.metadata_builder import (
    create_default_meta,
    dict_to_meta_string,
    parse_metas,
    build_metadata_dict,
    format_instruction,
    format_lyrics
)
```

#### Examples

**Create default metadata:**
```python
from acestep.handler_modules.metadata_builder import create_default_meta

meta = create_default_meta()
print(meta)
# - bpm: N/A
# - timesignature: N/A
# - keyscale: N/A
# - duration: 30 seconds
```

**Build metadata from components:**
```python
from acestep.handler_modules.metadata_builder import (
    build_metadata_dict,
    dict_to_meta_string
)

# Build metadata dictionary
meta_dict = build_metadata_dict(
    bpm=120,
    key_scale="C major",
    time_signature="4/4",
    duration=60.0
)

# Convert to string format
meta_str = dict_to_meta_string(meta_dict)
print(meta_str)
# - bpm: 120
# - timesignature: 4/4
# - keyscale: C major
# - duration: 60 seconds
```

**Parse metadata from various formats:**
```python
from acestep.handler_modules.metadata_builder import parse_metas

metas = [
    None,  # Will use default
    "custom metadata string",  # Already formatted
    {"bpm": 90, "keyscale": "D minor", "timesignature": "3/4"}  # Dictionary
]

parsed = parse_metas(metas)
for i, meta in enumerate(parsed):
    print(f"Meta {i}:", meta[:40], "...")
```

**Format instructions and lyrics:**
```python
from acestep.handler_modules.metadata_builder import (
    format_instruction,
    format_lyrics
)

# Add colon to instruction
instruction = format_instruction("Generate a rock song")
print(instruction)  # "Generate a rock song:"

# Add language tag to lyrics
lyrics = format_lyrics("Hello world, this is a song", "English")
print(lyrics)  # "[English] Hello world, this is a song"
```

## Backward Compatibility

**Important:** The original `handler.py` still exists and works exactly as before. These new modules are additions, not replacements (yet).

You can:
- Continue using `handler.py` as before
- Gradually migrate to new modules
- Mix old and new code during transition

## When to Use New Modules

Use the new modules when:

✅ Writing new code  
✅ Refactoring existing code  
✅ Adding tests  
✅ Need clear, focused functionality  

Continue using `handler.py` when:

⚠️ Making minimal bug fixes  
⚠️ Unsure which module to use  
⚠️ Existing code works fine  

## Future Modules

Coming soon to `handler_modules/`:

- `model_manager.py` - Model loading and initialization
- `audio_encoder.py` - Audio encoding to latents
- `audio_decoder.py` - Latent decoding to audio
- `lora_manager.py` - LoRA adapter management
- `inference_engine.py` - Core inference orchestration

## Common Patterns

### Pattern 1: Batch Processing

```python
from acestep.handler_modules.audio_utils import normalize_instructions

def process_generation_batch(captions, batch_size=4):
    # Normalize inputs to batch size
    instructions = normalize_instructions(
        captions,
        batch_size=batch_size,
        default="Generate music"
    )
    
    # Process each instruction
    for instruction in instructions:
        # Your generation logic here
        pass
```

### Pattern 2: Metadata Construction

```python
from acestep.handler_modules.metadata_builder import (
    build_metadata_dict,
    dict_to_meta_string
)

def create_music_metadata(user_params):
    # Build structured metadata
    meta_dict = build_metadata_dict(
        bpm=user_params.get('bpm', 120),
        key_scale=user_params.get('key', 'C major'),
        time_signature=user_params.get('time_sig', '4/4'),
        duration=user_params.get('duration', 30)
    )
    
    # Convert to string format for model
    return dict_to_meta_string(meta_dict)
```

### Pattern 3: Audio Preprocessing

```python
from acestep.handler_modules.audio_utils import (
    normalize_audio_to_stereo_48k,
    is_silence
)
import torchaudio

def preprocess_reference_audio(audio_path):
    # Load audio
    audio, sr = torchaudio.load(audio_path)
    
    # Normalize to stereo 48kHz
    audio = normalize_audio_to_stereo_48k(audio, sr)
    
    # Check if silent
    if is_silence(audio):
        raise ValueError("Reference audio is silent")
    
    return audio
```

## Testing Your Code

When using the new modules, test them independently:

```python
import torch
from acestep.handler_modules.audio_utils import normalize_audio_to_stereo_48k

def test_audio_normalization():
    # Create test audio
    mono_audio = torch.randn(1, 24000)
    
    # Normalize
    stereo_audio = normalize_audio_to_stereo_48k(mono_audio, 24000)
    
    # Verify
    assert stereo_audio.shape[0] == 2  # Stereo
    assert stereo_audio.shape[1] == 48000  # 48kHz
    
    print("✅ Test passed")

test_audio_normalization()
```

## Getting Help

If you have questions:

1. Check module docstrings: `help(function_name)`
2. Read module README: `acestep/handler_modules/README.md`
3. Look at architecture docs: `docs/ARCHITECTURE.md`
4. Ask on Discord: https://discord.gg/PeWDxrkdj7
5. Open an issue on GitHub

## Contributing

Want to help with refactoring? See:
- `docs/REFACTORING_PLAN.md` - Detailed roadmap
- `CONTRIBUTING.md` - Contribution guidelines
- `docs/REFACTORING_PROGRESS.md` - Current status

We welcome contributions! 🎵

---

**Last Updated:** 2026-02-06  
**Status:** Living document - will be updated as more modules are extracted
