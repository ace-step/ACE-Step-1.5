"""Generation metadata file-load wiring helpers."""

from typing import Any, Sequence

from .. import generation_handlers as gen_h
from ..generation.metadata_model_restore import restore_models_from_metadata
from .context import GenerationWiringContext


_LOAD_METADATA_GENERATION_OUTPUT_KEYS = (
    "task_type",
    "captions",
    "lyrics",
    "vocal_language",
    "bpm",
    "key_scale",
    "time_signature",
    "audio_duration",
    "batch_size_input",
    "inference_steps",
    "guidance_scale",
    "seed",
    "random_seed_checkbox",
    "use_adg",
    "cfg_interval_start",
    "cfg_interval_end",
    "shift",
    "infer_method",
    "custom_timesteps",
    "audio_format",
    "mp3_controls_row",
    "mp3_bitrate",
    "mp3_sample_rate",
    "lm_temperature",
    "lm_cfg_scale",
    "lm_top_k",
    "lm_top_p",
    "lm_negative_prompt",
    "use_cot_metas",
    "use_cot_caption",
    "use_cot_language",
    "audio_cover_strength",
    "cover_noise_strength",
    "think_checkbox",
    "text2music_audio_code_string",
    "repainting_start",
    "repainting_end",
    "track_name",
    "complete_track_classes",
    "instrumental_checkbox",
    "retake_variance",
    "retake_seed",
)


def _build_load_metadata_outputs(context: GenerationWiringContext) -> list[Any]:
    """Return ordered outputs for the metadata file-load upload handler."""

    generation_section = context.generation_section
    results_section = context.results_section
    outputs = [
        generation_section[key] for key in _LOAD_METADATA_GENERATION_OUTPUT_KEYS
    ]
    outputs.append(results_section["is_format_caption_state"])
    return outputs


def register_generation_metadata_file_handlers(
    context: GenerationWiringContext,
    *,
    auto_checkbox_inputs: Sequence[Any],
    auto_checkbox_outputs: Sequence[Any],
) -> None:
    """Register metadata load-file upload and auto-checkbox sync handlers."""

    generation_section = context.generation_section
    results_section = context.results_section
    llm_handler = context.llm_handler

    def load_metadata_and_models(file_obj, current_dit):
        """Load parameters, then model selectors, from one uploaded JSON.

        Both run in the same handler: the UploadButton value is already
        cleared when a chained ``.then`` step runs.
        """
        params = tuple(gen_h.load_metadata(file_obj, llm_handler))
        models = restore_models_from_metadata(
            file_obj, current_dit, context.dit_handler, llm_handler
        )
        return params + models

    generation_section["load_file"].upload(
        fn=load_metadata_and_models,
        inputs=[generation_section["load_file"], generation_section["config_path"]],
        outputs=_build_load_metadata_outputs(context) + [
            generation_section["config_path"],
            generation_section["lm_model_path"],
            generation_section["vae_checkpoint"],
            results_section["keep_loaded_params_state"],
        ],
    ).then(
        fn=gen_h.uncheck_auto_for_populated_fields,
        inputs=list(auto_checkbox_inputs),
        outputs=list(auto_checkbox_outputs),
    )
