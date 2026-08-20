"""Gradio package: web UI composition for ACE-Step controls and outputs."""

from __future__ import annotations

from typing import Any


def create_gradio_interface(*args: Any, **kwargs: Any) -> Any:
    """Create the Gradio interface using a lazy import.

    This keeps package imports lightweight for environments that run unit tests
    without Gradio installed, while preserving the existing public facade.
    """
    from acestep.ui.gradio.interfaces import create_gradio_interface as _create_gradio_interface

    return _create_gradio_interface(*args, **kwargs)
