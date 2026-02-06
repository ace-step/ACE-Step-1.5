# Code Decomposition and Architecture Refactoring Plan

## Executive Summary

This document outlines a comprehensive plan to refactor the ACE-Step codebase, addressing critical architectural issues including:
- Files exceeding 2500 lines of code (LOC)
- Monolithic modules with multiple responsibilities
- Work-in-progress (WIP) features exposed in production UI
- Lack of proper separation of concerns

## Current State Analysis

### Large Files Requiring Decomposition

| File | LOC | Methods/Functions | Primary Issues |
|------|-----|-------------------|----------------|
| `acestep/handler.py` | 3,466 | 62 | Monolithic business logic; handles model management, audio processing, LoRA, inference, metadata |
| `acestep/api_server.py` | 2,495 | N/A | All API routes in one file; mixed concerns |
| `acestep/llm_inference.py` | 2,446 | N/A | LLM inference, prompt building, streaming all together |
| `acestep/constrained_logits_processor.py` | 2,318 | N/A | All logits processing logic in one place |
| `acestep/gradio_ui/events/results_handlers.py` | 2,284 | N/A | All result handling in one massive file |
| `cli.py` | 2,006 | N/A | CLI implementation needs refactoring |

### WIP Features Currently Exposed

1. **LoRA Training Pipeline** - Currently broken according to issue:
   - UI fully exposed in training tab
   - Tensor generation runs for 10+ hours with GPU at 30% utilization
   - No clear indication that feature is incomplete
   - Needs feature flag to hide until stable

## Refactoring Principles

Following software engineering best practices:

1. **Single Responsibility** - Each module/function does one thing
2. **Separation of Concerns** - Split by responsibility, not convenience
3. **Clear Dependencies** - Data in, data out; obvious side effects
4. **Descriptive Naming** - Functions named after what they do, not how
5. **Testability** - Each module can be unit-tested independently
6. **Module Size** - Target maximum 200 LOC per module
7. **Avoid Premature Abstraction** - Refactor when responsibilities are clear

## Implementation Plan

### Phase 1: Feature Flag System (Priority: HIGH)

**Goal:** Hide WIP features from users to prevent confusion and wasted time.

**Implementation:**
1. Create `acestep/feature_flags.py`:
   - Define feature flag enum
   - Environment variable support
   - Configuration file support
   
2. Add configuration to hide LoRA training:
   ```python
   FEATURE_FLAGS = {
       "lora_training": False,  # Currently broken
       "advanced_editing": True,
       "batch_generation": True,
   }
   ```

3. Update `acestep/gradio_ui/interfaces/training.py`:
   - Check feature flag before showing LoRA training tab
   - Add informative message when feature is disabled

**Files to Create:**
- `acestep/feature_flags.py`
- `acestep/config/feature_config.toml`

**Files to Modify:**
- `acestep/gradio_ui/interfaces/training.py`
- `acestep/api_server.py` (if LoRA training endpoints exposed)

**Estimated LOC:** ~150

---

### Phase 2: Refactor `handler.py` (Priority: CRITICAL)

**Current:** 3,466 LOC with 62 methods in single class `AceStepHandler`

**Target Structure:**
```
acestep/
├── handler/
│   ├── __init__.py                    # Main handler facade (100 LOC)
│   ├── model_manager.py               # Model loading/unloading (200 LOC)
│   ├── audio_encoder.py               # Audio encoding to latents (200 LOC)
│   ├── audio_decoder.py               # Latent decoding to audio (200 LOC)
│   ├── lora_manager.py                # LoRA operations (150 LOC)
│   ├── inference_engine.py            # Core inference logic (200 LOC)
│   ├── metadata_builder.py            # Metadata construction (150 LOC)
│   ├── batch_processor.py             # Batch processing (200 LOC)
│   ├── text_processor.py              # Text encoding/processing (150 LOC)
│   └── audio_utils.py                 # Audio utilities (150 LOC)
```

**Decomposition Strategy:**

1. **Model Management** (`model_manager.py`):
   - `initialize_service()`
   - `_load_model_context()`
   - Model loading/unloading logic
   - Device management

2. **Audio Processing** (`audio_encoder.py`, `audio_decoder.py`):
   - `_encode_audio_to_latents()`
   - `tiled_encode()` and helpers
   - `tiled_decode()` and helpers
   - Audio normalization

3. **LoRA Management** (`lora_manager.py`):
   - `load_lora()`
   - `unload_lora()`
   - `set_use_lora()`
   - `set_lora_scale()`
   - `get_lora_status()`

