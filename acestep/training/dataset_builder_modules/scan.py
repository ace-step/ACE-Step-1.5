import os
from typing import List, Tuple

from loguru import logger

from acestep.training.path_safety import safe_path
from .audio_io import get_audio_duration, load_caption_file, load_json_metadata, load_lyrics_file
from .csv_metadata import load_csv_metadata
from .models import AudioSample, SUPPORTED_AUDIO_FORMATS


class ScanMixin:
    """Directory scanning helpers."""

    def scan_directory(self, directory: str) -> Tuple[List[AudioSample], str]:
        """Scan a directory for audio files."""
        try:
            directory = safe_path(directory)
        except ValueError:
            return [], f"❌ Rejected unsafe directory path: {directory}"

        if not os.path.exists(directory):
            return [], f"❌ Directory not found: {directory}"

        if not os.path.isdir(directory):
            return [], f"❌ Not a directory: {directory}"

        self._current_dir = directory
        self.samples = []

        audio_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_AUDIO_FORMATS:
                    audio_files.append(os.path.join(root, file))

        if not audio_files:
            return [], (
                f"❌ No audio files found in {directory}\n"
                f"Supported formats: {', '.join(SUPPORTED_AUDIO_FORMATS)}"
            )

        audio_files.sort()

        csv_metadata = load_csv_metadata(directory)
        csv_count = 0
        json_count = 0
        caption_count = 0
        lyrics_count = 0

        for audio_path in audio_files:
            try:
                duration = get_audio_duration(audio_path)
                caption_content, has_caption_file = load_caption_file(audio_path)
                lyrics_content, has_lyrics_file = load_lyrics_file(audio_path)
                json_meta, has_json = load_json_metadata(audio_path)

                if has_caption_file:
                    caption_count += 1
                if has_lyrics_file:
                    lyrics_count += 1
                if has_json:
                    json_count += 1

                is_instrumental = self.metadata.all_instrumental
                if has_lyrics_file:
                    is_instrumental = False

                sample = AudioSample(
                    audio_path=audio_path,
                    filename=os.path.basename(audio_path),
                    duration=duration,
                    is_instrumental=is_instrumental,
                    custom_tag=self.metadata.custom_tag,
                    caption=caption_content if has_caption_file else "",
                    lyrics=lyrics_content if has_lyrics_file else "[Instrumental]",
                    raw_lyrics=lyrics_content if has_lyrics_file else "",
                )
                if has_caption_file:
                    sample.labeled = True

                # Apply JSON metadata (overrides caption file if present)
                if has_json:
                    if json_meta.get("caption"):
                        sample.caption = json_meta["caption"]
                        sample.labeled = True
                    if json_meta.get("bpm"):
                        sample.bpm = json_meta["bpm"]
                    if json_meta.get("keyscale"):
                        sample.keyscale = json_meta["keyscale"]
                    if json_meta.get("timesignature"):
                        sample.timesignature = json_meta["timesignature"]
                    if json_meta.get("language"):
                        sample.language = json_meta["language"]
                        if sample.language != "instrumental":
                            sample.is_instrumental = False

                if csv_metadata and sample.filename in csv_metadata:
                    meta = csv_metadata[sample.filename]
                    if meta.get("bpm"):
                        sample.bpm = meta["bpm"]
                    if meta.get("key"):
                        sample.keyscale = meta["key"]
                    if meta.get("caption"):
                        sample.caption = meta["caption"]
                        sample.labeled = True
                    csv_count += 1

                self.samples.append(sample)
            except Exception as e:
                logger.warning(f"Failed to process {audio_path}: {e}")

        self.metadata.num_samples = len(self.samples)

        status = f"✅ Found {len(self.samples)} audio files in {directory}"
        if json_count > 0:
            status += f"\n   📄 Detected {json_count} JSON metadata (.json)"
        if caption_count > 0:
            status += f"\n   📋 Detected {caption_count} captions (.caption.txt)"
        if lyrics_count > 0:
            status += f"\n   📝 Detected {lyrics_count} lyrics (.lyrics.txt / .txt)"
        if csv_count > 0:
            status += f"\n   📊 {csv_count} files have metadata from CSV"

        return self.samples, status
