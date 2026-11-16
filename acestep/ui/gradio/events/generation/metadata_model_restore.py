"""Restore the DiT / LM / VAE selectors from a loaded JSON metadata file.

Old JSON files without model keys leave the selectors unchanged. Models are
only selected in the UI; the user still has to click "Initialize Service".
"""

import json
from typing import Any, Callable

import gradio as gr
from loguru import logger

from acestep.ui.gradio.events.generation.model_config import update_model_type_settings
from acestep.ui.gradio.events.results.model_info import collect_model_info
from acestep.ui.gradio.i18n import t

# Indexes of update_model_type_settings() outputs that carry a value which is
# also restored from the JSON (inference_steps, shift).
_LOADED_VALUE_INDEXES = (0, 3)
# init_service_wrapper() returns status, button and accordion before the
# model-type settings.
_INIT_SETTINGS_OFFSET = 3


def read_metadata_dict(file_obj: Any) -> dict | None:
    """Read a JSON metadata file uploaded through Gradio.

    Args:
        file_obj: Gradio file object or path, may be ``None``.

    Returns:
        The parsed dict, or ``None`` when missing or unreadable.
    """
    if file_obj is None:
        return None
    path = getattr(file_obj, "name", file_obj)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        logger.warning(f"Cannot read metadata for model restore: {exc}")
        return None
    return data if isinstance(data, dict) else None


def _available(list_choices: Callable[[], list]) -> list:
    """Return available model names, or an empty list when listing fails."""
    try:
        return list(list_choices())
    except (OSError, RuntimeError, AttributeError) as exc:
        logger.warning(f"Cannot list available models: {exc}")
        return []


def _list_vae_variants() -> list:
    """Return the available VAE variants."""
    from acestep.model_downloader import list_available_vae_variants

    return list_available_vae_variants()


def _model_catalog(dit_handler: Any, llm_handler: Any) -> dict[str, Callable[[], list]]:
    """Map each metadata model key to the function listing its choices."""
    return {
        "dit_model": dit_handler.get_available_acestep_v15_models,
        "lm_model": getattr(llm_handler, "get_available_5hz_lm_models", lambda: []),
        "vae_checkpoint": _list_vae_variants,
    }


def restore_models_from_metadata(
    file_obj: Any, current_dit: str | None, dit_handler: Any, llm_handler: Any
) -> tuple:
    """Build selector updates for the models recorded in a JSON metadata file.

    Args:
        file_obj: Uploaded JSON file.
        current_dit: Current value of the DiT selector.
        dit_handler: DiT handler (lists models, reports the loaded one).
        llm_handler: LLM handler, may be ``None``.

    Returns:
        Updates for (config_path, lm_model_path, vae_checkpoint), then two
        bools: ``True`` when the DiT selector changes value, and ``True`` when
        the JSON models differ from the loaded ones. Both tell the model-type
        defaults not to overwrite the values loaded from the JSON.
    """
    metadata = read_metadata_dict(file_obj) or {}
    loaded = collect_model_info(dit_handler, llm_handler)
    updates, differs = [], []
    for key, list_choices in _model_catalog(dit_handler, llm_handler).items():
        name = metadata.get(key)
        if not name:
            updates.append(gr.skip())
        elif name in _available(list_choices):
            updates.append(name)
            if name != loaded.get(key):
                differs.append(name)
        else:
            updates.append(gr.skip())
            gr.Warning(t("messages.metadata_model_not_found", model=name))
    if differs:
        gr.Warning(t("messages.metadata_models_differ", models=", ".join(differs)))
    dit_changes = isinstance(updates[0], str) and updates[0] != current_dit
    return (*updates, dit_changes, bool(differs))


def update_model_type_settings_keeping_loaded(
    config_path: str | None, current_mode: str | None, keep_loaded_values: bool
) -> tuple:
    """Apply model-type UI settings, optionally keeping values loaded from JSON.

    Args:
        config_path: Selected DiT model.
        current_mode: Current generation mode.
        keep_loaded_values: ``True`` right after a JSON load changed the DiT
            selector; steps and shift then keep the loaded values.

    Returns:
        The ``update_model_type_settings`` updates followed by ``False`` to
        reset the keep-loaded flag.
    """
    updates = update_model_type_settings(config_path, current_mode)
    if keep_loaded_values:
        updates = _without_values(updates, _LOADED_VALUE_INDEXES)
    return (*updates, False)


def keep_loaded_values_after_init(init_result: tuple, keep_loaded_values: bool) -> tuple:
    """Keep steps and shift from a loaded JSON in the Initialize Service result.

    Args:
        init_result: Return value of ``init_service_wrapper``.
        keep_loaded_values: ``True`` when the last JSON load selected models
            different from the loaded ones.

    Returns:
        ``init_result`` (without the steps/shift values when the flag is set)
        followed by ``False`` to reset the flag.
    """
    if keep_loaded_values:
        indexes = [_INIT_SETTINGS_OFFSET + index for index in _LOADED_VALUE_INDEXES]
        init_result = _without_values(init_result, indexes)
    return (*init_result, False)


def _without_values(updates: tuple, indexes: list[int] | tuple[int, ...]) -> list:
    """Return a copy of ``updates`` where the given updates do not set a value."""
    updates = list(updates)
    for index in indexes:
        update = dict(updates[index])
        update.pop("value", None)
        updates[index] = update
    return updates
