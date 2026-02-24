import json
import os
from typing import Dict, Any, Tuple

from loguru import logger

from acestep.training.path_safety import safe_path


def _read_text_file(path: str) -> Tuple[str, bool]:
    """Read a text file; return (content.strip(), True) if present and non-empty.

    Args:
        path: Already-validated file path.
    """
    validated = safe_path(path)
    if not os.path.exists(validated):
        return "", False
    try:
        with open(validated, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return content, True
        return "", False
    except Exception as e:
        logger.warning(f"Failed to read {validated}: {e}")
        return "", False


def load_caption_file(audio_path: str) -> Tuple[str, bool]:
    """Load caption from <basename>.caption.txt (explicit convention)."""
    validated = safe_path(audio_path)
    base_path = os.path.splitext(validated)[0]
    caption_path = base_path + ".caption.txt"
    content, ok = _read_text_file(caption_path)
    if ok:
        logger.debug(f"Loaded caption from {caption_path}")
    return content, ok


def load_json_metadata(audio_path: str) -> Tuple[Dict[str, Any], bool]:
    """Load metadata from <basename>.json.

    Expected JSON structure:
        {
            "caption": "",
            "bpm": 120,
            "keyscale": "C major",
            "timesignature": "4",
            "language": "ja"
        }

    All fields are optional.
    """
    validated = safe_path(audio_path)
    base_path = os.path.splitext(validated)[0]
    json_path = base_path + ".json"
    if not os.path.exists(json_path):
        return {}, False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            logger.debug(f"Loaded JSON metadata from {json_path}")
            return data, True
        return {}, False
    except Exception as e:
        logger.warning(f"Failed to read {json_path}: {e}")
        return {}, False


def load_lyrics_file(audio_path: str) -> Tuple[str, bool]:
    """Load lyrics from <basename>.lyrics.txt, then fallback to <basename>.txt for backward compat."""
    validated = safe_path(audio_path)
    base_path = os.path.splitext(validated)[0]
    for suffix in (".lyrics.txt", ".txt"):
        path = base_path + suffix
        content, ok = _read_text_file(path)
        if ok:
            if suffix == ".lyrics.txt":
                logger.debug(f"Loaded lyrics from {path}")
            else:
                logger.debug(f"Loaded lyrics from {path} (legacy .txt)")
            return content, True
    return "", False


def get_audio_duration(audio_path: str) -> int:
    """Get the duration of an audio file in seconds."""
    validated = safe_path(audio_path)
    # Primary: torchcodec (ships with torchaudio >=2.9, supports all ffmpeg formats)
    # Note: torchcodec is optional on ROCM/Intel platforms due to CUDA dependencies
    try:
        from torchcodec.decoders import AudioDecoder
        decoder = AudioDecoder(validated)
        return int(decoder.metadata.duration_seconds)
    except ImportError:
        logger.debug("torchcodec not available (expected on ROCM/Intel platforms), using soundfile fallback")
    except Exception as e:
        logger.debug(f"torchcodec failed for {validated}: {e}, trying soundfile")
    # Fallback: soundfile (fast for wav/flac/ogg, works on all platforms)
    try:
        import soundfile as sf
        info = sf.info(validated)
        return int(info.duration)
    except Exception as e:
        logger.warning(f"Failed to get duration for {validated}: {e}")
        return 0
