# ACE-Step Architecture Guide

## Overview

This document describes the architecture of ACE-Step 1.5, a music generation system based on hybrid LM+DiT architecture.

## Current Architecture (Before Refactoring)

### Major Components

```
ACE-Step/
├── acestep/
│   ├── handler.py (3,466 LOC)           # Core business logic - NEEDS REFACTORING
│   ├── api_server.py (2,495 LOC)        # FastAPI server - NEEDS REFACTORING
│   ├── llm_inference.py (2,446 LOC)     # LLM handling - NEEDS REFACTORING
│   ├── constrained_logits_processor.py (2,318 LOC) # Logits - NEEDS REFACTORING
│   ├── inference.py (1,193 LOC)         # Inference utilities
│   ├── training/                        # Training components
│   │   ├── trainer.py                   # LoRA training
│   │   ├── dataset_builder.py           # Dataset construction
│   │   └── ...
│   └── gradio_ui/                       # UI components
│       ├── events/
│       │   ├── results_handlers.py (2,284 LOC) # NEEDS REFACTORING
│       │   ├── generation_handlers.py
│       │   └── training_handlers.py
│       └── interfaces/
│           ├── generation.py
│           └── training.py
└── cli.py (2,006 LOC)                   # CLI interface - NEEDS REFACTORING
```

### Key Problems

1. **Monolithic Files**: Multiple files exceed 2,000 LOC, making them hard to maintain
2. **Mixed Concerns**: Single files handle multiple responsibilities
3. **WIP Features Exposed**: LoRA training is broken but visible to users
4. **Poor Testability**: Large modules are difficult to unit test
5. **Unclear Dependencies**: Complex interdependencies between modules

## Target Architecture (After Refactoring)

### Design Principles

1. **Single Responsibility**: Each module has one clear purpose
2. **Small Modules**: Maximum 200 LOC per module
3. **Clear Interfaces**: Well-defined public APIs
4. **Testability**: Each module can be tested independently
5. **Feature Flags**: WIP features hidden by default

### Proposed Structure

```
ACE-Step/
├── acestep/
│   ├── feature_flags.py                 # Feature flag system [NEW]
│   │
│   ├── handler/                         # Business logic [REFACTORED]
│   │   ├── __init__.py                  # Main handler facade
│   │   ├── model_manager.py             # Model loading/unloading
│   │   ├── audio_encoder.py             # Audio → latents
│   │   ├── audio_decoder.py             # Latents → audio
│   │   ├── lora_manager.py              # LoRA operations
│   │   ├── inference_engine.py          # Core inference
│   │   ├── metadata_builder.py          # Metadata construction
│   │   ├── batch_processor.py           # Batch processing
│   │   ├── text_processor.py            # Text encoding
│   │   └── audio_utils.py               # Audio utilities
│   │
│   ├── api/                             # API server [REFACTORED]
│   │   ├── __init__.py                  # App factory
│   │   ├── server.py                    # Main server
│   │   ├── models/                      # Pydantic models
│   │   │   ├── generation_models.py
│   │   │   ├── training_models.py
│   │   │   └── common_models.py
│   │   ├── routes/                      # API routes
│   │   │   ├── generation.py
│   │   │   ├── training.py
│   │   │   ├── model_management.py
│   │   │   └── health.py
│   │   ├── middleware/                  # Middleware
│   │   │   ├── error_handler.py
│   │   │   ├── logging.py
│   │   │   └── cors.py
│   │   └── dependencies.py              # FastAPI deps
│   │
│   ├── llm/                             # LLM handling [REFACTORED]
│   │   ├── __init__.py
│   │   ├── inference_engine.py          # Core inference
│   │   ├── prompt_builder.py            # Prompt construction
│   │   ├── streaming.py                 # Streaming logic
│   │   ├── tokenization.py              # Token processing
│   │   ├── response_parser.py           # Response parsing
│   │   └── models/
│   │       ├── model_loader.py
│   │       └── model_config.py
│   │
│   ├── logits/                          # Logits processing [REFACTORED]
│   │   ├── __init__.py
│   │   ├── base_processor.py
│   │   ├── constraints/                 # Constraint types
│   │   │   ├── grammar_constraint.py
│   │   │   ├── format_constraint.py
│   │   │   └── vocabulary_constraint.py
│   │   ├── processors/                  # Specific processors
│   │   │   ├── json_processor.py
│   │   │   ├── xml_processor.py
│   │   │   └── custom_processor.py
│   │   └── validators/                  # Validation logic
│   │       ├── syntax_validator.py
│   │       └── semantic_validator.py
│   │
│   ├── gradio_ui/
│   │   ├── handlers/                    # Result handlers [REFACTORED]
│   │   │   ├── __init__.py
│   │   │   ├── base_handler.py
│   │   │   ├── generation/
│   │   │   │   ├── music_generation.py
│   │   │   │   ├── cover_generation.py
│   │   │   │   └── audio_editing.py
│   │   │   ├── training/
│   │   │   │   ├── dataset_handler.py
│   │   │   │   ├── training_handler.py
│   │   │   │   └── export_handler.py
│   │   │   ├── analysis/
│   │   │   │   ├── audio_analysis.py
│   │   │   │   └── quality_scoring.py
│   │   │   └── common/
│   │   │       ├── file_handler.py
│   │   │       ├── ui_updater.py
│   │   │       └── error_handler.py
│   │   └── interfaces/                  # UI interfaces
│   │       ├── generation.py
│   │       └── training.py
│   │
│   └── training/                        # Training components
│       ├── trainer.py
│       ├── dataset_builder.py
│       └── ...
│
└── cli/                                 # CLI [REFACTORED]
    ├── __init__.py
    ├── commands/
    │   ├── generate.py
    │   ├── train.py
    │   ├── download.py
    │   └── server.py
    └── utils/
        ├── arg_parser.py
        ├── config_loader.py
        └── output_formatter.py
```

