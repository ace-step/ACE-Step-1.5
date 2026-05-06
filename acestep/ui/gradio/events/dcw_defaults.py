"""Think-aware DCW default values shared by Gradio event handlers."""


THINK_DCW_DEFAULTS = {
    "mode": "double",
    "scaler": 0.02,
    "high_scaler": 0.06,
}
NON_THINK_DCW_DEFAULTS = {
    "mode": "double",
    "scaler": 0.05,
    "high_scaler": 0.02,
}


def get_dcw_defaults_for_think(think_enabled: bool) -> dict[str, float | str]:
    """Return DCW defaults for the current Think state.

    Args:
        think_enabled: Whether LM Think mode is enabled.

    Returns:
        Defaults for ``dcw_mode``, ``dcw_scaler``, and ``dcw_high_scaler``.
    """
    return THINK_DCW_DEFAULTS if think_enabled else NON_THINK_DCW_DEFAULTS