4. **Inference Orchestration** (`inference_engine.py`):
   - `service_generate()`
   - `generate_music()`
   - Inference coordination

5. **Metadata Handling** (`metadata_builder.py`):
   - `_build_metadata_dict()`
   - `build_dit_inputs()`
   - `prepare_metadata()`
   - Metadata parsing

6. **Main Handler** (`__init__.py`):
   - Facade pattern
   - Delegates to specialized modules
   - Maintains backward compatibility

**Migration Strategy:**
- Create new module structure
- Move functions one responsibility at a time
- Update imports incrementally
- Keep old handler working until all references updated
- Add deprecation warnings

**Estimated Total LOC:** ~1,600 (across 10 modules)

---

### Phase 3: Refactor `api_server.py` (Priority: HIGH)

**Current:** 2,495 LOC with all routes in one file

**Target Structure:**
```
acestep/api/
├── __init__.py                        # API app factory (50 LOC)
├── server.py                          # Main server setup (150 LOC)
├── models/
│   ├── __init__.py                    # API schemas (50 LOC)
│   ├── generation_models.py          # Generation request/response (150 LOC)
│   ├── training_models.py             # Training request/response (100 LOC)
│   └── common_models.py               # Shared models (100 LOC)
├── routes/
│   ├── __init__.py                    # Route registration (50 LOC)
│   ├── generation.py                  # Generation endpoints (200 LOC)
│   ├── training.py                    # Training endpoints (150 LOC)
│   ├── model_management.py            # Model endpoints (150 LOC)
│   └── health.py                      # Health check endpoints (50 LOC)
├── middleware/
│   ├── __init__.py
│   ├── error_handler.py               # Error handling (100 LOC)
│   ├── logging.py                     # Request logging (100 LOC)
│   └── cors.py                        # CORS configuration (50 LOC)
└── dependencies.py                    # FastAPI dependencies (100 LOC)
```

**Estimated Total LOC:** ~1,500 (across 15 modules)

---

### Phase 4: Refactor `llm_inference.py` (Priority: HIGH)

**Current:** 2,446 LOC

**Target Structure:**
```
acestep/llm/
├── __init__.py                        # Public API (50 LOC)
├── inference_engine.py                # Core inference (200 LOC)
├── prompt_builder.py                  # Prompt construction (200 LOC)
├── streaming.py                       # Streaming logic (150 LOC)
├── tokenization.py                    # Token processing (150 LOC)
├── response_parser.py                 # Response parsing (200 LOC)
└── models/
    ├── __init__.py
    ├── model_loader.py                # Model loading (150 LOC)
    └── model_config.py                # Configuration (100 LOC)
```

**Estimated Total LOC:** ~1,200 (across 9 modules)

---

### Phase 5: Refactor `constrained_logits_processor.py` (Priority: MEDIUM)

**Current:** 2,318 LOC

**Target Structure:**
```
acestep/logits/
├── __init__.py                        # Public API (50 LOC)
├── base_processor.py                  # Base classes (150 LOC)
├── constraints/
│   ├── __init__.py
│   ├── grammar_constraint.py          # Grammar constraints (200 LOC)
│   ├── format_constraint.py           # Format constraints (200 LOC)
│   └── vocabulary_constraint.py       # Vocab constraints (200 LOC)
├── processors/
│   ├── __init__.py
│   ├── json_processor.py              # JSON processing (200 LOC)
│   ├── xml_processor.py               # XML processing (200 LOC)
│   └── custom_processor.py            # Custom processors (200 LOC)
└── validators/
    ├── __init__.py
    ├── syntax_validator.py            # Syntax validation (150 LOC)
    └── semantic_validator.py          # Semantic validation (150 LOC)
```

**Estimated Total LOC:** ~1,700 (across 13 modules)

---

### Phase 6: Refactor `results_handlers.py` (Priority: MEDIUM)

**Current:** 2,284 LOC in gradio_ui/events/

