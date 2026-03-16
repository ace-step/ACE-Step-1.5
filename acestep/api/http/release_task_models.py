"""Pydantic request model definitions used by the `/release_task` flow."""

from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

from acestep.constants import DEFAULT_DIT_INSTRUCTION


class GenerateMusicRequest(BaseModel):
    """Typed request payload model for generation jobs.

    This schema mirrors the historical `api_server` request contract so legacy
    clients remain compatible while route handling is decomposed.
    """

    prompt: str = Field(default="", description="Text prompt describing the music (local/per-track description for lego SFT)")
    global_caption: str = Field(default="", description="Global song description for SFT-stems lego tasks (full song context)")
    lyrics: str = Field(default="", description="Lyric text")

    # New API semantics:
    # - thinking=True: use 5Hz LM to generate audio codes (lm-dit behavior)
    # - thinking=False: do not use LM to generate codes (dit behavior)
    # Regardless of thinking, if some metas are missing, server may use LM to fill them.
    thinking: bool = False
    # Sample-mode requests auto-generate caption/lyrics/metas via LM (no user prompt).
    sample_mode: bool = False
    # Description for sample mode: auto-generate caption/lyrics from description query
    sample_query: str = Field(default="", description="Query/description for sample mode (use create_sample)")
    # Whether to use format_sample() to enhance input caption/lyrics
    use_format: bool = Field(default=False, description="Use format_sample() to enhance input (default: False)")
    # Model name for multi-model support (select which DiT model to use)
    model: Optional[str] = Field(default=None, description="Model name to use (e.g., 'acestep-v15-turbo')")

    bpm: Optional[int] = None
    key_scale: str = ""
    time_signature: str = ""
    vocal_language: str = "en"
    inference_steps: int = 8
    guidance_scale: float = 7.0
    use_random_seed: bool = True
    seed: Union[int, str] = -1

    reference_audio_path: Optional[str] = None
    src_audio_path: Optional[str] = None
    audio_duration: Optional[float] = None
    batch_size: Optional[int] = None

    repainting_start: float = 0.0
    repainting_end: Optional[float] = None

    instruction: str = DEFAULT_DIT_INSTRUCTION
    audio_cover_strength: float = 1.0
    cover_noise_strength: float = Field(
        default=0.0,
        description="Cover noise blending strength (0.0=pure noise, 1.0=closest to source audio). Used for cover/repaint tasks.",
    )
    audio_code_string: str = Field(
        default="",
        description="User-provided audio semantic codes string for code-control generation. When non-empty, skips LM code generation.",
    )
    task_type: str = "text2music"
    chunk_mask_mode: Literal["explicit", "auto"] = "auto"
    repaint_latent_crossfade_frames: int = Field(
        default=10,
        description="Latent-level boundary blend width in frames (25Hz, 10~0.4s)",
    )
    repaint_wav_crossfade_sec: float = Field(
        default=0.0,
        description="Waveform-level splice crossfade in seconds (0=hard cut)",
    )
    repaint_mode: Literal["conservative", "balanced", "aggressive"] = Field(
        default="balanced",
        description="Repaint preservation mode: conservative (max src retention), balanced (tunable), aggressive (pure diffusion)",
    )
    repaint_strength: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Balanced-mode repaint intensity: 0.0=conservative (max source preservation), 1.0=aggressive (pure diffusion). Only used in balanced mode.",
    )
    analysis_only: bool = False
    full_analysis_only: bool = False
    extract_codes_only: bool = False

    use_adg: bool = False
    cfg_interval_start: float = 0.0
    cfg_interval_end: float = 1.0
    infer_method: str = "ode"  # "ode" or "sde" - diffusion inference method
    shift: float = Field(
        default=3.0,
        description="Timestep shift factor (range 1.0~5.0, default 3.0). Only effective for base models, not turbo models.",
    )
    timesteps: Optional[str] = Field(
        default=None,
        description="Custom timesteps (comma-separated, e.g., '0.97,0.76,0.615,0.5,0.395,0.28,0.18,0.085,0'). Overrides inference_steps and shift.",
    )

    audio_format: str = Field(
        default="mp3",
        description="Output audio format. Supported formats: 'flac', 'mp3', 'opus', 'aac', 'wav', 'wav32'. Default: 'mp3'",
    )
    use_tiled_decode: bool = True

    # 5Hz LM (server-side): used for metadata completion and (when thinking=True) codes generation.
    lm_model_path: Optional[str] = None  # e.g. "acestep-5Hz-lm-0.6B"
    lm_backend: Literal["vllm", "pt", "mlx"] = "vllm"

    constrained_decoding: bool = True
    constrained_decoding_debug: bool = False
    use_cot_caption: bool = True
    use_cot_language: bool = True
    is_format_caption: bool = False
    allow_lm_batch: bool = True
    track_name: Optional[str] = None
    track_classes: Optional[List[str]] = None

    lm_temperature: float = 0.85
    lm_cfg_scale: float = 2.5
    lm_top_k: Optional[int] = None
    lm_top_p: Optional[float] = 0.9
    lm_repetition_penalty: float = 1.0
    lm_negative_prompt: str = "NO USER INPUT"

    class Config:
        """Legacy pydantic config preserving prior population semantics."""

        allow_population_by_field_name = True
        allow_population_by_alias = True
