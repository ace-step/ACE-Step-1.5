"""Shared helpers for help-content unit tests."""

import sys
from unittest.mock import MagicMock


def ensure_gradio_mocked() -> None:
    """Ensure a mock gradio module exists for package imports in tests."""
    if "gradio" not in sys.modules:
        sys.modules["gradio"] = MagicMock()
