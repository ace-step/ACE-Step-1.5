"""Generation parameter/config assembly helpers for API job execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from acestep.inference import GenerationConfig, GenerationParams

# Sensible fallback when the API receives a null/missing audio_duration.
# This prevents -1.0/None from propagating into the LLM and DiT, which
# can cause unconstrained code generation and downstream tensor mismatches.
_API_DEFAULT_DURATION_SECONDS: float = 120.0


@dataclass
class GenerationSetup:
    """Prepared generation objects for a single API job."""

    params: GenerationParams
    config: GenerationConfig


def _resolve_instruction(
    *,
    req: Any,
    default_dit_instruction: str,
    task_instructions: dict[str, str],
) -> str:
    """Resolve task-specific instruction text for generation.

    Args:
        req: Request object with task_type and optional track fields.
        default_dit_instruction: Default instruction fallback.
        task_instructions: Task-type instruction templates.

    Returns:
        str: Instruction to pass to generation.
    """

    instruction_to_use = req.instruction
    should_resolve = (
        not instruction_to_use or not instruction_to_use.strip()
        or instruction_to_use == default_dit_instruction
    ) and req.task_type in task_instructions
    if should_resolve:
        raw_instruction = task_instructions[req.task_type]

        if req.task_type == "complete":
            if req.track_classes:
                classes_str = " | ".join([str(track).upper() for track in req.track_classes])
                instruction_to_use = raw_instruction.format(TRACK_CLASSES=classes_str)
            else:
                instruction_to_use = task_instructions.get("complete_default", raw_instruction)
        elif "{TRACK_NAME}" in raw_instruction:
            if req.track_name:
                instruction_to_use = raw_instruction.format(TRACK_NAME=req.track_name.upper())
            else:
                # Fall back to default instruction when track_name is missing
                # to avoid sending literal {TRACK_NAME} placeholder to the model
                default_key = f"{req.task_type}_default"
                instruction_to_use = task_instructions.get(default_key, raw_instruction)
        else:
            instruction_to_use = raw_instruction

    return instruction_to_use


def _resolve_generation_seeds(req: Any) -> Optional[list[int]]:
    """Resolve request seed input into GenerationConfig.seeds format.

    Args:
        req: Request object with use_random_seed and seed values.

    Returns:
        Optional[list[int]]: Seed list when explicit deterministic seeds are usable.
    """

    resolved_seeds = None
    if not req.use_random_seed and req.seed is not None:
        if isinstance(req.seed, int):
            if req.seed >= 0:
                resolved_seeds = [req.seed]
        elif isinstance(req.seed, str):
            resolved_seeds = []
            for value in req.seed.split(","):
                value = value.strip()
                if value and value != "-1":
                    try:
                        resolved_seeds.append(int(float(value)))
                    except (ValueError, TypeError):
                        pass
            if not resolved_seeds:
                resolved_seeds = None
    return resolved_seeds


def build_generation_setup(
    *,
    req: Any,
    caption: str,
    global_caption: str = "",
    lyrics: str,
    bpm: Any,
    key_scale: Any,
    time_signature: Any,
    audio_duration: Any,
    thinking: bool,
    sample_mode: bool,
    format_has_duration: bool,
    use_cot_caption: bool,
    use_cot_language: bool,
    lm_top_k: int,
    lm_top_p: float,
    parse_timesteps: Callable[[Optional[str]], Optional[list[float]]],
    is_instrumental: Callable[[str], bool],
    default_dit_instruction: str,
    task_instructions: dict[str, str],
) -> GenerationSetup:
    """Build GenerationParams and GenerationConfig from request and prepared LLM inputs.

    Args:
        req: Request object for music generation.
        caption: Final caption text to generate from.
        lyrics: Final lyrics text to generate from.
        bpm: Optional BPM metadata.
        key_scale: Optional keyscale metadata.
        time_signature: Optional time signature metadata.
        audio_duration: Optional target duration metadata.
        thinking: Whether LM code generation mode is enabled.
        sample_mode: Whether sample mode generated metadata already.
        format_has_duration: Whether format mode already produced duration metadata.
        use_cot_caption: Optional CoT caption enhancement flag.
        use_cot_language: Optional CoT language enhancement flag.
        lm_top_k: Normalized LM top-k sampling value.
        lm_top_p: Normalized LM top-p sampling value.
        parse_timesteps: Timesteps parsing callback.
        is_instrumental: Instrumental detection callback.
        default_dit_instruction: Default instruction constant.
        task_instructions: Task instruction mapping.

    Returns:
        GenerationSetup: Prepared params/config pair for `generate_music`.
    """

    parsed_timesteps = parse_timesteps(req.timesteps)
    instruction_to_use = _resolve_instruction(
        req=req,
        default_dit_instruction=default_dit_instruction,
        task_instructions=task_instructions,
    )

    params = GenerationParams(
        task_type=req.task_type,
        instruction=instruction_to_use,
        reference_audio=req.reference_audio_path,
        src_audio=req.src_audio_path,
        audio_codes=req.audio_code_string if req.audio_code_string else "",
        caption=caption,
        global_caption=global_caption,
        lyrics=lyrics,
        instrumental=is_instrumental(lyrics),
        vocal_language=req.vocal_language,
        bpm=bpm,
        keyscale=key_scale,
        timesignature=time_signature,
        duration=audio_duration if (audio_duration and audio_duration > 0) else _API_DEFAULT_DURATION_SECONDS,
        inference_steps=req.inference_steps,
        seed=req.seed,
        guidance_scale=req.guidance_scale,
        use_adg=req.use_adg,
        cfg_interval_start=req.cfg_interval_start,
        cfg_interval_end=req.cfg_interval_end,
        shift=req.shift,
        infer_method=req.infer_method,
        timesteps=parsed_timesteps,
        repainting_start=req.repainting_start,
        repainting_end=req.repainting_end if req.repainting_end else -1,
        chunk_mask_mode=getattr(req, "chunk_mask_mode", "auto"),
        repaint_latent_crossfade_frames=getattr(
            req, "repaint_latent_crossfade_frames", 10,
        ),
        repaint_wav_crossfade_sec=getattr(
            req, "repaint_wav_crossfade_sec", 0.0,
        ),
        repaint_mode=getattr(req, "repaint_mode", "balanced"),
        repaint_strength=getattr(req, "repaint_strength", 0.5),
        audio_cover_strength=req.audio_cover_strength,
        cover_noise_strength=req.cover_noise_strength,
        thinking=thinking,
        lm_temperature=req.lm_temperature,
        lm_cfg_scale=req.lm_cfg_scale,
        lm_top_k=lm_top_k,
        lm_top_p=lm_top_p,
        lm_negative_prompt=req.lm_negative_prompt,
        use_cot_metas=not sample_mode and not format_has_duration,
        use_cot_caption=use_cot_caption,
        use_cot_language=use_cot_language,
        use_constrained_decoding=True,
    )

    batch_size = req.batch_size if req.batch_size is not None else 2
    config = GenerationConfig(
        batch_size=batch_size,
        allow_lm_batch=req.allow_lm_batch,
        use_random_seed=req.use_random_seed,
        seeds=_resolve_generation_seeds(req),
        audio_format=req.audio_format,
        constrained_decoding_debug=req.constrained_decoding_debug,
    )

    return GenerationSetup(params=params, config=config)
