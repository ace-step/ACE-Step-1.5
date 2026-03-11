"""Results batch-management facade.

This thin compatibility module re-exports decomposed batch-management
functions and helper utilities so existing imports continue to work.
"""
from acestep.ui.gradio.events.results import batch_management_background as _background
from acestep.ui.gradio.events.results import batch_management_helpers as _helpers
from acestep.ui.gradio.events.results import batch_management_wrapper as _wrapper


generate_with_batch_management = _wrapper.generate_with_batch_management
generate_next_batch_background = _background.generate_next_batch_background

# Backward-compat helper exports for existing internal import paths.
_apply_param_defaults = _helpers._apply_param_defaults
_build_saved_params = _helpers._build_saved_params
_extract_scores = _helpers._extract_scores
_extract_ui_core_outputs = _helpers._extract_ui_core_outputs
_log_background_params = _helpers._log_background_params


__all__ = [
    "generate_with_batch_management",
    "generate_next_batch_background",
]
