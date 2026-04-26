# Re-export from canonical location to avoid duplication.
# All model variants that use APG/ADG guidance share the same implementation.
from acestep.models.common.apg_guidance import (
    MomentumBuffer,
    adg_forward,
    adg_w_norm_forward,
    adg_wo_clip_forward,
    apg_forward,
    cfg_forward,
    call_cos_tensor,
    compute_perpendicular_component,
    project,
)

__all__ = [
    "MomentumBuffer",
    "adg_forward",
    "adg_w_norm_forward",
    "adg_wo_clip_forward",
    "apg_forward",
    "cfg_forward",
    "call_cos_tensor",
    "compute_perpendicular_component",
    "project",
]
