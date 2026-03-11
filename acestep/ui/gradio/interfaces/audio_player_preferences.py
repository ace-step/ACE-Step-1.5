"""Frontend audio-player preference helpers for the Gradio UI."""

from pathlib import Path


_ASSET_FILENAME = "audio_player_preferences.js"


def _load_preferences_script() -> str:
    """Load the external audio-preferences JavaScript asset.

    Returns:
        JavaScript source text used by the Gradio ``head`` injection.
    """
    asset_path = Path(__file__).with_name(_ASSET_FILENAME)
    return asset_path.read_text(encoding="utf-8").strip()


def get_audio_player_preferences_head() -> str:
    """Return Gradio head HTML that injects audio preference behavior.

    Returns:
        HTML snippet with a single ``<script>`` tag containing the externalized
        audio preference JavaScript payload.
    """
    script_source = _load_preferences_script()
    return f"<script>\n{script_source}\n</script>"
