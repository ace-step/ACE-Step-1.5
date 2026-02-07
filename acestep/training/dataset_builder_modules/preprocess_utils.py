import random
from typing import List, Set

from .models import AudioSample


def select_genre_indices(samples: List[AudioSample], genre_ratio: int) -> Set[int]:
    """Select indices that should use genre, based on ratio."""
    num_genre_samples = int(len(samples) * genre_ratio / 100)
    random.seed(42)
    all_indices = list(range(len(samples)))
    random.shuffle(all_indices)
    return set(all_indices[:num_genre_samples])


def build_metas_str(sample: AudioSample) -> str:
    """Construct metadata string for text prompt."""
    return (
        f"- bpm: {sample.bpm if sample.bpm else 'N/A'}\n"
        f"- timesignature: {sample.timesignature if sample.timesignature else 'N/A'}\n"
        f"- keyscale: {sample.keyscale if sample.keyscale else 'N/A'}\n"
        f"- duration: {sample.duration} seconds\n"
    )
