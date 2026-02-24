"""AST utility helpers for generation interface decomposition contract tests."""

import ast
from pathlib import Path


INTERFACES_DIR = Path(__file__).resolve().parent
WIRING_DIR = INTERFACES_DIR.parent / "events" / "wiring"


def load_module(module_name: str) -> ast.Module:
    """Parse and return AST for a generation interface module.

    Args:
        module_name: Filename under ``acestep/ui/gradio/interfaces`` to parse.

    Returns:
        Parsed ``ast.Module`` tree for the requested module.
    """

    path = INTERFACES_DIR / module_name
    return ast.parse(path.read_text(encoding="utf-8"))


def call_name(node: ast.AST) -> str | None:
    """Extract a simple call-target name from an AST call function node.

    Args:
        node: AST node representing a call target expression.

    Returns:
        The simple function/attribute name when resolvable; otherwise ``None``.
    """

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def collect_return_dict_keys(module_name: str, function_name: str) -> set[str]:
    """Collect string keys from dict literals assigned/returned in a function.

    Args:
        module_name: Module filename under ``interfaces`` to inspect.
        function_name: Function name whose body should be scanned.

    Returns:
        Set of string keys found in literal dict assignments/updates/returns.
    """

    module = load_module(module_name)
    function_node = None
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            function_node = node
            break
    if function_node is None:
        raise AssertionError(f"{function_name} not found in {module_name}")

    keys: set[str] = set()
    for node in ast.walk(function_node):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update":
            if node.args and isinstance(node.args[0], ast.Dict):
                for key in node.args[0].keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    return keys


def collect_generation_section_keys_used_by_wiring() -> set[str]:
    """Collect generation-section keys referenced by wiring modules.

    Args:
        None.

    Returns:
        Set of ``generation_section[...]`` keys consumed by wiring modules.
    """

    keys: set[str] = set()
    for path in WIRING_DIR.glob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if not isinstance(node, ast.Subscript):
                continue
            if not isinstance(node.value, ast.Name) or node.value.id != "generation_section":
                continue
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                keys.add(node.slice.value)
    return keys