**Target Structure:**
```
acestep/gradio_ui/handlers/
├── __init__.py                        # Handler registry (50 LOC)
├── base_handler.py                    # Base handler class (100 LOC)
├── generation/
│   ├── __init__.py
│   ├── music_generation.py            # Music gen handler (200 LOC)
│   ├── cover_generation.py            # Cover gen handler (150 LOC)
│   └── audio_editing.py               # Edit handler (150 LOC)
├── training/
│   ├── __init__.py
│   ├── dataset_handler.py             # Dataset operations (200 LOC)
│   ├── training_handler.py            # Training operations (200 LOC)
│   └── export_handler.py              # Export operations (100 LOC)
├── analysis/
│   ├── __init__.py
│   ├── audio_analysis.py              # Audio analysis (150 LOC)
│   └── quality_scoring.py             # Quality scoring (150 LOC)
└── common/
    ├── __init__.py
    ├── file_handler.py                # File operations (150 LOC)
    ├── ui_updater.py                  # UI updates (100 LOC)
    └── error_handler.py               # Error handling (100 LOC)
```

**Estimated Total LOC:** ~1,800 (across 18 modules)

---

### Phase 7: Refactor `cli.py` (Priority: LOW)

**Current:** 2,006 LOC

**Target Structure:**
```
cli/
├── __init__.py                        # Main CLI entry (100 LOC)
├── commands/
│   ├── __init__.py
│   ├── generate.py                    # Generate command (200 LOC)
│   ├── train.py                       # Train command (150 LOC)
│   ├── download.py                    # Download command (100 LOC)
│   └── server.py                      # Server command (100 LOC)
└── utils/
    ├── __init__.py
    ├── arg_parser.py                  # Argument parsing (150 LOC)
    ├── config_loader.py               # Config loading (100 LOC)
    └── output_formatter.py            # Output formatting (100 LOC)
```

**Estimated Total LOC:** ~1,000 (across 11 modules)

---

## Implementation Timeline

### Sprint 1 (Week 1): Feature Flags & Critical Planning
- [ ] Implement feature flag system
- [ ] Hide LoRA training UI
- [ ] Create detailed module specifications
- [ ] Set up testing framework for refactored code

### Sprint 2 (Week 2-3): Handler Refactoring
- [ ] Create new module structure for handler
- [ ] Migrate model management code
- [ ] Migrate audio processing code
- [ ] Migrate LoRA management code

### Sprint 3 (Week 3-4): Handler Completion
- [ ] Migrate inference engine code
- [ ] Migrate metadata handling code
- [ ] Update all imports
- [ ] Comprehensive testing

### Sprint 4 (Week 5): API Server Refactoring
- [ ] Create API module structure
- [ ] Extract route handlers
- [ ] Extract API models
- [ ] Add middleware

### Sprint 5 (Week 6): LLM Inference Refactoring
- [ ] Create LLM module structure
- [ ] Separate inference, prompts, streaming
- [ ] Update dependencies

### Sprint 6 (Week 7-8): Remaining Refactoring
- [ ] Refactor constrained_logits_processor
- [ ] Refactor results_handlers
- [ ] Refactor CLI (if time permits)

### Sprint 7 (Week 9): Documentation & Testing
- [ ] Update all documentation
- [ ] Add architectural diagrams
- [ ] Create contribution guidelines
- [ ] Full integration testing

## Testing Strategy

1. **Unit Tests**: Each new module should have unit tests
2. **Integration Tests**: Test interactions between refactored modules
3. **Regression Tests**: Ensure existing functionality still works
4. **Performance Tests**: Verify no performance degradation

## Risk Mitigation

1. **Breaking Changes**:
   - Maintain backward compatibility facades
   - Add deprecation warnings
   - Version migration guide

2. **Testing Coverage**:
   - Write tests before refactoring
   - Use existing functionality as test oracle
   - Automated regression testing

3. **Dependencies**:
   - Map all dependencies before refactoring
   - Update imports incrementally
   - Use IDE refactoring tools

## Success Metrics

1. **Code Quality**:
   - No file exceeds 200 LOC
   - Each module has single responsibility
   - 80%+ test coverage

2. **Maintainability**:
   - New contributors can understand modules in < 10 minutes
   - Changes localized to single modules
   - Clear module boundaries

3. **Functionality**:
   - All existing features work
   - No performance degradation
   - WIP features properly hidden

## Rollout Strategy

1. **Phase 1**: Feature flags (immediate)
2. **Phase 2-3**: Handler refactoring (staged, with feature flags)
3. **Phase 4-6**: Other refactoring (after handler stable)
4. **Phase 7**: Documentation and polish

## Notes

- This is a living document and will be updated as refactoring progresses
- Each phase should be in a separate PR for easier review
- All changes should maintain backward compatibility where possible
- Feature flags allow us to deploy changes without exposing WIP code

---

**Last Updated:** 2026-02-06
**Status:** Planning Phase
**Owner:** Development Team