## Component Responsibilities

### Feature Flags (`feature_flags.py`)
- **Purpose**: Control visibility of experimental/WIP features
- **Interface**: `is_feature_enabled(Feature) -> bool`
- **Configuration**: Environment variables, runtime overrides

### Handler Package (`handler/`)

#### Main Handler (`__init__.py`)
- **Purpose**: Facade for all business logic operations
- **Delegates to**: Specialized handlers
- **Maintains**: Backward compatibility

#### Model Manager (`model_manager.py`)
- **Purpose**: Model lifecycle management
- **Responsibilities**:
  - Load/unload models
  - Device management
  - Memory optimization

#### Audio Encoder/Decoder (`audio_encoder.py`, `audio_decoder.py`)
- **Purpose**: Audio ↔ latent space conversion
- **Responsibilities**:
  - Tiled encoding/decoding
  - Audio normalization
  - Memory-efficient processing

#### LoRA Manager (`lora_manager.py`)
- **Purpose**: LoRA adapter management
- **Responsibilities**:
  - Load/unload LoRA weights
  - Scale control
  - Status tracking

#### Inference Engine (`inference_engine.py`)
- **Purpose**: Coordinate music generation
- **Responsibilities**:
  - Orchestrate generation pipeline
  - Batch processing
  - Progress tracking

#### Metadata Builder (`metadata_builder.py`)
- **Purpose**: Construct metadata for generation
- **Responsibilities**:
  - Build metadata dictionaries
  - Parse metadata strings
  - Format instructions

### API Package (`api/`)

#### Server (`server.py`)
- **Purpose**: FastAPI application setup
- **Responsibilities**:
  - App initialization
  - Middleware configuration
  - Lifecycle management

#### Routes (`routes/`)
- **Purpose**: API endpoint handlers
- **Organization**: By feature domain
- **Feature flags**: Check before exposing routes

#### Models (`models/`)
- **Purpose**: Request/response schemas
- **Uses**: Pydantic models
- **Validation**: Input/output validation

### LLM Package (`llm/`)

#### Inference Engine (`inference_engine.py`)
- **Purpose**: Execute LLM inference
- **Responsibilities**:
  - Model execution
  - Token generation
  - Response handling

#### Prompt Builder (`prompt_builder.py`)
- **Purpose**: Construct LLM prompts
- **Responsibilities**:
  - Template management
  - Context building
  - Format conversion

## Data Flow

### Music Generation Pipeline

```
1. User Input
   ├→ caption/lyrics
   ├→ metadata (BPM, key, etc.)
   └→ optional reference audio

2. LLM Processing (llm/)
   ├→ prompt construction
   ├→ constrained generation
   └→ metadata extraction

3. Handler Processing (handler/)
   ├→ audio encoding (if reference)
   ├→ metadata building
   ├→ batch preparation
   └→ inference execution

4. DiT Generation
   ├→ latent generation
   └→ LoRA application (if enabled)

5. Audio Decoding (handler/audio_decoder.py)
   ├→ tiled decoding
   └→ audio reconstruction

6. Result Processing
   ├→ file saving
   ├→ quality scoring
   └→ metadata generation
```

### LoRA Training Pipeline (WIP - Hidden by Feature Flag)

