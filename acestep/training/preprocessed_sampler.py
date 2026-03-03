"""Sampling utilities for preprocessed tensor training datasets."""

from __future__ import annotations

import random
from typing import Dict, List


class BucketedBatchSampler:
    """Batch sampler that groups indices by latent-length buckets."""

    def __init__(self, lengths: List[int], batch_size: int, shuffle: bool = True) -> None:
        """Initialize bucket sampler.

        Args:
            lengths: Per-sample latent lengths.
            batch_size: Number of items per yielded batch.
            shuffle: Whether to shuffle buckets and samples each epoch.
        """
        self.lengths = lengths
        self.batch_size = max(1, int(batch_size))
        self.shuffle = shuffle

    def __iter__(self):
        """Yield batches of indices grouped by coarse latent-length buckets."""
        buckets: Dict[int, List[int]] = {}
        for idx, length in enumerate(self.lengths):
            bucket = int(length // 64)
            buckets.setdefault(bucket, []).append(idx)

        bucket_keys = list(buckets.keys())
        if self.shuffle:
            random.shuffle(bucket_keys)

        for key in bucket_keys:
            group = buckets[key]
            if self.shuffle:
                random.shuffle(group)
            for start in range(0, len(group), self.batch_size):
                yield group[start:start + self.batch_size]

    def __len__(self) -> int:
        """Return estimated number of batches."""
        total = len(self.lengths)
        return (total + self.batch_size - 1) // self.batch_size
