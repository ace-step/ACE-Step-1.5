from typing import List

from .models import AudioSample, DatasetMetadata


class CoreMixin:
    """Base state for dataset builder."""

    def __init__(self):
        self.samples: List[AudioSample] = []
        self.metadata = DatasetMetadata()
        self._current_dir: str = ""

    def get_sample_count(self) -> int:
        """Get the number of samples in the dataset."""
        return len(self.samples)

    def get_labeled_count(self) -> int:
        """Get the number of labeled samples."""
        return sum(1 for s in self.samples if s.labeled)
