from typing import Any, Optional

from loguru import logger


def get_audio_codes(audio_path: str, dit_handler) -> Optional[str]:
    """Encode audio to get semantic codes for LLM understanding."""
    try:
        if not hasattr(dit_handler, "convert_src_audio_to_codes"):
            logger.error("DiT handler missing convert_src_audio_to_codes method")
            return None

        codes_string = dit_handler.convert_src_audio_to_codes(audio_path)

        if codes_string and not codes_string.startswith("❌"):
            return codes_string
        logger.warning(f"Failed to convert audio to codes: {codes_string}")
        return None
    except Exception:
        logger.exception(f"Error encoding audio {audio_path}")
        return None


def parse_int(value: Any) -> Optional[int]:
    """Safely parse an integer value."""
    if value is None or value == "N/A" or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
