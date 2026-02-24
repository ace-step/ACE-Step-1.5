"""Scoring package: alignment and quality metrics for generated outputs."""
from acestep.core.scoring.dit_alignment import (
    MusicStampsAligner,
    TokenTimestamp,
    SentenceTimestamp,
)
from acestep.core.scoring.dit_score import MusicLyricScorer
from acestep.core.scoring.lm_score import (
    calculate_pmi_score_per_condition,
    calculate_reward_score,
)

__all__ = [
    "MusicStampsAligner",
    "TokenTimestamp",
    "SentenceTimestamp",
    "MusicLyricScorer",
    "calculate_pmi_score_per_condition",
    "calculate_reward_score",
]
