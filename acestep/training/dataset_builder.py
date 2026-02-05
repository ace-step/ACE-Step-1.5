"""
Dataset Builder for LoRA Training

Provides functionality to:
1. Scan directories for audio files
2. Auto-label audio using LLM
3. Preview and edit metadata
4. Save datasets in JSON format
"""

import os
import json
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import torch
import torchaudio
from loguru import logger

from acestep.constants import SFT_GEN_PROMPT, DEFAULT_DIT_INSTRUCTION


# Supported audio formats
SUPPORTED_AUDIO_FORMATS = {'.wav', '.mp3', '.flac', '.ogg', '.opus'}


@dataclass
class AudioSample:
    """Represents a single audio sample with its metadata.

    Attributes:
        id: Unique identifier for the sample
        audio_path: Path to the audio file
        filename: Original filename
        caption: Generated or user-provided caption describing the music
        genre: Generated genre tags (e.g., "pop, electronic, dance")
        lyrics: Lyrics or "[Instrumental]" for instrumental tracks (used for training)
        raw_lyrics: Original user-provided lyrics from .txt file (before formatting)
        formatted_lyrics: LM-formatted lyrics (if format_lyrics was enabled)
        bpm: Beats per minute
        keyscale: Musical key (e.g., "C Major", "Am")
        timesignature: Time signature (e.g., "4" for 4/4)
        duration: Duration in seconds
        language: Vocal language or "instrumental"
        is_instrumental: Whether the track is instrumental
        custom_tag: User-defined activation tag for LoRA
        labeled: Whether the sample has been labeled
        prompt_override: Per-sample override for prompt type (None=use global, "caption", "genre")
    """
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
    prompt_override: Optional[str] = None  # None=use global ratio, "caption" or "genre" for override

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
        # Filter out unknown keys for backward compatibility
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)

    def get_full_caption(self, tag_position: str = "prepend") -> str:
        """Get caption with custom tag applied.

        Args:
            tag_position: Where to place the custom tag ("prepend", "append", "replace")

        Returns:
            Caption with custom tag applied
        """
        if not self.custom_tag:
            return self.caption

        if tag_position == "prepend":
            return f"{self.custom_tag}, {self.caption}" if self.caption else self.custom_tag
        elif tag_position == "append":
            return f"{self.caption}, {self.custom_tag}" if self.caption else self.custom_tag
        elif tag_position == "replace":
            return self.custom_tag
        else:
            return self.caption

    def get_full_genre(self, tag_position: str = "prepend") -> str:
        """Get genre with custom tag applied.

        Args:
            tag_position: Where to place the custom tag ("prepend", "append", "replace")

        Returns:
            Genre with custom tag applied
        """
        if not self.custom_tag:
            return self.genre

        if tag_position == "prepend":
            return f"{self.custom_tag}, {self.genre}" if self.genre else self.custom_tag
        elif tag_position == "append":
            return f"{self.genre}, {self.custom_tag}" if self.genre else self.custom_tag
        elif tag_position == "replace":
            return self.custom_tag
        else:
            return self.genre

    def get_training_prompt(self, tag_position: str = "prepend", use_genre: bool = False) -> str:
        """Get the prompt to use for training.

        Args:
            tag_position: Where to place the custom tag
            use_genre: Global setting - whether to use genre (can be overridden by prompt_override)

        Returns:
            Either caption or genre with custom tag applied
        """
        # Per-sample override takes priority
        if self.prompt_override == "genre":
            return self.get_full_genre(tag_position)
        elif self.prompt_override == "caption":
            return self.get_full_caption(tag_position)
        # Use global setting
        elif use_genre:
            return self.get_full_genre(tag_position)
        else:
            return self.get_full_caption(tag_position)

    def has_raw_lyrics(self) -> bool:
        """Check if sample has user-provided raw lyrics from .txt file."""
        return bool(self.raw_lyrics and self.raw_lyrics.strip())

    def has_formatted_lyrics(self) -> bool:
        """Check if sample has LM-formatted lyrics."""
        return bool(self.formatted_lyrics and self.formatted_lyrics.strip())


@dataclass
class DatasetMetadata:
    """Metadata for the entire dataset.

    Attributes:
        name: Dataset name
        custom_tag: Default custom tag for all samples
        tag_position: Where to place custom tag ("prepend", "append", "replace")
        created_at: Creation timestamp
        num_samples: Number of samples in the dataset
        all_instrumental: Whether all tracks are instrumental
        genre_ratio: Ratio of samples using genre vs caption (0=all caption, 100=all genre)
    """
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


