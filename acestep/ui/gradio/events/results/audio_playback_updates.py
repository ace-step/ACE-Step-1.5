"""Audio playback update helpers for Gradio result players.

These helpers standardize audio update payloads so playback always rewinds to
the start of the track when a new value is assigned.
"""

from typing import Any, Optional


def build_audio_slot_update(
    gr_module: Any,
    audio_path: Optional[str],
    *,
    label: Optional[str] = None,
    interactive: Optional[bool] = None,
) -> Any:
    """Build an audio slot update that always rewinds playback to 0.

    Args:
        gr_module: Module/object exposing ``update(**kwargs)``.
        audio_path: Filepath for the audio component, or ``None`` to clear.
        label: Optional component label override.
        interactive: Optional component interactivity override.

    Returns:
        The framework-specific update object returned by ``gr_module.update``.
    """
    update_kwargs = {
        "value": audio_path,
        "playback_position": 0,
    }
    if label is not None:
        update_kwargs["label"] = label
    if interactive is not None:
        update_kwargs["interactive"] = interactive
    return gr_module.update(**update_kwargs)
