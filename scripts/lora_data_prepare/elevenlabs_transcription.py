"""ElevenLabs Scribe transcription service.

Transcribe audio to lyrics text using ElevenLabs Scribe API.
Uses word-level timestamps for intelligent line breaking,
then outputs plain text without timestamps.
"""

import os
from typing import Optional, List, Dict, Any
from pathlib import Path

import requests


def is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0x20000 <= cp <= 0x2A6DF or 0x2A700 <= cp <= 0x2B73F or
            0x2B740 <= cp <= 0x2B81F or 0x2B820 <= cp <= 0x2CEAF or
            0xF900 <= cp <= 0xFAFF or 0x2F800 <= cp <= 0x2FA1F or
            0x3000 <= cp <= 0x303F or 0x3040 <= cp <= 0x309F or
            0x30A0 <= cp <= 0x30FF or 0xFF00 <= cp <= 0xFFEF)


def smart_join(word_list: List[str]) -> str:
    if not word_list:
        return ""
    result = word_list[0]
    for j in range(1, len(word_list)):
        prev_last = word_list[j - 1][-1] if word_list[j - 1] else ""
        curr_first = word_list[j][0] if word_list[j] else ""
        if is_cjk(prev_last) or is_cjk(curr_first):
            result += word_list[j]
        else:
            result += " " + word_list[j]
    return result.strip()


def words_to_lyrics(words: List[Dict[str, Any]], line_gap: float = 1.5) -> str:
    """Convert word-level timestamps to plain lyrics text.

    Uses timestamps to detect line breaks (by punctuation or time gaps),
    then outputs text only.
    """
    if not words:
        return ""
    lines = []
    current_line = []

    for i, w in enumerate(words):
        current_line.append(w["word"])
        is_last = (i == len(words) - 1)
        has_punct = w["word"].rstrip().endswith((".", "!", "?", "\u3002", "\uff01", "\uff1f", "\uff0c", ","))
        has_gap = (not is_last and words[i + 1]["start"] - w["end"] > line_gap)

        if is_last or has_punct or has_gap:
            text = smart_join(current_line)
            text = text.rstrip("\uff0c\u3002,.")
            if text:
                lines.append(text)
            current_line = []

    return "\n".join(lines) + "\n"


def transcribe_elevenlabs(
    audio_path: str,
    api_key: str,
    api_url: str = "https://api.elevenlabs.io/v1",
    model: str = "scribe_v2",
    language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Transcribe audio using ElevenLabs Scribe API.

    Args:
        audio_path: Path to the audio file
        api_key: ElevenLabs API key
        api_url: ElevenLabs API base URL
        model: Scribe model name
        language: Optional language code (e.g. "zh", "en", "ja")

    Returns:
        List of word-level timestamps [{word, start, end}, ...]
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    url = f"{api_url.rstrip('/')}/speech-to-text"
    headers = {"xi-api-key": api_key}

    data = {"model_id": model}
    if language:
        data["language_code"] = language

    with open(audio_path, "rb") as f:
        files = {"file": (Path(audio_path).name, f)}
        response = requests.post(url, headers=headers, data=data, files=files, timeout=300)

    if response.status_code != 200:
        error_msg = "Unknown error"
        try:
            err = response.json()
            error_msg = err.get("detail", {}).get("message", "") or err.get("detail", error_msg)
        except Exception:
            pass
        raise RuntimeError(f"ElevenLabs API error (HTTP {response.status_code}): {error_msg}")

    result = response.json()
    # ElevenLabs returns {text, words: [{text, start, end, type}, ...]}
    # Filter only "word" type entries and normalize field names
    words = [
        {"word": w["text"], "start": w["start"], "end": w["end"]}
        for w in result.get("words", [])
        if w.get("type") == "word"
    ]
    return words


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".aiff"}


def transcribe_to_file(
    audio_path: str,
    output_path: str,
    api_key: str,
    api_url: str = "https://api.elevenlabs.io/v1",
    model: str = "scribe_v2",
    language: Optional[str] = None,
    line_gap: float = 1.5,
) -> str:
    """Transcribe audio and save plain lyrics text to file.

    Args:
        audio_path: Path to the audio file
        output_path: Path to save the output txt file
        api_key: ElevenLabs API key
        api_url: ElevenLabs API base URL
        model: Scribe model name
        language: Optional language code
        line_gap: Gap threshold (seconds) for line breaking

    Returns:
        Path to the output file
    """
    words = transcribe_elevenlabs(audio_path, api_key, api_url, model, language)

    if not words:
        raise RuntimeError("No word-level timestamps returned from ElevenLabs API")

    content = words_to_lyrics(words, line_gap)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path


def process_folder(
    input_dir: str,
    output_dir: str,
    api_key: str,
    api_url: str = "https://api.elevenlabs.io/v1",
    model: str = "scribe_v2",
    language: Optional[str] = None,
    line_gap: float = 1.5,
) -> List[str]:
    """Transcribe all audio files in a folder.

    Args:
        input_dir: Directory containing audio files
        output_dir: Directory to save output txt files
        api_key: ElevenLabs API key
        api_url: ElevenLabs API base URL
        model: Scribe model name
        language: Optional language code
        line_gap: Gap threshold (seconds) for line breaking

    Returns:
        List of output file paths
    """
    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise NotADirectoryError(f"Input directory not found: {input_dir}")

    os.makedirs(output_dir, exist_ok=True)

    audio_files = sorted(
        f for f in input_path.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    )

    if not audio_files:
        print(f"No audio files found in {input_dir}")
        return []

    output_paths = []
    for i, audio_file in enumerate(audio_files, 1):
        output_file = Path(output_dir) / f"{audio_file.stem}.lyrics.txt"
        print(f"[{i}/{len(audio_files)}] {audio_file.name}")

        try:
            transcribe_to_file(
                audio_path=str(audio_file),
                output_path=str(output_file),
                api_key=api_key,
                api_url=api_url,
                model=model,
                language=language,
                line_gap=line_gap,
            )
            output_paths.append(str(output_file))
            print(f"  -> {output_file.name}")
        except Exception as e:
            print(f"  Error: {e}")

    print(f"Done: {len(output_paths)}/{len(audio_files)} files processed")
    return output_paths
