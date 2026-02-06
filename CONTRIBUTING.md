# Contributing to ACE-Step

Thank you for your interest in contributing to ACE-Step! This guide will help you get started with contributing to the codebase.

## Table of Contents

- [Code Organization](#code-organization)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Refactoring Guidelines](#refactoring-guidelines)

## Code Organization

ACE-Step is organized into several main components:

- `acestep/` - Core library code
  - `handler/` - Business logic and model management
  - `api/` - FastAPI server implementation
  - `llm/` - Language model inference
  - `gradio_ui/` - User interface components
  - `training/` - Training and fine-tuning code
- `cli/` - Command-line interface
- `docs/` - Documentation
- `examples/` - Example scripts

For detailed architecture information, see [ARCHITECTURE.md](./docs/ARCHITECTURE.md).

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ace-step/ACE-Step-1.5.git
   cd ACE-Step-1.5
   ```

2. **Install dependencies:**
   ```bash
   # Using uv (recommended)
   uv sync
   
   # Or using pip
   pip install -e .
   ```

3. **Download models:**
   ```bash
   python -m acestep.model_downloader
   ```

## Coding Standards

### Module Size
- **Maximum 200 lines of code per module**
- If a module exceeds 200 LOC, consider splitting it
- Each module should have a single, clear responsibility

### Code Style
- Follow PEP 8 style guide
- Use type hints for function signatures
- Write docstrings for all public functions and classes
- Keep functions focused and small (prefer 10-30 lines)

### Naming Conventions
- **Functions**: `verb_noun` (e.g., `load_model`, `encode_audio`)
- **Classes**: `PascalCase` (e.g., `ModelManager`, `AudioEncoder`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_BATCH_SIZE`)
- **Private**: Prefix with underscore (e.g., `_internal_helper`)

### Function Design
- **Single Responsibility**: Each function should do one thing
- **No "and" in descriptions**: If you need "and", split the function
- **Clear inputs/outputs**: Data in, data out
- **Obvious side effects**: Document any side effects clearly

### Example

❌ **Bad: Multiple responsibilities**
```python
def load_and_process_audio(path: str) -> torch.Tensor:
    """Load audio file and normalize it."""
    audio = load_audio(path)
    audio = normalize_audio(audio)
    audio = resample_audio(audio)
    return audio
```

✅ **Good: Single responsibility**
```python
def load_audio(path: str) -> torch.Tensor:
    """Load audio file from disk."""
    return torchaudio.load(path)[0]

def normalize_audio(audio: torch.Tensor) -> torch.Tensor:
    """Normalize audio to [-1, 1] range."""
    return audio / audio.abs().max()

def resample_audio(audio: torch.Tensor, target_sr: int) -> torch.Tensor:
    """Resample audio to target sample rate."""
    return torchaudio.functional.resample(audio, orig_sr, target_sr)
```

## Making Changes

### Before You Start
1. Check existing issues and PRs to avoid duplication
2. For large changes, open an issue first to discuss
3. Create a feature branch from `main`

### Feature Flags
When adding experimental or WIP features, use feature flags:

```python
from acestep.feature_flags import Feature, is_feature_enabled

if is_feature_enabled(Feature.MY_NEW_FEATURE):
    # Your experimental code here
    pass
```

### Commit Messages
- Use clear, descriptive commit messages
- Start with a verb in present tense (e.g., "Add", "Fix", "Refactor")
- Keep the first line under 72 characters
- Add details in the body if needed

Example:
```
Add audio encoder module for handler refactoring

- Extract audio encoding logic from handler.py
- Create separate audio_encoder.py module
- Maintain backward compatibility
- Add unit tests for encoding functions
```

## Testing

### Unit Tests
- Write tests for new functionality
- Test happy path and error conditions
- Use pytest for testing

```python
def test_load_model():
    """Test model loading functionality."""
    manager = ModelManager()
    model = manager.load_model("acestep-v15-turbo")
    assert model is not None
    assert manager.is_model_loaded()
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_handler.py

# Run with coverage
pytest --cov=acestep
```

## Pull Request Process

1. **Update your branch:**
   ```bash
   git checkout main
   git pull origin main
   git checkout your-feature-branch
   git rebase main
   ```

2. **Run tests and linting:**
   ```bash
   pytest
   # Add linting if available
   ```

3. **Create pull request:**
   - Use a clear, descriptive title
   - Describe what changes you made and why
   - Reference any related issues
   - Include screenshots for UI changes

4. **Address review feedback:**
   - Respond to all comments
   - Make requested changes
   - Push updates to your branch

5. **Wait for approval:**
   - At least one maintainer approval required
   - All CI checks must pass

## Refactoring Guidelines

We are actively refactoring the codebase to improve maintainability. See [REFACTORING_PLAN.md](./docs/REFACTORING_PLAN.md) for details.

### When Refactoring

1. **Don't break existing functionality**
   - Maintain backward compatibility
   - Add deprecation warnings for old APIs
   - Provide migration guides

2. **Refactor incrementally**
   - Small, focused changes
   - One responsibility at a time
   - Keep PRs reviewable

3. **Add tests first**
   - Write tests for current behavior
   - Refactor code
   - Verify tests still pass

4. **Update documentation**
   - Update docstrings
   - Update architecture docs
   - Add migration notes

### Refactoring Checklist

- [ ] Current behavior is tested
- [ ] New module structure is clear
- [ ] Backward compatibility maintained
- [ ] All tests pass
- [ ] Documentation updated
- [ ] No increase in module LOC beyond 200

## Code Review Guidelines

### For Authors
- Keep PRs small and focused
- Provide context in PR description
- Respond to feedback constructively
- Be patient - reviews take time

### For Reviewers
- Be constructive and respectful
- Focus on code quality and maintainability
- Suggest improvements, don't demand perfection
- Approve when ready, request changes when needed

## Getting Help

- **Discord**: Join our [Discord server](https://discord.gg/PeWDxrkdj7)
- **Issues**: Open an issue for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions

## Code of Conduct

Be respectful, inclusive, and constructive. We want everyone to feel welcome contributing to ACE-Step.

---

Thank you for contributing to ACE-Step! 🎵
