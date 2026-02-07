from typing import Tuple

from .models import AudioSample


class UpdateSampleMixin:
    """Sample update helpers."""

    def update_sample(self, sample_idx: int, **kwargs) -> Tuple[AudioSample, str]:
        """Update a sample's metadata."""
        if sample_idx < 0 or sample_idx >= len(self.samples):
            return None, f"❌ Invalid sample index: {sample_idx}"

        sample = self.samples[sample_idx]

        for key, value in kwargs.items():
            if hasattr(sample, key):
                setattr(sample, key, value)

        self.samples[sample_idx] = sample
        return sample, f"✅ Updated: {sample.filename}"
