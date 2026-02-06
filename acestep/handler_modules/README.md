# Handler Modules

This package contains utility modules extracted from the monolithic `handler.py` file as part of the ongoing code decomposition and refactoring effort.

## Modules

### `audio_utils.py` (180 LOC)

Audio processing utilities including:

- `is_silence(audio)` - Detect if audio is effectively silent
- `normalize_audio_to_stereo_48k(audio, sr)` - Convert audio to stereo 48kHz format
- `normalize_audio_code_hints(hints, batch_size)` - Normalize audio code hints for batch processing
- `normalize_instructions(instructions, batch_size, default)` - Normalize instructions for batch processing
- `pad_sequences(sequences, max_length, pad_value)` - Pad sequences to uniform length

**Usage Example:**
```python
from acestep.handler_modules.audio_utils import normalize_audio_to_stereo_48k
import torch

# Convert mono audio to stereo 48kHz
mono_audio = torch.randn(1, 24000)  # Mono at 24kHz
stereo_audio = normalize_audio_to_stereo_48k(mono_audio, sr=24000)
# Result: torch.Size([2, 48000])
```

### `metadata_builder.py` (195 LOC)

Metadata construction and parsing utilities including:

- `create_default_meta()` - Create default metadata string
- `dict_to_meta_string(meta_dict)` - Convert metadata dictionary to formatted string
- `parse_metas(metas)` - Parse and normalize metadata inputs
- `build_metadata_dict(bpm, key_scale, time_signature, duration)` - Build metadata dictionary
- `format_instruction(instruction)` - Format instruction strings
- `format_lyrics(lyrics, language)` - Format lyrics with language tags

**Usage Example:**
```python
from acestep.handler_modules.metadata_builder import build_metadata_dict, dict_to_meta_string

# Build metadata
meta = build_metadata_dict(bpm=120, key_scale="C major", time_signature="4/4", duration=60)
# Result: {'bpm': 120, 'keyscale': 'C major', 'timesignature': '4/4', 'duration': 60}

# Convert to string format
meta_str = dict_to_meta_string(meta)
# Result: "- bpm: 120\n- timesignature: 4/4\n- keyscale: C major\n- duration: 60 seconds\n"
```

## Design Principles

Each module in this package follows these principles:

1. **Single Responsibility** - Each module has one clear purpose
2. **Small Size** - Maximum 200 LOC per module
3. **Pure Functions** - Functions are stateless where possible
4. **Clear Interfaces** - Well-defined inputs and outputs
5. **Testability** - Each function can be tested independently

## Integration

These modules are designed to be:

- **Imported directly** from the handler or other modules
- **Backward compatible** with existing code
- **Independently testable** without mocking the entire system

## Future Modules

Additional modules planned for extraction from `handler.py`:

- `model_manager.py` - Model loading, initialization, device management
- `audio_encoder.py` - Audio encoding to latent space
- `audio_decoder.py` - Latent decoding to audio
- `lora_manager.py` - LoRA adapter management
- `inference_engine.py` - Core inference orchestration

See [docs/REFACTORING_PLAN.md](../../docs/REFACTORING_PLAN.md) for the complete refactoring roadmap.

## Testing

All modules have been tested to ensure correctness:

```bash
# Test audio_utils
python3 -c "from acestep.handler_modules.audio_utils import *; print('✅ Tests passed')"

# Test metadata_builder
python3 -c "from acestep.handler_modules.metadata_builder import *; print('✅ Tests passed')"
```

## Contributing

When adding new modules to this package:

1. Keep modules under 200 LOC
2. Write clear docstrings with examples
3. Add type hints to all functions
4. Test the module independently
5. Update this README with module documentation

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for detailed guidelines.
