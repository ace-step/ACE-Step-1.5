import os
from typing import Tuple

import torchaudio
from loguru import logger


def load_lyrics_file(audio_path: str) -> Tuple[str, bool]:
    """Load lyrics from a .txt file with the same name as the audio file."""
    base_path = os.path.splitext(audio_path)[0]
    lyrics_path = base_path + ".txt"

    if os.path.exists(lyrics_path):
        try:
            with open(lyrics_path, "r", encoding="utf-8") as f:
                lyrics_content = f.read().strip()

            if lyrics_content:
                logger.info(f"Loaded lyrics from {lyrics_path}")
                return lyrics_content, True
            logger.warning(f"Lyrics file is empty: {lyrics_path}")
            return "", False
        except Exception as e:
            logger.warning(f"Failed to read lyrics file {lyrics_path}: {e}")
            return "", False

    return "", False


def get_audio_duration(audio_path: str) -> int:
    """Get the duration of an audio file in seconds."""
    try:
        info = torchaudio.info(audio_path)
        return int(info.num_frames / info.sample_rate)
    except Exception as e:
        logger.warning(f"Failed to get duration for {audio_path}: {e}")
        return 0
