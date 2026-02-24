"""
Handler caching for Streamlit.

Creates / caches AceStepHandler and LLMHandler instances and exposes
a single ``initialize_models()`` that loads weights on demand.
"""
import os
import sys
from typing import Optional, Tuple
from pathlib import Path

import streamlit as st
from loguru import logger

# Ensure ACE-Step repo is on Python path
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ------------------------------------------------------------------
# Lightweight handler singletons (no model weights loaded yet)
# ------------------------------------------------------------------

@st.cache_resource
def get_dit_handler():
    """Return a cached AceStepHandler instance (uninitialised)."""
    try:
        from acestep.handler import AceStepHandler
        logger.info("Creating AceStepHandler instance...")
        return AceStepHandler()
    except Exception as exc:
        logger.error(f"Failed to create AceStepHandler: {exc}")
        return None


@st.cache_resource
def get_llm_handler():
    """Return a cached LLMHandler instance (uninitialised)."""
    try:
        from acestep.llm_inference import LLMHandler
        logger.info("Creating LLMHandler instance...")
        return LLMHandler()
    except Exception as exc:
        logger.error(f"Failed to create LLMHandler: {exc}")
        return None


@st.cache_resource
def get_dataset_handler():
    """Return a cached DatasetHandler instance."""
    try:
        from acestep.dataset_handler import DatasetHandler
        logger.info("Creating DatasetHandler instance...")
        return DatasetHandler()
    except Exception as exc:
        logger.error(f"Failed to create DatasetHandler: {exc}")
        return None


# ------------------------------------------------------------------
# Model initialisation helpers
# ------------------------------------------------------------------

def is_dit_ready() -> bool:
    """Check whether DiT model weights are loaded."""
    handler = get_dit_handler()
    return handler is not None and handler.model is not None


def is_llm_ready() -> bool:
    """Check whether LLM model weights are loaded."""
    handler = get_llm_handler()
    return handler is not None and handler.llm_initialized


def initialize_dit(
    config_path: str = "acestep-v15-turbo",
    device: str = "auto",
    offload_to_cpu: bool = False,
    compile_model: bool = False,
) -> Tuple[str, bool]:
    """Load DiT model weights into the cached handler.

    Returns:
        (status_message, success)
    """
    handler = get_dit_handler()
    if handler is None:
        return "AceStepHandler could not be created", False

    project_root = str(_project_root)
    use_flash = handler.is_flash_attention_available(device)

    status, ok = handler.initialize_service(
        project_root=project_root,
        config_path=config_path,
        device=device,
        use_flash_attention=use_flash,
        compile_model=compile_model,
        offload_to_cpu=offload_to_cpu,
    )
    return status, ok


def initialize_llm(
    lm_model_path: str = "acestep-5Hz-lm-1.7B",
    backend: str = "mlx",
    device: str = "auto",
    offload_to_cpu: bool = False,
) -> Tuple[str, bool]:
    """Load LLM model weights into the cached handler.

    Returns:
        (status_message, success)
    """
    handler = get_llm_handler()
    if handler is None:
        return "LLMHandler could not be created", False

    checkpoint_dir = str(_project_root / "checkpoints")

    # Ensure model is downloaded
    try:
        from acestep.model_downloader import ensure_lm_model
        dl_ok, dl_msg = ensure_lm_model(
            model_name=lm_model_path,
            checkpoints_dir=checkpoint_dir,
        )
        if not dl_ok:
            logger.warning(f"LM model download issue: {dl_msg}")
    except Exception as exc:
        logger.warning(f"LM model download check failed: {exc}")

    status, ok = handler.initialize(
        checkpoint_dir=checkpoint_dir,
        lm_model_path=lm_model_path,
        backend=backend,
        device=device,
        offload_to_cpu=offload_to_cpu,
    )
    return status, ok


def clear_handlers() -> None:
    """Clear all cached handlers (forces re-creation)."""
    st.cache_resource.clear()
