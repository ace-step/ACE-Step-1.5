# AGENTS.md

Guidance for AI coding agents working in `ace-step/ACE-Step-1.5`.

This document is aligned with the intent from:
- Discussion #408: functional decomposition to reduce risk from large mixed-responsibility files.
- Discussion #365: low-risk contribution workflow, minimal scope, and review rigor.

## Primary Objectives

1. Keep changes safe and reviewable.
2. Prefer small, maintainable, decomposed modules.
3. Preserve behavior outside the target fix.
4. Validate with focused Python unit tests.

## Build, Lint, and Test Commands

```bash
# Install dependencies
uv sync

# Run all tests (unittest-based, discovery in */*_test.py and test_*.py)
uv run python -m unittest discover -s . -p "*_test.py"
uv run python -m unittest discover -s . -p "test_*.py"

# Run a single test file
uv run python -m unittest acestep.training.test_lora_utils

# Run a specific test class
uv run python -m unittest acestep.training.test_lora_utils.TestUnwrapDecoder

# Run a single test method
uv run python -m unittest acestep.training.test_lora_utils.TestUnwrapDecoder.test_returns_module_directly

# Run all tests in a directory
uv run python -m unittest discover -s acestep/training -p "*_test.py"
```

## Scope and Change Control (Required)

- Solve one problem per task/PR.
- Keep edits minimal: touch only files/functions required for the requested change.
- Do not make drive-by refactors, formatting sweeps, or opportunistic cleanups.
- Do not alter non-target hardware/runtime paths (CPU/CUDA/MPS/XPU) unless required by the task.
- If any cross-path change is necessary, isolate it and justify it in the PR notes.
- Preserve existing public interfaces unless the task explicitly requires an interface change.

## Decomposition and Module Size Policy

- Prefer single-responsibility modules with clear boundaries.
- Target module size:
  - Optimal: `<= 150` LOC
  - Hard cap: `200` LOC
- Function decomposition rules:
  - Do one thing at a time; if a function description naturally contains "and", split it.
  - Split by responsibility, not by convenience.
  - Keep data flow explicit (`data in, data out`); side effects must be obvious and deliberate.
  - Push decisions up and push work down (orchestration at higher layers, execution details in lower layers).
  - The call graph should read clearly from top-level orchestration to leaf operations.
- If a module would exceed `200` LOC:
  - Split by responsibility before merging, or
  - Add a short justification in PR notes and include a concrete follow-up split plan.
- Keep orchestrator/facade modules thin. Move logic into focused helpers/services.
- Preserve stable facade imports when splitting large files so external callers are not broken.

## Python Unit Testing Expectations

- Add or update tests for every behavior change and bug fix.
- Match repository conventions:
  - Use `unittest`-style tests.
  - Name test files as `*_test.py` or `test_*.py`.
- Keep tests deterministic, fast, and scoped to changed behavior.
- Use `unittest.mock.MagicMock` and `unittest.mock.patch` for mocking.
- Mock GPU, filesystem, network, and external services where possible.
- If a change requires mocking a large portion of the system to test one unit, treat that as a decomposition smell and refactor boundaries.
- Include at least:
  - One success-path test.
  - One regression/edge-case test for the bug being fixed.
  - One non-target behavior check when relevant.
- Run targeted tests locally before submitting.

## Code Style Guidelines

- **Python version**: 3.11-3.12
- **Indentation**: 4 spaces (no tabs)
- **Line length**: Maximum 100 characters (recommended). See `pyproject.toml` for configured formatter limits. Exceptions allowed for URLs and long strings where wrapping would hurt readability.
- **Strings**: Double quotes `"` preferred
- **Imports**: Group by type (stdlib, third-party, local), sort alphabetically within groups

```python
# Example import ordering
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import torch
import torch.nn as nn

from acestep.training.lora_injection import inject_lora_into_dit
```

**Naming conventions**:
- `snake_case` for functions, variables, and module names
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Prefix private/internal names with underscore: `_internal_func`, `_private_var`

**Type hints**: Add type annotations for new/modified functions when practical.

**Docstrings**: Mandatory for all modules, classes, and public functions. Use concise format:

```python
def inject_lora_into_dit(
    dit: nn.Module,
    config: dict[str, Any],
    target_modules: list[str],
) -> nn.Module:
    """Inject LoRA adapters into DiT model for parameter-efficient fine-tuning.

    Args:
        dit: The Diffusion Transformer model to modify.
        config: LoRA configuration dictionary.
        target_modules: List of module names to apply LoRA to.

    Returns:
        The modified DiT model with LoRA adapters injected.
    """
```

**Error handling**:
- Avoid bare `except:` clauses; catch specific exceptions
- Use custom exceptions for domain errors
- Log errors with `loguru.logger` (not `print()`)
- Let exceptions propagate for truly exceptional conditions

**Logging**:
- Use `from loguru import logger` and `logger.info()`, `logger.error()`, etc.
- Keep logs actionable and debug-level for development
- Avoid `print()` in committed code except CLI output

**Multi-platform support** (CUDA, ROCm, Intel XPU, MPS, MLX, CPU):
- Use `gpu_config.py` for hardware detection
- Do not alter non-target platform paths unless explicitly required
- Changes to CUDA code should not break MPS/XPU/CPU paths

## Feature Gating and WIP Safety

- Do not expose unfinished or non-functional user-facing flows by default.
- Gate WIP or unstable UI/API paths behind explicit feature/release flags.
- Keep default behavior stable; "coming soon" paths must not appear as usable functionality unless they are operational and tested.

## Python Coding Best Practices

- Use explicit, readable code over clever shortcuts.
- Docstrings are mandatory for all new or modified Python modules, classes, and functions.
- Docstrings must be concise and include purpose plus key inputs/outputs (and raised exceptions when relevant).
- Add type hints for new/modified functions when practical.
- Keep functions focused and short; extract helpers instead of nesting complexity.
- Use clear names that describe behavior, not implementation trivia.
- Prefer pure functions for logic-heavy paths where possible.
- Avoid duplicated logic, but do not introduce broad abstractions too early; prefer simple local duplication over unstable premature abstraction.
- Handle errors explicitly; avoid bare `except`.
- Keep logging actionable; avoid noisy logs and `print` debugging in committed code.
- Avoid hidden state and unintended side effects.
- Write comments only where intent is non-obvious; keep comments concise and technical.

## AI-Agent Workflow (Recommended)

1. Understand the task and define explicit in-scope/out-of-scope boundaries.
2. Propose a minimal patch plan before editing.
3. Implement the smallest viable change.
4. Add/update focused tests.
5. Self-review only changed hunks for regressions and scope creep.
6. Summarize risk, validation, and non-target impact in PR notes.

## PR Readiness Checklist

- [ ] Change is tightly scoped to one problem.
- [ ] Non-target paths are unchanged, or changes are explicitly justified.
- [ ] New/updated tests cover changed behavior and edge cases.
- [ ] No unrelated refactor/formatting churn.
- [ ] Required docstrings are present for all new/modified modules, classes, and functions.
- [ ] WIP/unstable functionality is feature-flagged and not exposed as default-ready behavior.
- [ ] Module LOC policy is met (`<=150` target, `<=200` hard cap or justified exception).
