"""Generation interface facade for advanced settings and tab builders."""

from typing import Any

from .generation_advanced_settings import create_advanced_settings_section
from .generation_defaults import compute_init_defaults
from .generation_service_config import (
    create_service_config_content as _create_service_config_content,
    create_service_config_section,
)
from .generation_tab_section import create_generation_tab_section


def _compute_init_defaults(
    dit_handler: Any,
    llm_handler: Any,
    init_params: dict[str, Any] | None,
    language: str,
) -> dict[str, Any]:
    """Backward-compatible wrapper for legacy private defaults helper signature.

    Args:
        dit_handler: Unused legacy placeholder to preserve old call signature.
        llm_handler: Unused legacy placeholder to preserve old call signature.
        init_params: Optional initialization dictionary from CLI/startup.
        language: Default UI language code.

    Returns:
        A normalized defaults dictionary used by generation UI builders.
    """

    _ = (dit_handler, llm_handler)
    return compute_init_defaults(init_params=init_params, language=language)


def create_generation_section(
    dit_handler: Any,
    llm_handler: Any,
    init_params: dict[str, Any] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Build the legacy combined generation section for backward compatibility.

    Args:
        dit_handler: DiT service handler used to build generation controls.
        llm_handler: LM service handler used to build generation controls.
        init_params: Optional initialization state for pre-populating controls.
        language: UI language code.

    Returns:
        A merged component map containing both advanced settings and generation-tab controls.
    """

    settings_section = create_advanced_settings_section(
        dit_handler=dit_handler,
        llm_handler=llm_handler,
        init_params=init_params,
        language=language,
    )
    generation_tab_section = create_generation_tab_section(
        dit_handler=dit_handler,
        llm_handler=llm_handler,
        init_params=init_params,
        language=language,
    )
    merged: dict[str, Any] = {}
    merged.update(settings_section)
    merged.update(generation_tab_section)
    return merged