```
1. Dataset Building
   ├→ scan audio files
   ├→ extract metadata
   └→ prepare training data

2. Training (CURRENTLY BROKEN)
   ├→ load base model
   ├→ initialize LoRA layers
   ├→ training loop
   └→ checkpoint saving

3. Export
   ├→ merge LoRA weights
   └→ save adapter
```

## Feature Flag System

### Purpose
Control visibility of features that are:
- Work in progress (WIP)
- Experimental
- Platform-specific
- Unstable

### Usage

```python
from acestep.feature_flags import Feature, is_feature_enabled

# Check if feature is enabled
if is_feature_enabled(Feature.LORA_TRAINING):
    # Show training UI
    pass
else:
    # Show informative message
    pass
```

### Configuration

#### Environment Variables
```bash
export ACESTEP_FEATURE_LORA_TRAINING=true
export ACESTEP_FEATURE_API_TRAINING_ENDPOINTS=false
```

#### Runtime Overrides
```python
from acestep.feature_flags import FeatureFlags, Feature

# Enable for testing
FeatureFlags.enable(Feature.LORA_TRAINING)

# Disable after testing
FeatureFlags.disable(Feature.LORA_TRAINING)
```

### Current Flags

| Flag | Default | Status | Reason |
|------|---------|--------|--------|
| `LORA_TRAINING` | `false` | 🔴 Disabled | Broken: 10+ hour tensor gen, 30% GPU |
| `API_TRAINING_ENDPOINTS` | `false` | 🔴 Disabled | Depends on LoRA training |
| `ADVANCED_EDITING` | `true` | 🟢 Enabled | Working |
| `BATCH_GENERATION` | `true` | 🟢 Enabled | Working |
| `EXPERIMENTAL_SCORING` | `true` | 🟢 Enabled | Working |

## Migration Strategy

### Phase 1: Feature Flags ✅
- [x] Create feature flag system
- [x] Hide broken LoRA training
- [x] Add informative messages

### Phase 2: Handler Refactoring (In Progress)
- [ ] Create module structure
- [ ] Extract model management
- [ ] Extract audio processing
- [ ] Extract LoRA management
- [ ] Update imports
- [ ] Test compatibility

### Phase 3: API Refactoring
- [ ] Create API package structure
- [ ] Extract routes
- [ ] Extract models
- [ ] Add middleware

### Phase 4: LLM Refactoring
- [ ] Create LLM package
- [ ] Extract inference
- [ ] Extract prompt building
- [ ] Extract streaming

### Phase 5: Remaining Refactoring
- [ ] Logits processor
- [ ] Result handlers
- [ ] CLI

## Testing Strategy

### Unit Tests
Each module should have unit tests covering:
- Happy path scenarios
- Error conditions
- Edge cases
- Invalid inputs

### Integration Tests
Test interactions between modules:
- Handler → LLM
- Handler → API
- API → Handler

### Regression Tests
Ensure existing functionality:
- Music generation works
- API endpoints work
- CLI commands work

### Performance Tests
Verify no degradation:
- Generation time
- Memory usage
- GPU utilization

## Best Practices

### Module Design
1. **Single Responsibility**: One clear purpose per module
2. **Small Size**: Maximum 200 LOC
3. **Clear Interface**: Well-defined public API
4. **Minimal Dependencies**: Reduce coupling

### Code Organization
1. **Imports at Top**: Standard, third-party, local
2. **Type Hints**: Use type annotations
3. **Docstrings**: Document all public functions
4. **Error Handling**: Explicit error conditions

### Naming Conventions
1. **Functions**: Verb phrases (e.g., `load_model`, `encode_audio`)
2. **Classes**: Nouns (e.g., `ModelManager`, `AudioEncoder`)
3. **Constants**: UPPER_SNAKE_CASE
4. **Private**: Leading underscore

### Documentation
1. **Module Docstring**: Purpose and usage
2. **Function Docstring**: Args, returns, raises
3. **Inline Comments**: Explain complex logic
4. **Type Hints**: Document expected types

## Troubleshooting

### Feature Not Available
**Issue**: Feature is hidden in UI
**Solution**: Check feature flags, set environment variable if testing

### Import Errors After Refactoring
**Issue**: Old imports no longer work
**Solution**: Update imports to new module structure, use compatibility facade

### Performance Degradation
**Issue**: Refactored code is slower
**Solution**: Profile code, optimize hot paths, consider caching

## References

- [Refactoring Plan](./REFACTORING_PLAN.md) - Detailed refactoring roadmap
- [Contributing Guide](../CONTRIBUTING.md) - How to contribute
- [Security Policy](../SECURITY.md) - Security guidelines

---

**Last Updated:** 2026-02-06
**Status:** Phase 1 Complete, Phase 2 In Progress
