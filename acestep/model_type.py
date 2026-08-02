"""Shared turbo/non-turbo model-name classification.

Used to pick a sensible default for DCW (Differential Correction in Wavelet
domain): DCW should default on for turbo (distilled) models and off for
non-turbo (sft/base) models, matching the Gradio UI's behavior since #1207.
See issue #1259 for the distorted-audio symptom when DCW is left on for
non-turbo models.

Both `cli.py` and `acestep/api/job_generation_setup.py` import this so the
CLI and the REST API can't silently diverge from each other (or from the
Gradio UI) the way `cli.py` previously diverged, causing #1259.
"""

import re
from typing import Optional


def is_turbo_model_path(config_path: Optional[str]) -> bool:
    """Check whether a DiT config/model path refers to a turbo (distilled) model.

    Matches "turbo" as a delimited token (bounded by start/end of string or a
    path/name delimiter), e.g. "acestep-v15-turbo" or "acestep-v15-xl-turbo",
    but not an unrelated model name that merely contains "turbo" as part of a
    longer word.
    """
    if not config_path:
        return False
    return re.search(r"(^|[\\/._-])turbo($|[\\/._-])", str(config_path).lower()) is not None
