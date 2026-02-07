import json
import os
from datetime import datetime
from typing import List, Tuple

from loguru import logger

from .models import AudioSample, DatasetMetadata


class SerializationMixin:
    """Save/load dataset JSON."""

    def save_dataset(self, output_path: str, dataset_name: str = None) -> str:
        """Save the dataset to a JSON file."""
        if not self.samples:
            return "❌ No samples to save"

        if dataset_name:
            self.metadata.name = dataset_name

        self.metadata.num_samples = len(self.samples)
        self.metadata.created_at = datetime.now().isoformat()

        dataset = {
            "metadata": self.metadata.to_dict(),
            "samples": [sample.to_dict() for sample in self.samples],
        }

        try:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(dataset, f, indent=2, ensure_ascii=False)

            return f"✅ Dataset saved to {output_path}\n{len(self.samples)} samples, tag: '{self.metadata.custom_tag}'"
        except Exception as e:
            logger.exception("Error saving dataset")
            return f"❌ Failed to save dataset: {str(e)}"

    def load_dataset(self, dataset_path: str) -> Tuple[List[AudioSample], str]:
        """Load a dataset from a JSON file."""
        if not os.path.exists(dataset_path):
            return [], f"❌ Dataset not found: {dataset_path}"

        try:
            with open(dataset_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "metadata" in data:
                meta_dict = data["metadata"]
                self.metadata = DatasetMetadata(
                    name=meta_dict.get("name", "untitled"),
                    custom_tag=meta_dict.get("custom_tag", ""),
                    tag_position=meta_dict.get("tag_position", "prepend"),
                    created_at=meta_dict.get("created_at", ""),
                    num_samples=meta_dict.get("num_samples", 0),
                    all_instrumental=meta_dict.get("all_instrumental", True),
                    genre_ratio=meta_dict.get("genre_ratio", 0),
                )

            self.samples = []
            for sample_dict in data.get("samples", []):
                sample = AudioSample.from_dict(sample_dict)
                self.samples.append(sample)

            return self.samples, f"✅ Loaded {len(self.samples)} samples from {dataset_path}"
        except Exception as e:
            logger.exception("Error loading dataset")
            return [], f"❌ Failed to load dataset: {str(e)}"
