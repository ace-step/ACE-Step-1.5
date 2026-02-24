"""Generation handlers sub-package.

Re-exports all public symbols so callers can import from
``acestep.ui.gradio.events.generation`` directly.
"""

from .validation import (
    clamp_duration_to_gpu_limit,
    parse_and_validate_timesteps,
    _has_reference_audio,
    _extract_audio_path,
    validate_uploaded_audio_file,
    _contains_audio_code_tokens,
)
from .metadata_loading import (
    load_metadata,
    load_random_example,
    sample_example_smart,
    load_random_simple_description,
)
from .service_init import (
    refresh_checkpoints,
    init_service_wrapper,
    on_tier_change,
)
from .model_config import (
    is_pure_base_model,
    update_model_type_settings,
    get_ui_control_config,
    get_model_type_ui_settings,
    get_generation_mode_choices,
)
from .mode_ui import (
    compute_mode_ui_updates,
    handle_generation_mode_change,
    handle_extract_track_name_change,
    handle_extract_src_audio_change,
)
from .llm_actions import (
    handle_create_sample,
    handle_format_sample,
    handle_format_caption,
    handle_format_lyrics,
    transcribe_audio_codes,
    analyze_src_audio,
)
from .ui_helpers import (
    update_negative_prompt_visibility,
    on_auto_checkbox_change,
    reset_all_auto,
    uncheck_auto_for_populated_fields,
    update_audio_cover_strength_visibility,
    convert_src_audio_to_codes_wrapper,
    update_instruction_ui,
    update_transcribe_button_text,
    reset_format_caption_flag,
    update_audio_uploads_accordion,
    handle_instrumental_checkbox,
    handle_simple_instrumental_change,
    update_audio_components_visibility,
)
