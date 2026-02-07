"""
Data models for dataset builder.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Optional
import uuid


SUPPORTED_AUDIO_FORMATS = {".wav", ".mp3", ".flac", ".ogg", ".opus"}


@dataclass
class AudioSample:
    """Represents a single audio sample with its metadata."""

    id: str = ""
    audio_path: str = ""
    filename: str = ""
    caption: str = ""
    genre: str = ""  # Genre tags from LLM
    lyrics: str = "[Instrumental]"
    raw_lyrics: str = ""  # Original user-provided lyrics from .txt file
    formatted_lyrics: str = ""  # LM-formatted lyrics
    bpm: Optional[int] = None
    keyscale: str = ""
    timesignature: str = ""
    duration: int = 0
    language: str = "unknown"
    is_instrumental: bool = True
    custom_tag: str = ""
    labeled: bool = False
    prompt_override: Optional[str] = None  # None=use global ratio, "caption" or "genre"

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AudioSample":
        """Create from dictionary.

        Handles backward compatibility for datasets without raw_lyrics/formatted_lyrics/genre.
        """
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)

    def get_full_caption(self, tag_position: str = "prepend") -> str:
        """Get caption with custom tag applied."""
        if not self.custom_tag:
            return self.caption

        if tag_position == "prepend":
            return f"{self.custom_tag}, {self.caption}" if self.caption else self.custom_tag
        if tag_position == "append":
            return f"{self.caption}, {self.custom_tag}" if self.caption else self.custom_tag
        if tag_position == "replace":
            return self.custom_tag
        return self.caption

    def get_full_genre(self, tag_position: str = "prepend") -> str:
        """Get genre with custom tag applied."""
        if not self.custom_tag:
            return self.genre

        if tag_position == "prepend":
            return f"{self.custom_tag}, {self.genre}" if self.genre else self.custom_tag
        if tag_position == "append":
            return f"{self.genre}, {self.custom_tag}" if self.genre else self.custom_tag
        if tag_position == "replace":
            return self.custom_tag
        return self.genre

    def get_training_prompt(self, tag_position: str = "prepend", use_genre: bool = False) -> str:
        """Get the prompt to use for training."""
        if self.prompt_override == "genre":
            return self.get_full_genre(tag_position)
        if self.prompt_override == "caption":
            return self.get_full_caption(tag_position)
        if use_genre:
            return self.get_full_genre(tag_position)
        return self.get_full_caption(tag_position)

    def has_raw_lyrics(self) -> bool:
        """Check if sample has user-provided raw lyrics from .txt file."""
        return bool(self.raw_lyrics and self.raw_lyrics.strip())

    def has_formatted_lyrics(self) -> bool:
        """Check if sample has LM-formatted lyrics."""
        return bool(self.formatted_lyrics and self.formatted_lyrics.strip())


@dataclass
class DatasetMetadata:
    """Metadata for the entire dataset."""

    name: str = "untitled_dataset"
    custom_tag: str = ""
    tag_position: str = "prepend"
    created_at: str = ""
    num_samples: int = 0
    all_instrumental: bool = True
    genre_ratio: int = 0  # 0-100, percentage of samples using genre

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
