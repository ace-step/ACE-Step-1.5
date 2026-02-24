"""Shared AST helpers for decomposition contract tests."""

import ast
from pathlib import Path


_EVENTS_INIT_PATH = Path(__file__).resolve().parents[1] / "__init__.py"
_MODE_WIRING_PATH = Path(__file__).resolve().with_name("generation_mode_wiring.py")
_METADATA_FILE_WIRING_PATH = Path(__file__).resolve().with_name(
    "generation_metadata_file_wiring.py"
)
_RUN_WIRING_PATH = Path(__file__).resolve().with_name("generation_run_wiring.py")
_BATCH_NAV_WIRING_PATH = Path(__file__).resolve().with_name(
    "generation_batch_navigation_wiring.py"
)
_RESULTS_DISPLAY_WIRING_PATH = Path(__file__).resolve().with_name(
    "results_display_wiring.py"
)
_TRAINING_DATASET_BUILDER_WIRING_PATH = Path(__file__).resolve().with_name(
    "training_dataset_builder_wiring.py"
)
_TRAINING_DATASET_PREPROCESS_WIRING_PATH = Path(__file__).resolve().with_name(
    "training_dataset_preprocess_wiring.py"
)
_TRAINING_RUN_WIRING_PATH = Path(__file__).resolve().with_name("training_run_wiring.py")
_TRAINING_LOKR_WIRING_PATH = Path(__file__).resolve().with_name("training_lokr_wiring.py")


def load_setup_event_handlers_node() -> ast.FunctionDef:
    """Return the AST node for ``setup_event_handlers``."""

    source = _EVENTS_INIT_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "setup_event_handlers":
            return node
    raise AssertionError("setup_event_handlers not found")


def load_setup_training_event_handlers_node() -> ast.FunctionDef:
    """Return the AST node for ``setup_training_event_handlers``."""

    source = _EVENTS_INIT_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "setup_training_event_handlers":
            return node
    raise AssertionError("setup_training_event_handlers not found")


def load_generation_mode_wiring_node() -> ast.FunctionDef:
    """Return the AST node for ``register_generation_mode_handlers``."""

    source = _MODE_WIRING_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "register_generation_mode_handlers":
            return node
    raise AssertionError("register_generation_mode_handlers not found")


def load_generation_metadata_file_wiring_module() -> ast.Module:
    """Return the parsed AST module for metadata file-load wiring."""

    source = _METADATA_FILE_WIRING_PATH.read_text(encoding="utf-8")
    return ast.parse(source)


def load_generation_run_wiring_node() -> ast.FunctionDef:
    """Return the AST node for ``register_generation_run_handlers``."""

    source = _RUN_WIRING_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "register_generation_run_handlers":
            return node
    raise AssertionError("register_generation_run_handlers not found")


def load_generation_batch_navigation_wiring_node() -> ast.FunctionDef:
    """Return the AST node for ``register_generation_batch_navigation_handlers``."""

    source = _BATCH_NAV_WIRING_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "register_generation_batch_navigation_handlers":
            return node
    raise AssertionError("register_generation_batch_navigation_handlers not found")


def load_results_display_wiring_module() -> ast.Module:
    """Return the parsed AST module for results display/save wiring."""

    source = _RESULTS_DISPLAY_WIRING_PATH.read_text(encoding="utf-8")
    return ast.parse(source)


def load_training_run_wiring_module() -> ast.Module:
    """Return the parsed AST module for ``training_run_wiring.py``."""

    source = _TRAINING_RUN_WIRING_PATH.read_text(encoding="utf-8")
    return ast.parse(source)


def load_training_lokr_wiring_module() -> ast.Module:
    """Return the parsed AST module for ``training_lokr_wiring.py``."""

    source = _TRAINING_LOKR_WIRING_PATH.read_text(encoding="utf-8")
    return ast.parse(source)


def load_training_dataset_preprocess_wiring_module() -> ast.Module:
    """Return the parsed AST module for training dataset/preprocess wiring."""

    source = _TRAINING_DATASET_PREPROCESS_WIRING_PATH.read_text(encoding="utf-8")
    return ast.parse(source)


def load_training_dataset_builder_wiring_module() -> ast.Module:
    """Return the parsed AST module for training dataset-builder wiring."""

    source = _TRAINING_DATASET_BUILDER_WIRING_PATH.read_text(encoding="utf-8")
    return ast.parse(source)


def call_name(node: ast.AST) -> str | None:
    """Extract a simple function name from a call node target."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
