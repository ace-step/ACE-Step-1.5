"""Frontend AutoPlay JavaScript loader for the Gradio UI.

Provides a helper that returns the AutoPlay head-script HTML fragment
for injection via ``gr.Blocks(head=…)``.
"""

from pathlib import Path


_ASSET_FILENAME = "autoplay.js"


def _load_autoplay_script() -> str:
    """Load the external AutoPlay JavaScript asset.

    Returns:
        JavaScript source text used by the Gradio ``head`` injection.
    """
    asset_path = Path(__file__).with_name(_ASSET_FILENAME)
    return asset_path.read_text(encoding="utf-8").strip()


def get_autoplay_head() -> str:
    """Return Gradio head HTML that injects the AutoPlay behaviour script.

    Returns:
        HTML snippet with a single ``<script>`` tag containing the AutoPlay
        JavaScript payload.
    """
    script_source = _load_autoplay_script()
    return f"<script>\n{script_source}\n</script>"
