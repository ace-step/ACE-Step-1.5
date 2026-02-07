import os
from typing import List, Tuple

from loguru import logger

from .audio_io import get_audio_duration, load_lyrics_file
from .csv_metadata import load_csv_metadata
from .models import AudioSample, SUPPORTED_AUDIO_FORMATS


class ScanMixin:
    """Directory scanning helpers."""

    def scan_directory(self, directory: str) -> Tuple[List[AudioSample], str]:
        """Scan a directory for audio files."""
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
        lyrics_count = 0

        for audio_path in audio_files:
            try:
                duration = get_audio_duration(audio_path)
                lyrics_content, has_lyrics_file = load_lyrics_file(audio_path)

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
                    raw_lyrics=lyrics_content if has_lyrics_file else "",
                )

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
        if lyrics_count > 0:
            status += f"\n   📝 {lyrics_count} files have accompanying lyrics (.txt)"
        if csv_count > 0:
            status += f"\n   📊 {csv_count} files have metadata from CSV"

        return self.samples, status
