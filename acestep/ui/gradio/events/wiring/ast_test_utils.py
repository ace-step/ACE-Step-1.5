"""Shared AST parsing helpers for wiring contract tests."""

import ast
from pathlib import Path


def load_module_ast(module_path: Path) -> ast.Module:
    """Return the parsed AST module for the provided source path."""

    return ast.parse(module_path.read_text(encoding="utf-8"))


def subscript_key(node: ast.Subscript) -> str | None:
    """Return constant key value from a simple subscript expression."""

    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return None
