"""Collect the names of the models used for a generation.

The names are stored in each saved JSON metadata file so that a song can be
recreated with the same DiT, LM and VAE.
"""

import os
from typing import Any

MODEL_INFO_KEYS = ("dit_model", "lm_model", "vae_checkpoint")


def _model_name(path: Any) -> str | None:
    """Return the folder name of a model path, or ``None`` when empty.

    Args:
        path: Model path or model name.

    Returns:
        The last path component, or ``None`` for empty values.
    """
    if not path:
        return None
    return os.path.basename(os.path.normpath(str(path)))


def _dit_model_info(dit_handler: Any) -> dict[str, str | None]:
    """Return DiT model and VAE names from the last service initialization.

    Args:
        dit_handler: DiT handler; ``last_init_params`` may be ``None``.

    Returns:
        Dict with ``dit_model`` and ``vae_checkpoint`` (``None`` when unknown).
    """
    init_params = getattr(dit_handler, "last_init_params", None) or {}
    return {
        "dit_model": _model_name(init_params.get("config_path")),
        "vae_checkpoint": init_params.get("vae_checkpoint") or None,
    }


def _lm_model_name(llm_handler: Any) -> str | None:
    """Return the loaded 5Hz LM name, or ``None`` when the LM is not initialized.

    Args:
        llm_handler: LLM handler, may be ``None``.

    Returns:
        The LM model name or ``None``.
    """
    if llm_handler is None or not getattr(llm_handler, "llm_initialized", False):
        return None
    init_config = getattr(llm_handler, "_last_initialize_config", None) or {}
    lm_path = init_config.get("lm_model_path") or getattr(llm_handler, "_lm_full_model_path", None)
    return _model_name(lm_path)


def collect_model_info(dit_handler: Any, llm_handler: Any) -> dict[str, str | None]:
    """Return the currently loaded DiT, LM and VAE names.

    Args:
        dit_handler: DiT handler.
        llm_handler: LLM handler, may be ``None``.

    Returns:
        Dict with keys ``dit_model``, ``lm_model`` and ``vae_checkpoint``.
        Unknown values are ``None``.
    """
    info = _dit_model_info(dit_handler)
    info["lm_model"] = _lm_model_name(llm_handler)
    return {key: info.get(key) for key in MODEL_INFO_KEYS}
