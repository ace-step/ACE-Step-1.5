"""Download and precheck helpers for service initialization."""

from pathlib import Path
from typing import Optional, Tuple

from loguru import logger

from acestep.model_downloader import (
    check_main_model_exists,
    check_model_exists,
    ensure_dit_model,
    ensure_main_model,
)


class InitServiceDownloadsMixin:
    """Helpers that validate and fetch required model checkpoints."""

    def _ensure_models_present(
        self,
        *,
        checkpoint_path: Path,
        config_path: str,
        prefer_source: Optional[str],
    ) -> Optional[Tuple[str, bool]]:
        """Ensure required checkpoint assets exist locally, downloading when missing."""
        if not check_main_model_exists(checkpoint_path):
            logger.info("[initialize_service] Main model not found, starting auto-download...")
            success, msg = ensure_main_model(checkpoint_path, prefer_source=prefer_source)
            if not success:
                return f"ERROR: Failed to download main model: {msg}", False
            logger.info(f"[initialize_service] {msg}")

        if config_path == "":
            logger.warning(
                "[initialize_service] Empty config_path; pass None to use the default model."
            )

        if not check_model_exists(config_path, checkpoint_path):
            logger.info(f"[initialize_service] DiT model '{config_path}' not found, starting auto-download...")
            success, msg = ensure_dit_model(config_path, checkpoint_path, prefer_source=prefer_source)
            if not success:
                return f"ERROR: Failed to download DiT model '{config_path}': {msg}", False
            logger.info(f"[initialize_service] {msg}")

        return None

    @staticmethod
    def _sync_model_code_if_needed(config_path: str, checkpoint_path: Path) -> None:
        """Sync model-side python files when checkpoint code metadata diverges."""
        from acestep.model_downloader import _check_code_mismatch, _sync_model_code_files

        mismatched = _check_code_mismatch(config_path, checkpoint_path)
        if mismatched:
            logger.warning(
                f"[initialize_service] Model code mismatch detected for '{config_path}': "
                f"{mismatched}. Auto-syncing from acestep/models/..."
            )
            _sync_model_code_files(config_path, checkpoint_path)
            logger.info("[initialize_service] Model code files synced successfully.")