class DatasetBuilder:
    """Builder for creating training datasets from audio files.
    
    This class handles:
    - Scanning directories for audio files
    - Auto-labeling using LLM
    - Managing sample metadata
    - Saving/loading datasets
    """
    
    def __init__(self):
        """Initialize the dataset builder."""
        self.samples: List[AudioSample] = []
        self.metadata = DatasetMetadata()
        self._current_dir: str = ""
    
    def scan_directory(self, directory: str) -> Tuple[List[AudioSample], str]:
        """Scan a directory for audio files.

        If a .txt file with the same name as an audio file exists, it will be
        treated as the lyrics file for that audio. For example:
        - song.mp3 + song.txt -> song.txt is the lyrics file

        Also scans for CSV metadata files (e.g., key_bpm.csv) with columns:
        File, Artist, Title, BPM, Key, Camelot, and optionally Caption/caption.
        If found, pre-fills BPM, Key, and Caption metadata.

        Args:
            directory: Path to directory containing audio files

        Returns:
            Tuple of (list of AudioSample objects, status message)
        """
        if not os.path.exists(directory):
            return [], f"❌ Directory not found: {directory}"

        if not os.path.isdir(directory):
            return [], f"❌ Not a directory: {directory}"

        self._current_dir = directory
        self.samples = []

        # Scan for audio files
        audio_files = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_AUDIO_FORMATS:
                    audio_files.append(os.path.join(root, file))

        if not audio_files:
            return [], f"❌ No audio files found in {directory}\nSupported formats: {', '.join(SUPPORTED_AUDIO_FORMATS)}"

        # Sort files by name
        audio_files.sort()

        # Load CSV metadata if available
        csv_metadata = self._load_csv_metadata(directory)
        csv_count = 0

        # Count how many samples have lyrics files
        lyrics_count = 0

        # Create AudioSample objects
        for audio_path in audio_files:
            try:
                # Get duration
                duration = self._get_audio_duration(audio_path)

                # Check for accompanying lyrics .txt file with same name
                lyrics_content, has_lyrics_file = self._load_lyrics_file(audio_path)

                # Determine if instrumental based on lyrics file presence
                is_instrumental = self.metadata.all_instrumental
                if has_lyrics_file:
                    is_instrumental = False
                    lyrics_count += 1

                sample = AudioSample(
                    audio_path=audio_path,
                    filename=os.path.basename(audio_path),
                    duration=duration,
                    is_instrumental=is_instrumental,
                    custom_tag=self.metadata.custom_tag,
                    lyrics=lyrics_content if has_lyrics_file else "[Instrumental]",
                    raw_lyrics=lyrics_content if has_lyrics_file else "",  # Store original lyrics
                )

                # Apply CSV metadata if available
                if csv_metadata and sample.filename in csv_metadata:
                    meta = csv_metadata[sample.filename]
                    if meta.get('bpm'):
                        sample.bpm = meta['bpm']
                    if meta.get('key'):
                        sample.keyscale = meta['key']
                    if meta.get('caption'):
                        sample.caption = meta['caption']
                        sample.labeled = True  # Mark as labeled if caption exists
                    csv_count += 1

                self.samples.append(sample)
            except Exception as e:
                logger.warning(f"Failed to process {audio_path}: {e}")

        self.metadata.num_samples = len(self.samples)

        # Build status message
        status = f"✅ Found {len(self.samples)} audio files in {directory}"
        if lyrics_count > 0:
            status += f"\n   📝 {lyrics_count} files have accompanying lyrics (.txt)"
        if csv_count > 0:
            status += f"\n   📊 {csv_count} files have metadata from CSV"

        return self.samples, status

    def _load_csv_metadata(self, directory: str) -> Dict[str, Dict[str, Any]]:
        """Load metadata from CSV files in the directory.

        Looks for CSV files with columns: File, Artist, Title, BPM, Key, Camelot.
        Optionally also recognizes Caption or caption columns.

        Args:
            directory: Path to directory to search for CSV files

        Returns:
            Dict mapping filename -> {bpm, key, caption} metadata
        """
        import csv

        metadata = {}

        # Find all CSV files in directory
        csv_files = []
        for file in os.listdir(directory):
            if file.lower().endswith('.csv'):
                csv_files.append(os.path.join(directory, file))

        if not csv_files:
            return metadata

        for csv_path in csv_files:
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    # Try to detect delimiter
                    sample = f.read(4096)
                    f.seek(0)

                    # Use csv.Sniffer to detect delimiter, fallback to comma
                    try:
                        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
                        reader = csv.DictReader(f, dialect=dialect)
                    except csv.Error:
                        reader = csv.DictReader(f)

                    # Normalize header names (case-insensitive)
                    if reader.fieldnames is None:
                        continue

                    header_map = {h.lower(): h for h in reader.fieldnames}

                    # Check if this CSV has the required columns
                    if 'file' not in header_map:
                        continue

                    file_col = header_map['file']
                    bpm_col = header_map.get('bpm')
                    key_col = header_map.get('key')
                    caption_col = header_map.get('caption')

                    for row in reader:
                        filename = row.get(file_col, '').strip()
                        if not filename:
                            continue

                        entry = {}

                        # Parse BPM
                        if bpm_col and row.get(bpm_col):
                            try:
                                bpm_val = row[bpm_col].strip()
                                # Handle decimal BPM (e.g., "120.5" -> 120)
                                entry['bpm'] = int(float(bpm_val))
                            except (ValueError, TypeError):
                                pass

                        # Parse Key
                        if key_col and row.get(key_col):
                            key_val = row[key_col].strip()
                            if key_val:
                                entry['key'] = key_val

                        # Parse Caption
                        if caption_col and row.get(caption_col):
                            caption_val = row[caption_col].strip()
                            if caption_val:
                                entry['caption'] = caption_val

                        if entry:
                            metadata[filename] = entry

                logger.info(f"Loaded {len(metadata)} entries from CSV: {csv_path}")

            except Exception as e:
                logger.warning(f"Failed to load CSV {csv_path}: {e}")

        return metadata

    def _load_lyrics_file(self, audio_path: str) -> Tuple[str, bool]:
        """Load lyrics from a .txt file with the same name as the audio file.

        Args:
            audio_path: Path to the audio file

        Returns:
            Tuple of (lyrics_content, has_lyrics_file)
            - lyrics_content: The lyrics text or empty string if not found
            - has_lyrics_file: True if a lyrics file was found and loaded
        """
        # Get the base name without extension
        base_path = os.path.splitext(audio_path)[0]
        lyrics_path = base_path + ".txt"

        if os.path.exists(lyrics_path):
            try:
                with open(lyrics_path, 'r', encoding='utf-8') as f:
                    lyrics_content = f.read().strip()

                if lyrics_content:
                    logger.info(f"Loaded lyrics from {lyrics_path}")
                    return lyrics_content, True
                else:
                    logger.warning(f"Lyrics file is empty: {lyrics_path}")
                    return "", False
            except Exception as e:
                logger.warning(f"Failed to read lyrics file {lyrics_path}: {e}")
                return "", False

        return "", False
    
    def _get_audio_duration(self, audio_path: str) -> int:
        """Get the duration of an audio file in seconds.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Duration in seconds (integer)
        """
        try:
            info = torchaudio.info(audio_path)
            return int(info.num_frames / info.sample_rate)
        except Exception as e:
            logger.warning(f"Failed to get duration for {audio_path}: {e}")
            return 0
    
    def label_sample(
        self,
        sample_idx: int,
        dit_handler,
        llm_handler,
        format_lyrics: bool = False,
        transcribe_lyrics: bool = False,
        skip_metas: bool = False,
        progress_callback=None,
    ) -> Tuple[AudioSample, str]:
        """Label a single sample using the LLM.

        Args:
            sample_idx: Index of sample to label
            dit_handler: DiT handler for audio encoding
            llm_handler: LLM handler for caption generation
            format_lyrics: If True, use LLM to format user-provided lyrics
            transcribe_lyrics: If True, use LLM to transcribe lyrics from audio
            skip_metas: If True, skip generating BPM/Key/TimeSig metadata but still generate caption/genre
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (updated AudioSample, status message)
        """
        if sample_idx < 0 or sample_idx >= len(self.samples):
            return None, f"❌ Invalid sample index: {sample_idx}"

        sample = self.samples[sample_idx]

        # Check if sample has pre-loaded lyrics from .txt file
        has_preloaded_lyrics = sample.has_raw_lyrics() and not sample.is_instrumental

        # Remember if sample has pre-existing metadata from CSV (don't overwrite)
        has_csv_bpm = sample.bpm is not None
        has_csv_key = bool(sample.keyscale)

        try:
            if progress_callback:
                progress_callback(f"Processing: {sample.filename}")

            # Step 1: Load and encode audio to get audio codes
            audio_codes = self._get_audio_codes(sample.audio_path, dit_handler)

            if not audio_codes:
                return sample, f"❌ Failed to encode audio: {sample.filename}"

            if progress_callback:
                progress_callback(f"Generating metadata for: {sample.filename}")

            # Step 2: Use LLM based on mode
            if format_lyrics and has_preloaded_lyrics:
                # Format mode: Use format_sample to format user-provided lyrics
                from acestep.inference import format_sample

                result = format_sample(
                    llm_handler=llm_handler,
                    caption="",  # Let LLM generate caption
                    lyrics=sample.raw_lyrics,  # Pass user's raw lyrics
                    user_metadata=None,
                    temperature=0.85,
                    use_constrained_decoding=True,
                )

                if not result.success:
                    return sample, f"❌ LLM format failed: {result.error}"

                # Update sample with formatted results (preserve CSV metadata)
                sample.caption = result.caption or ""
                if not skip_metas:
                    if not has_csv_bpm:
                        sample.bpm = result.bpm
                    if not has_csv_key:
                        sample.keyscale = result.keyscale or ""
                    sample.timesignature = result.timesignature or ""
                sample.language = result.language or "unknown"
                sample.formatted_lyrics = result.lyrics or ""
                sample.lyrics = sample.formatted_lyrics if sample.formatted_lyrics else sample.raw_lyrics

                status_suffix = "(lyrics formatted by LM)"

            else:
                # Understand mode: Use understand_audio_from_codes to get metadata and optionally transcribe lyrics
                metadata, status = llm_handler.understand_audio_from_codes(
                    audio_codes=audio_codes,
                    temperature=0.7,
                    use_constrained_decoding=True,
                )

                if not metadata:
                    return sample, f"❌ LLM labeling failed: {status}"

                # Update sample with generated caption and genre (always)
                sample.caption = metadata.get('caption', '')
                sample.genre = metadata.get('genres', '')  # Extract genre from LLM output

                # Update metas only if not skipped and not from CSV
                if not skip_metas:
                    if not has_csv_bpm:
                        sample.bpm = self._parse_int(metadata.get('bpm'))
                    if not has_csv_key:
                        sample.keyscale = metadata.get('keyscale', '')
                    sample.timesignature = metadata.get('timesignature', '')

                sample.language = metadata.get('vocal_language', 'unknown')

                # LLM-generated/transcribed lyrics
                llm_lyrics = metadata.get('lyrics', '')

                # Handle lyrics based on mode
                if sample.is_instrumental:
                    sample.lyrics = "[Instrumental]"
                    sample.language = "unknown"
                    sample.formatted_lyrics = ""
                    status_suffix = "(instrumental)"
                elif transcribe_lyrics:
                    # Transcribe mode: Use LLM-generated lyrics, ignore user's .txt file
                    sample.formatted_lyrics = llm_lyrics
                    sample.lyrics = llm_lyrics
                    status_suffix = "(lyrics transcribed by LM)"
                elif has_preloaded_lyrics:
                    # Keep raw lyrics from .txt file
                    sample.lyrics = sample.raw_lyrics
                    sample.formatted_lyrics = ""
                    status_suffix = "(using raw lyrics)"
                else:
                    # No pre-loaded lyrics and not transcribing, use LLM lyrics
                    sample.lyrics = llm_lyrics
                    sample.formatted_lyrics = llm_lyrics
                    status_suffix = ""

            # NOTE: Duration is NOT overwritten from LM metadata.
            # We keep the real audio duration obtained from torchaudio during scan.

            sample.labeled = True
            self.samples[sample_idx] = sample

            status_msg = f"✅ Labeled: {sample.filename}"
            if skip_metas:
                status_msg += " (skip metas)"
            if status_suffix:
                status_msg += f" {status_suffix}"

            return sample, status_msg

        except Exception as e:
            logger.exception(f"Error labeling sample {sample.filename}")
            return sample, f"❌ Error: {str(e)}"

    def label_all_samples(
        self,
        dit_handler,
        llm_handler,
        format_lyrics: bool = False,
        transcribe_lyrics: bool = False,
        skip_metas: bool = False,
        only_unlabeled: bool = False,
        progress_callback=None,
    ) -> Tuple[List[AudioSample], str]:
        """Label all samples in the dataset.

        Args:
            dit_handler: DiT handler for audio encoding
            llm_handler: LLM handler for caption generation
            format_lyrics: If True, use LLM to format user-provided lyrics
            transcribe_lyrics: If True, use LLM to transcribe lyrics from audio
            skip_metas: If True, skip generating BPM/Key/TimeSig but still generate caption/genre
            only_unlabeled: If True, only label samples without caption
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (list of updated samples, status message)
        """
        if not self.samples:
            return [], "❌ No samples to label. Please scan a directory first."

        # Filter samples if only_unlabeled
        if only_unlabeled:
            samples_to_label = [
                (i, s) for i, s in enumerate(self.samples)
                if not s.labeled or not s.caption
            ]
        else:
            samples_to_label = [(i, s) for i, s in enumerate(self.samples)]

        if not samples_to_label:
            return self.samples, "✅ All samples already labeled"

        success_count = 0
        fail_count = 0
        total = len(samples_to_label)

        for idx, (i, sample) in enumerate(samples_to_label):
            if progress_callback:
                progress_callback(f"Labeling {idx+1}/{total}: {sample.filename}")

            _, status = self.label_sample(
                i, dit_handler, llm_handler, format_lyrics, transcribe_lyrics, skip_metas, progress_callback
            )

            if "✅" in status:
                success_count += 1
            else:
                fail_count += 1

        status_msg = f"✅ Labeled {success_count}/{total} samples"
        if fail_count > 0:
            status_msg += f" ({fail_count} failed)"
        if only_unlabeled:
            status_msg += f" (unlabeled only, {len(self.samples)} total)"

        return self.samples, status_msg
    
    def _get_audio_codes(self, audio_path: str, dit_handler) -> Optional[str]:
        """Encode audio to get semantic codes for LLM understanding.
        
        Args:
            audio_path: Path to audio file
            dit_handler: DiT handler with VAE and tokenizer
            
        Returns:
            Audio codes string or None if failed
        """
        try:
            # Check if handler has required methods
            if not hasattr(dit_handler, 'convert_src_audio_to_codes'):
                logger.error("DiT handler missing convert_src_audio_to_codes method")
                return None
            
            # Use handler's method to convert audio to codes
            codes_string = dit_handler.convert_src_audio_to_codes(audio_path)
            
            if codes_string and not codes_string.startswith("❌"):
                return codes_string
            else:
                logger.warning(f"Failed to convert audio to codes: {codes_string}")
                return None
                
        except Exception as e:
            logger.exception(f"Error encoding audio {audio_path}")
            return None
    
    def _parse_int(self, value: Any) -> Optional[int]:
        """Safely parse an integer value."""
        if value is None or value == "N/A" or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def update_sample(self, sample_idx: int, **kwargs) -> Tuple[AudioSample, str]:
        """Update a sample's metadata.
        
        Args:
            sample_idx: Index of sample to update
            **kwargs: Fields to update
            
        Returns:
            Tuple of (updated sample, status message)
        """
        if sample_idx < 0 or sample_idx >= len(self.samples):
            return None, f"❌ Invalid sample index: {sample_idx}"
        
        sample = self.samples[sample_idx]
        
        for key, value in kwargs.items():
            if hasattr(sample, key):
                setattr(sample, key, value)
        
        self.samples[sample_idx] = sample
        return sample, f"✅ Updated: {sample.filename}"
    
    def set_custom_tag(self, custom_tag: str, tag_position: str = "prepend"):
        """Set the custom tag for all samples.
        
        Args:
            custom_tag: Custom activation tag
            tag_position: Where to place tag ("prepend", "append", "replace")
        """
        self.metadata.custom_tag = custom_tag
        self.metadata.tag_position = tag_position
        
        for sample in self.samples:
            sample.custom_tag = custom_tag
    
    def set_all_instrumental(self, is_instrumental: bool):
        """Set instrumental flag for all samples.

        Args:
            is_instrumental: Whether all tracks are instrumental

        Note:
            If a sample has raw_lyrics (from .txt file), setting is_instrumental=True
            will NOT override its lyrics. The raw_lyrics takes precedence.
        """
        self.metadata.all_instrumental = is_instrumental

        for sample in self.samples:
            # If sample has raw lyrics from .txt file, don't treat it as instrumental
            if sample.has_raw_lyrics():
                sample.is_instrumental = False
                # Keep existing lyrics from raw_lyrics
                if not sample.lyrics or sample.lyrics == "[Instrumental]":
                    sample.lyrics = sample.raw_lyrics
            else:
                sample.is_instrumental = is_instrumental
                if is_instrumental:
                    sample.lyrics = "[Instrumental]"
                    sample.language = "unknown"
    
    def get_sample_count(self) -> int:
        """Get the number of samples in the dataset."""
        return len(self.samples)
    
    def get_labeled_count(self) -> int:
        """Get the number of labeled samples."""
        return sum(1 for s in self.samples if s.labeled)
    
    def save_dataset(self, output_path: str, dataset_name: str = None) -> str:
        """Save the dataset to a JSON file.
        
        Args:
            output_path: Path to save the dataset JSON
            dataset_name: Optional name for the dataset
            
        Returns:
            Status message
        """
        if not self.samples:
            return "❌ No samples to save"
        
        if dataset_name:
            self.metadata.name = dataset_name
        
        self.metadata.num_samples = len(self.samples)
        self.metadata.created_at = datetime.now().isoformat()
        
        # Build dataset (save raw values, custom tag is applied during preprocessing)
        dataset = {
            "metadata": self.metadata.to_dict(),
            "samples": [sample.to_dict() for sample in self.samples]
        }
        
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(dataset, f, indent=2, ensure_ascii=False)
            
            return f"✅ Dataset saved to {output_path}\n{len(self.samples)} samples, tag: '{self.metadata.custom_tag}'"
        except Exception as e:
            logger.exception("Error saving dataset")
            return f"❌ Failed to save dataset: {str(e)}"
    
    def load_dataset(self, dataset_path: str) -> Tuple[List[AudioSample], str]:
        """Load a dataset from a JSON file.
        
        Args:
            dataset_path: Path to the dataset JSON file
            
        Returns:
            Tuple of (list of samples, status message)
        """
        if not os.path.exists(dataset_path):
            return [], f"❌ Dataset not found: {dataset_path}"
        
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Load metadata
            if "metadata" in data:
                meta_dict = data["metadata"]
                self.metadata = DatasetMetadata(
                    name=meta_dict.get("name", "untitled"),
                    custom_tag=meta_dict.get("custom_tag", ""),
                    tag_position=meta_dict.get("tag_position", "prepend"),
                    created_at=meta_dict.get("created_at", ""),
                    num_samples=meta_dict.get("num_samples", 0),
                    all_instrumental=meta_dict.get("all_instrumental", True),
                )
            
            # Load samples
            self.samples = []
            for sample_dict in data.get("samples", []):
                sample = AudioSample.from_dict(sample_dict)
                self.samples.append(sample)
            
            return self.samples, f"✅ Loaded {len(self.samples)} samples from {dataset_path}"
            
        except Exception as e:
            logger.exception("Error loading dataset")
            return [], f"❌ Failed to load dataset: {str(e)}"
    
    def get_samples_dataframe_data(self) -> List[List[Any]]:
        """Get samples data in a format suitable for Gradio DataFrame.

        Returns:
            List of rows for DataFrame display
        """
        rows = []
        for i, sample in enumerate(self.samples):
            # Determine lyrics status
            if sample.has_raw_lyrics():
                lyrics_status = "📝"  # Has lyrics from .txt file
            elif sample.is_instrumental:
                lyrics_status = "🎵"  # Instrumental
            else:
                lyrics_status = "-"  # No lyrics

            rows.append([
                i,
                sample.filename,
                f"{sample.duration:.1f}s",
                lyrics_status,
                "✅" if sample.labeled else "❌",
                sample.bpm or "-",
                sample.keyscale or "-",
                sample.caption[:50] + "..." if len(sample.caption) > 50 else sample.caption or "-",
            ])
        return rows
    
    def to_training_format(self) -> List[Dict[str, Any]]:
        """Convert dataset to format suitable for training.
        
        Returns:
            List of training sample dictionaries
        """
        training_samples = []
        
        for sample in self.samples:
            if not sample.labeled:
                continue
            
            training_sample = {
                "audio_path": sample.audio_path,
                "caption": sample.get_full_caption(self.metadata.tag_position),
                "lyrics": sample.lyrics,
                "bpm": sample.bpm,
                "keyscale": sample.keyscale,
                "timesignature": sample.timesignature,
                "duration": sample.duration,
                "language": sample.language,
                "is_instrumental": sample.is_instrumental,
            }
            training_samples.append(training_sample)
        
        return training_samples
    
    def preprocess_to_tensors(
        self,
        dit_handler,
        output_dir: str,
        max_duration: float = 240.0,
        progress_callback=None,
    ) -> Tuple[List[str], str]:
        """Preprocess all labeled samples to tensor files for efficient training.
        
        This method pre-computes all tensors needed by the DiT decoder:
        - target_latents: VAE-encoded audio
        - encoder_hidden_states: Condition encoder output
        - context_latents: Source context (silence_latent + zeros for text2music)
        
        Args:
            dit_handler: Initialized DiT handler with model, VAE, and text encoder
            output_dir: Directory to save preprocessed .pt files
            max_duration: Maximum audio duration in seconds (default 240s = 4 min)
            progress_callback: Optional callback for progress updates
            
        Returns:
            Tuple of (list of output paths, status message)
        """
        if not self.samples:
            return [], "❌ No samples to preprocess"
        
        labeled_samples = [s for s in self.samples if s.labeled]
        if not labeled_samples:
            return [], "❌ No labeled samples to preprocess"
        
        # Validate handler
        if dit_handler is None or dit_handler.model is None:
            return [], "❌ Model not initialized. Please initialize the service first."
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        output_paths = []
        success_count = 0
        fail_count = 0
        
        # Get model and components
        model = dit_handler.model
        vae = dit_handler.vae
        text_encoder = dit_handler.text_encoder
        text_tokenizer = dit_handler.text_tokenizer
        silence_latent = dit_handler.silence_latent
        device = dit_handler.device
        dtype = dit_handler.dtype

        target_sample_rate = 48000

        # Determine which samples use genre based on ratio (for samples without override)
        # genre_ratio: 0 = all caption, 100 = all genre
        genre_ratio = self.metadata.genre_ratio
        num_genre_samples = int(len(labeled_samples) * genre_ratio / 100)

        # Create a list of indices that should use genre (evenly distributed)
        import random
        random.seed(42)  # Reproducible
        all_indices = list(range(len(labeled_samples)))
        random.shuffle(all_indices)
        genre_indices = set(all_indices[:num_genre_samples])

        for i, sample in enumerate(labeled_samples):
            try:
                if progress_callback:
                    progress_callback(f"Preprocessing {i+1}/{len(labeled_samples)}: {sample.filename}")

                # Determine if this sample uses genre (per-sample override > global ratio)
                use_genre = i in genre_indices

                # Step 1: Load and preprocess audio to stereo @ 48kHz
                audio, sr = torchaudio.load(sample.audio_path)
                
                # Resample if needed
                if sr != target_sample_rate:
                    resampler = torchaudio.transforms.Resample(sr, target_sample_rate)
                    audio = resampler(audio)
                
                # Convert to stereo
                if audio.shape[0] == 1:
                    audio = audio.repeat(2, 1)
                elif audio.shape[0] > 2:
                    audio = audio[:2, :]
                
                # Truncate to max duration
                max_samples = int(max_duration * target_sample_rate)
                if audio.shape[1] > max_samples:
                    audio = audio[:, :max_samples]
                
                # Add batch dimension: [2, T] -> [1, 2, T]
                audio = audio.unsqueeze(0).to(device).to(vae.dtype)
                
                # Step 2: VAE encode audio to get target_latents
                with torch.no_grad():

                    # Determine the device where the VAE is currently located
                    model_device = next(vae.parameters()).device

                    # Move audio to match model device if needed
                    if audio.device != model_device:
                        audio = audio.to(model_device)

                    latent = vae.encode(audio).latent_dist.sample()
                    target_latents = latent.transpose(1, 2).to(dtype)

                # Now handle text encoding
                if 'text_input_ids' in locals() and text_input_ids is not None:

                    # Determine text encoder device
                    text_dev = next(text_encoder.parameters()).device

                    # Move ids to match text encoder device as needed
                    if text_input_ids.device != text_dev:
                        text_input_ids = text_input_ids.to(text_dev)

                    text_outputs = text_encoder(text_input_ids)
                else:
                    text_outputs = None

                latent_length = target_latents.shape[1]
                
                # Step 3: Create attention mask (all ones for valid audio)
                attention_mask = torch.ones(1, latent_length, device=device, dtype=dtype)

                # Step 4: Encode caption/genre text (per-sample override > global ratio)
                # Use SFT_GEN_PROMPT format to match inference (handler.py)
                caption = sample.get_training_prompt(self.metadata.tag_position, use_genre=use_genre)

                # Construct metas string (matches handler.py _dict_to_meta_string format)
                metas_str = (
                    f"- bpm: {sample.bpm if sample.bpm else 'N/A'}\n"
                    f"- timesignature: {sample.timesignature if sample.timesignature else 'N/A'}\n"
                    f"- keyscale: {sample.keyscale if sample.keyscale else 'N/A'}\n"
                    f"- duration: {sample.duration} seconds\n"
                )

                # Use SFT_GEN_PROMPT format (same as inference)
                text_prompt = SFT_GEN_PROMPT.format(DEFAULT_DIT_INSTRUCTION, caption, metas_str)

                # Debug: Print first sample's text_prompt for verification
                if i == 0:
                    logger.info(f"\n{'='*70}")
                    logger.info("🔍 [DEBUG] DiT TEXT ENCODER INPUT (Training Preprocess)")
                    logger.info(f"{'='*70}")
                    logger.info(f"text_prompt:\n{text_prompt}")
                    logger.info(f"{'='*70}\n")

                text_inputs = text_tokenizer(
                    text_prompt,
                    padding="max_length",
                    max_length=256,
                    truncation=True,
                    return_tensors="pt",
                )
                text_input_ids = text_inputs.input_ids.to(device)
                text_attention_mask = text_inputs.attention_mask.to(device).to(dtype)

                with torch.no_grad():
                    text_outputs = text_encoder(text_input_ids)
                    text_hidden_states = text_outputs.last_hidden_state.to(dtype)
                
                # Step 5: Encode lyrics
                lyrics = sample.lyrics if sample.lyrics else "[Instrumental]"
                lyric_inputs = text_tokenizer(
                    lyrics,
                    padding="max_length",
                    max_length=512,
                    truncation=True,
                    return_tensors="pt",
                )
                lyric_input_ids = lyric_inputs.input_ids.to(device)
                lyric_attention_mask = lyric_inputs.attention_mask.to(device).to(dtype)
                
                with torch.no_grad():
                    lyric_hidden_states = text_encoder.embed_tokens(lyric_input_ids).to(dtype)
                
                # Step 6: Prepare refer_audio (empty for text2music)
                # Create minimal refer_audio placeholder
                refer_audio_hidden = torch.zeros(1, 1, 64, device=device, dtype=dtype)
                refer_audio_order_mask = torch.zeros(1, device=device, dtype=torch.long)
                
                # Step 7: Run model.encoder to get encoder_hidden_states
                with torch.no_grad():
                    encoder_hidden_states, encoder_attention_mask = model.encoder(
                        text_hidden_states=text_hidden_states,
                        text_attention_mask=text_attention_mask,
                        lyric_hidden_states=lyric_hidden_states,
                        lyric_attention_mask=lyric_attention_mask,
                        refer_audio_acoustic_hidden_states_packed=refer_audio_hidden,
                        refer_audio_order_mask=refer_audio_order_mask,
                    )
                
                # Step 8: Build context_latents for text2music
                # For text2music: src_latents = silence_latent, is_covers = 0
                # chunk_masks: 1 = generate, 0 = keep original
                # IMPORTANT: chunk_masks must have same shape as src_latents [B, T, 64]
                # For text2music, we want to generate the entire audio, so chunk_masks = all 1s
                src_latents = silence_latent[:, :latent_length, :].to(dtype)
                if src_latents.shape[0] < 1:
                    src_latents = src_latents.expand(1, -1, -1)
                
                # Pad or truncate silence_latent to match latent_length
                if src_latents.shape[1] < latent_length:
                    pad_len = latent_length - src_latents.shape[1]
                    src_latents = torch.cat([
                        src_latents,
                        silence_latent[:, :pad_len, :].expand(1, -1, -1).to(dtype)
                    ], dim=1)
                elif src_latents.shape[1] > latent_length:
                    src_latents = src_latents[:, :latent_length, :]
                
                # chunk_masks = 1 means "generate this region", 0 = keep original
                # Shape must match src_latents: [B, T, 64] (NOT [B, T, 1])
                # For text2music, generate everything -> all 1s with shape [1, T, 64]
                chunk_masks = torch.ones(1, latent_length, 64, device=device, dtype=dtype)
                # context_latents = [src_latents, chunk_masks] -> [B, T, 128]
                context_latents = torch.cat([src_latents, chunk_masks], dim=-1)
                
                # Step 9: Save all tensors to .pt file (squeeze batch dimension for storage)
                output_data = {
                    "target_latents": target_latents.squeeze(0).cpu(),  # [T, 64]
                    "attention_mask": attention_mask.squeeze(0).cpu(),  # [T]
                    "encoder_hidden_states": encoder_hidden_states.squeeze(0).cpu(),  # [L, D]
                    "encoder_attention_mask": encoder_attention_mask.squeeze(0).cpu(),  # [L]
                    "context_latents": context_latents.squeeze(0).cpu(),  # [T, 65]
                    "metadata": {
                        "audio_path": sample.audio_path,
                        "filename": sample.filename,
                        "caption": caption,
                        "lyrics": lyrics,
                        "duration": sample.duration,
                        "bpm": sample.bpm,
                        "keyscale": sample.keyscale,
                        "timesignature": sample.timesignature,
                        "language": sample.language,
                        "is_instrumental": sample.is_instrumental,
                    }
                }
                
                # Save with sample ID as filename
                output_path = os.path.join(output_dir, f"{sample.id}.pt")
                torch.save(output_data, output_path)
                output_paths.append(output_path)
                success_count += 1
                
            except Exception as e:
                logger.exception(f"Error preprocessing {sample.filename}")
                fail_count += 1
                if progress_callback:
                    progress_callback(f"❌ Failed: {sample.filename}: {str(e)}")
        
        # Save manifest file listing all preprocessed samples
        manifest = {
            "metadata": self.metadata.to_dict(),
            "samples": output_paths,
            "num_samples": len(output_paths),
        }
        manifest_path = os.path.join(output_dir, "manifest.json")
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        
        status = f"✅ Preprocessed {success_count}/{len(labeled_samples)} samples to {output_dir}"
        if fail_count > 0:
            status += f" ({fail_count} failed)"
        
        return output_paths, status
