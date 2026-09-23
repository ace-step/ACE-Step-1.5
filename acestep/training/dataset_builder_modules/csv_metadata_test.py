"""Regression tests for UTF-8 CSV metadata used by training dataset scans."""

import csv
import tempfile
import unittest
import wave
from pathlib import Path

from acestep.training.dataset_builder import DatasetBuilder
from acestep.training.dataset_builder_modules.csv_metadata import load_csv_metadata
from acestep.training.path_safety import get_safe_root, set_safe_root


class CsvMetadataTests(unittest.TestCase):
    """Exercise real CSV files through the dataset builder and metadata loader."""

    def setUp(self):
        """Create a small WAV dataset inside a temporary safe root."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        previous_root = get_safe_root()
        self.addCleanup(set_safe_root, previous_root)
        set_safe_root(str(self.root))
        self.filename = "歌曲.wav"
        with wave.open(str(self.root / self.filename), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\0\0" * 8000)

    def _write_csv(self, encoding: str, delimiter: str = ",", caption: str = "柔和, piano") -> None:
        """Write a tutorial-style metadata table with the selected UTF-8 encoding."""
        with (self.root / "metadata.csv").open("w", encoding=encoding, newline="") as handle:
            writer = csv.writer(handle, delimiter=delimiter)
            writer.writerow(["File", "BPM", "Key", "Caption"])
            writer.writerow([self.filename, "120", "D major", caption])

    def test_scan_applies_metadata_with_and_without_bom(self):
        """A BOM must not hide the File header or drop training annotations."""
        for encoding in ("utf-8", "utf-8-sig"):
            for delimiter in (",", ";", "\t"):
                with self.subTest(encoding=encoding, delimiter=delimiter):
                    self._write_csv(encoding, delimiter)
                    samples, status = DatasetBuilder().scan_directory(str(self.root))
                    self.assertEqual(len(samples), 1)
                    sample = samples[0]
                    self.assertEqual(
                        (sample.bpm, sample.keyscale, sample.caption, sample.labeled),
                        (120, "D major", "柔和, piano", True),
                    )
                    self.assertIn("1 files have metadata from CSV", status)

    def test_bom_in_caption_content_is_preserved(self):
        """Only the encoding signature should be removed, not annotation text."""
        caption = "piano \ufeffstrings"
        self._write_csv("utf-8-sig", caption=caption)
        metadata = load_csv_metadata(str(self.root))
        self.assertEqual(metadata[self.filename]["caption"], caption)

    def test_csv_without_file_header_is_ignored(self):
        """Tables without the required File column remain unsupported."""
        (self.root / "metadata.csv").write_text("Title,BPM\nSong,120\n", encoding="utf-8-sig")
        self.assertEqual(load_csv_metadata(str(self.root)), {})


if __name__ == "__main__":
    unittest.main()
