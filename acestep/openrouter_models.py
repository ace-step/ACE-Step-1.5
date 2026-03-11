"""OpenRouter API compatible Pydantic models for ACE-Step.

This module defines request/response models that conform to OpenRouter's
chat completions API specification for audio generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# =============================================================================
# Request Models
# =============================================================================

class AudioInputContent(BaseModel):
    """Audio input content in base64 format."""
    data: str = Field(..., description="Base64-encoded audio data")
    format: str = Field(default="mp3", description="Audio format (mp3, wav, flac, etc.)")


class TextContent(BaseModel):
    """Text content block."""
    type: Literal["text"] = "text"
    text: str = Field(..., description="Text content")


class AudioContent(BaseModel):
    """Audio input content block."""
    type: Literal["input_audio"] = "input_audio"
    input_audio: AudioInputContent


# Union type for message content
ContentPart = Union[TextContent, AudioContent, Dict[str, Any]]


class ChatMessage(BaseModel):
    """A single message in the chat conversation."""
    role: Literal["system", "user", "assistant"] = Field(..., description="Message role")
    content: Union[str, List[ContentPart]] = Field(..., description="Message content")
    name: Optional[str] = Field(default=None, description="Optional name for the message author")


class AudioConfig(BaseModel):
    """Audio generation configuration."""
    duration: Optional[float] = Field(default=None, description="Target audio duration in seconds")
    format: str = Field(default="mp3", description="Output audio format")
    # ACE-Step specific parameters
    bpm: Optional[int] = Field(default=None, description="Beats per minute")
    key_scale: Optional[str] = Field(default=None, description="Musical key and scale")
    time_signature: Optional[str] = Field(default=None, description="Time signature (e.g., 4/4)")
    vocal_language: Optional[str] = Field(default=None, description="Vocal language code")
    instrumental: Optional[bool] = Field(default=None, description="Generate instrumental only")


class ChatCompletionRequest(BaseModel):
    """OpenRouter-compatible chat completion request."""
    model: str = Field(..., description="Model ID to use")
    messages: List[ChatMessage] = Field(..., description="List of messages")

    # Modalities
    modalities: Optional[List[str]] = Field(
        default=None,
        description="Output modalities (e.g., ['audio', 'text'])"
    )

    # Audio configuration
    audio_config: Optional[AudioConfig] = Field(
        default=None,
        description="Audio generation configuration"
    )

    # Standard OpenAI parameters
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    top_k: Optional[int] = Field(default=None, ge=0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: bool = Field(default=False, description="Enable streaming response")
    stop: Optional[Union[str, List[str]]] = Field(default=None)
    seed: Optional[Union[int, str]] = Field(default=None, description="Seed(s) for reproducibility. Comma-separated for batch (e.g. '42,123,456')")

    # ACE-Step specific parameters (extended)
    thinking: Optional[bool] = Field(default=None, description="Use LM for audio code generation")
    guidance_scale: Optional[float] = Field(default=None, description="Classifier-free guidance scale")
    batch_size: Optional[int] = Field(default=None, description="Number of audio samples to generate")

    # ACE-Step direct fields (bypass message parsing / audio_config)
    lyrics: str = Field(default="", description="Direct lyrics input (bypass message parsing)")
    sample_mode: bool = Field(default=False, description="Auto-generate caption/lyrics/metas via LM; user message becomes the query")
    use_format: bool = Field(default=False, description="Use format_sample to enhance caption/lyrics")
    use_cot_caption: bool = Field(default=True, description="Use CoT for caption rewriting")
    use_cot_language: bool = Field(default=True, description="Use CoT for language detection")

    # Task type
    task_type: str = Field(default="text2music", description="Task type: text2music, cover, repaint, extract, lego, complete")

    # Audio editing parameters
    repainting_start: float = Field(default=0.0, description="Repainting region start (seconds)")
    repainting_end: Optional[float] = Field(default=None, description="Repainting region end (seconds)")
    audio_cover_strength: float = Field(default=1.0, description="Audio cover strength (0.0~1.0)")

    # Extended fields for ComfyUI node compatibility
    audio_codes: str = Field(default="", description="Pre-computed audio codes (bypass auto-conversion)")
    cover_noise_strength: float = Field(default=0.0, description="Cover noise strength (0=pure noise, 1=closest to src)")
    inference_steps: int = Field(default=8, description="Number of diffusion inference steps")
    infer_method: str = Field(default="ode", description="Diffusion inference method: 'ode' or 'sde'")
    lm_cfg_scale: float = Field(default=2.0, description="LM classifier-free guidance scale")
    use_cot_metas: Optional[bool] = Field(default=None, description="Use CoT for metadata generation (auto if None)")

    class Config:
        extra = "allow"  # Allow additional fields for forward compatibility


# =============================================================================
# Response Models
# =============================================================================

class AudioOutputUrl(BaseModel):
    """Audio output URL (base64 data URL)."""
    url: str = Field(..., description="Base64 data URL of the audio")


class AudioOutput(BaseModel):
    """Audio output content block."""
    type: Literal["audio_url"] = "audio_url"
    audio_url: AudioOutputUrl


class AssistantMessage(BaseModel):
    """Assistant response message."""
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = Field(default=None, description="Text content")
    audio: Optional[List[AudioOutput]] = Field(default=None, description="Generated audio files")
    audio_codes: Optional[str] = Field(default=None, description="Generated audio codes")


class Choice(BaseModel):
    """A single completion choice."""
    index: int = Field(default=0)
    message: AssistantMessage
    finish_reason: Literal["stop", "length", "content_filter", "error"] = "stop"


class Usage(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenRouter-compatible chat completion response."""
    id: str = Field(..., description="Unique completion ID")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(..., description="Unix timestamp")
    model: str = Field(..., description="Model ID used")
    choices: List[Choice] = Field(..., description="Completion choices")
    usage: Usage = Field(default_factory=Usage)

    # Extended metadata
    system_fingerprint: Optional[str] = Field(default=None)


