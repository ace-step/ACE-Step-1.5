"""
ACE-Step Training V2 (Side-Step) -- Corrected LoRA Fine-Tuning CLI

Non-destructive parallel module providing corrected training procedures
that match each model variant's own forward() training logic.

Subcommands:
    vanilla   -- Reproduce existing (bugged) training for backward compatibility
    fixed     -- Corrected training: continuous timesteps + CFG dropout
    estimate  -- Gradient sensitivity analysis (no training)

Note:
    This is the upstream-integrated version of Side-Step.
    For the standalone version with additional features and more
    frequent updates, visit: https://github.com/koda-dernet/Side-Step
"""

__version__ = "2.0.0"
