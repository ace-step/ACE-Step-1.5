import os
import csv
from typing import Any, Dict

from loguru import logger


def load_csv_metadata(directory: str) -> Dict[str, Dict[str, Any]]:
    """Load metadata from CSV files in the directory."""
    metadata: Dict[str, Dict[str, Any]] = {}

    csv_files = []
    for file in os.listdir(directory):
        if file.lower().endswith(".csv"):
            csv_files.append(os.path.join(directory, file))

    if not csv_files:
        return metadata

    for csv_path in csv_files:
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                sample = f.read(4096)
                f.seek(0)

                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                    reader = csv.DictReader(f, dialect=dialect)
                except csv.Error:
                    reader = csv.DictReader(f)

                if reader.fieldnames is None:
                    continue

                header_map = {h.lower(): h for h in reader.fieldnames}
                if "file" not in header_map:
                    continue

                file_col = header_map["file"]
                bpm_col = header_map.get("bpm")
                key_col = header_map.get("key")
                caption_col = header_map.get("caption")

                for row in reader:
                    filename = row.get(file_col, "").strip()
                    if not filename:
                        continue

                    entry: Dict[str, Any] = {}

                    if bpm_col and row.get(bpm_col):
                        try:
                            bpm_val = row[bpm_col].strip()
                            entry["bpm"] = int(float(bpm_val))
                        except (ValueError, TypeError):
                            pass

                    if key_col and row.get(key_col):
                        key_val = row[key_col].strip()
                        if key_val:
                            entry["key"] = key_val

                    if caption_col and row.get(caption_col):
                        caption_val = row[caption_col].strip()
                        if caption_val:
                            entry["caption"] = caption_val

                    if entry:
                        metadata[filename] = entry

            logger.info(f"Loaded {len(metadata)} entries from CSV: {csv_path}")
        except Exception as e:
            logger.warning(f"Failed to load CSV {csv_path}: {e}")

    return metadata