# =============================================================================
# Streaming Response Models
# =============================================================================

class DeltaContent(BaseModel):
    """Delta content for streaming."""
    role: Optional[Literal["assistant"]] = None
    content: Optional[str] = None
    audio: Optional[List[AudioOutput]] = None


class StreamChoice(BaseModel):
    """Streaming choice."""
    index: int = 0
    delta: DeltaContent
    finish_reason: Optional[Literal["stop", "length", "content_filter", "error"]] = None


class ChatCompletionChunk(BaseModel):
    """Streaming chunk response."""
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[StreamChoice]


# =============================================================================
# Models Endpoint Response
# =============================================================================

class ModelPricing(BaseModel):
    """Model pricing information."""
    prompt: str = Field(default="0", description="Price per prompt token in USD")
    completion: str = Field(default="0", description="Price per completion token in USD")
    request: str = Field(default="0", description="Price per request in USD")
    image: str = Field(default="0", description="Price per image in USD")


class ModelInfo(BaseModel):
    """OpenRouter-compatible model information."""
    id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Display name")
    created: int = Field(..., description="Unix timestamp of creation")

    # Modalities
    input_modalities: List[str] = Field(
        default_factory=lambda: ["text"],
        description="Supported input modalities"
    )
    output_modalities: List[str] = Field(
        default_factory=lambda: ["audio", "text"],
        description="Supported output modalities"
    )

    # Limits
    context_length: int = Field(default=4096, description="Maximum context length")
    max_output_length: int = Field(default=300, description="Maximum output length in seconds")

    # Pricing
    pricing: ModelPricing = Field(default_factory=ModelPricing)

    # Metadata
    description: Optional[str] = Field(default=None)
    architecture: Optional[Dict[str, Any]] = Field(default=None)


class ModelsResponse(BaseModel):
    """Response for /v1/models endpoint."""
    object: Literal["list"] = "list"
    data: List[ModelInfo] = Field(default_factory=list)


# =============================================================================
# Error Response
# =============================================================================

class ErrorDetail(BaseModel):
    """Error detail information."""
    message: str
    type: str = "invalid_request_error"
    param: Optional[str] = None
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """OpenRouter-compatible error response."""
    error: ErrorDetail
