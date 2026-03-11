"""OpenRouter API adapter for ACE-Step music generation.

This module provides OpenRouter-compatible endpoints that wrap the ACE-Step
music generation API, mounted as a sub-router on the main api_server.

All generation requests go through the shared asyncio.Queue, ensuring unified
GPU scheduling with release_task.

Endpoints:
- POST /v1/chat/completions  - Generate music via chat completion format
- GET  /v1/models            - List available models (OpenRouter format)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import tempfile
import time
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from acestep.openrouter_models import (
    AudioConfig,
    ChatCompletionRequest,
    ModelInfo,
    ModelPricing,
    ModelsResponse,
)


# =============================================================================
# Constants
# =============================================================================

MODEL_PREFIX = "acestep"
DEFAULT_AUDIO_FORMAT = "mp3"

# Generation timeout for non-streaming requests (seconds)
GENERATION_TIMEOUT = int(os.environ.get("ACESTEP_GENERATION_TIMEOUT", "600"))


# =============================================================================
# Helper Functions
# =============================================================================

def _generate_completion_id() -> str:
    """Generate a unique completion ID."""
    return f"chatcmpl-{os.urandom(8).hex()}"


def _get_model_id(model_name: str) -> str:
    """Convert internal model name to OpenRouter model ID."""
    return f"{MODEL_PREFIX}/{model_name}"


def _parse_model_name(model_id: str) -> str:
    """Extract internal model name from OpenRouter model ID."""
    if "/" in model_id:
        return model_id.split("/", 1)[1]
    return model_id


def _audio_to_base64_url(audio_path: str, audio_format: str = "mp3") -> str:
    """Convert audio file to base64 data URL."""
    if not audio_path or not os.path.exists(audio_path):
        return ""

    mime_types = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "flac": "audio/flac",
        "ogg": "audio/ogg",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
    }
    mime_type = mime_types.get(audio_format.lower(), "audio/mpeg")

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    b64_data = base64.b64encode(audio_data).decode("utf-8")
    return f"data:{mime_type};base64,{b64_data}"


def _format_lm_content(result: Dict[str, Any]) -> str:
    """Format generation result as content string with metadata and lyrics."""
    metas = result.get("metas", {})
    lyrics = result.get("lyrics", "")

    parts = []

    # Add metadata section
    meta_lines = []
    caption = metas.get("prompt") or metas.get("caption") or result.get("prompt", "")
    if caption:
        meta_lines.append(f"**Caption:** {caption}")
    if metas.get("bpm") and metas["bpm"] != "N/A":
        meta_lines.append(f"**BPM:** {metas['bpm']}")
    if metas.get("duration") and metas["duration"] != "N/A":
        meta_lines.append(f"**Duration:** {metas['duration']}s")
    if metas.get("keyscale") and metas["keyscale"] != "N/A":
        meta_lines.append(f"**Key:** {metas['keyscale']}")
    if metas.get("timesignature") and metas["timesignature"] != "N/A":
        meta_lines.append(f"**Time Signature:** {metas['timesignature']}")

    if meta_lines:
        parts.append("## Metadata\n" + "\n".join(meta_lines))

    # Add lyrics section
    if lyrics and lyrics.strip() and lyrics.strip().lower() not in ("[inst]", "[instrumental]"):
        parts.append(f"## Lyrics\n{lyrics}")

    if parts:
        return "\n\n".join(parts)
    else:
        return "Music generated successfully."


def _base64_to_temp_file(b64_data: str, audio_format: str = "mp3") -> str:
    """Save base64 audio data to temporary file."""
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]

    audio_bytes = base64.b64decode(b64_data)
    suffix = f".{audio_format}" if not audio_format.startswith(".") else audio_format
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="openrouter_audio_")
    os.close(fd)

    with open(path, "wb") as f:
        f.write(audio_bytes)

    return path


class _AudioBlob(NamedTuple):
    """Deferred audio data extracted from a message (not yet on disk)."""

    data: str
    format: str


def _materialize_audio_files(
    blobs: List[_AudioBlob],
) -> List[str]:
    """Write deferred audio blobs to temporary files.

    Args:
        blobs: Audio blobs extracted by _parse_messages.

    Returns:
        List of temp file paths (caller must ensure cleanup).
    """
    paths: List[str] = []
    for blob in blobs:
        try:
            path = _base64_to_temp_file(blob.data, blob.format)
            paths.append(path)
        except Exception:
            pass
    return paths


def _cleanup_temp_paths(paths: List[str]) -> None:
    """Remove temporary files, ignoring errors."""
    for p in paths:
        try:
            os.remove(p)
        except Exception:
            pass


def _extract_tagged_content(text: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    Extract content from <prompt> and <lyrics> tags.

    Returns:
        (prompt, lyrics, remaining_text)
    """
    prompt = None
    lyrics = None
    remaining = text

    prompt_match = re.search(r'<prompt>(.*?)</prompt>', text, re.DOTALL | re.IGNORECASE)
    if prompt_match:
        prompt = prompt_match.group(1).strip()
        remaining = remaining.replace(prompt_match.group(0), '').strip()

    lyrics_match = re.search(r'<lyrics>(.*?)</lyrics>', text, re.DOTALL | re.IGNORECASE)
    if lyrics_match:
        lyrics = lyrics_match.group(1).strip()
        remaining = remaining.replace(lyrics_match.group(0), '').strip()

    return prompt, lyrics, remaining


def _looks_like_lyrics(text: str) -> bool:
    """Heuristic to detect if text looks like song lyrics."""
    if not text:
        return False

    lyrics_markers = [
        "[verse", "[chorus", "[bridge", "[intro", "[outro",
        "[hook", "[pre-chorus", "[refrain", "[inst",
    ]
    text_lower = text.lower()
    for marker in lyrics_markers:
        if marker in text_lower:
            return True

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) >= 4:
        avg_line_length = sum(len(line) for line in lines) / len(lines)
        if avg_line_length < 60:
            return True

    return False


def _is_instrumental(lyrics: str) -> bool:
    """Check if the music should be instrumental based on lyrics."""
    if not lyrics:
        return True
    lyrics_clean = lyrics.strip().lower()
    if not lyrics_clean:
        return True
    return lyrics_clean in ("[inst]", "[instrumental]")


def _parse_messages(
    messages: List[Any],
) -> Tuple[str, str, List[_AudioBlob], Optional[str]]:
    """Parse chat messages to extract prompt, lyrics, and audio references.

    Only processes the last user message (consistent with server behavior).
    Audio data is returned as deferred blobs — no temp files are created.
    Call _materialize_audio_files to write them to disk.

    Returns:
        (prompt, lyrics, audio_blobs, sample_query)
    """
    prompt = ""
    lyrics = ""
    sample_query = None
    audio_blobs: List[_AudioBlob] = []

    # Process only the last user message
    for msg in reversed(messages):
        if msg.role != "user" or not msg.content:
            continue

        content = msg.content

        # Handle multimodal content (list of parts)
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    part_type = part.get("type", "")
                    if part_type == "text":
                        text_parts.append(
                            part.get("text", "").strip()
                        )
                    elif part_type == "input_audio":
                        ad = part.get("input_audio", {})
                        if isinstance(ad, dict):
                            b64 = ad.get("data", "")
                            fmt = ad.get("format", "mp3")
                            if b64:
                                audio_blobs.append(
                                    _AudioBlob(b64, fmt)
                                )
                elif hasattr(part, "type"):
                    if part.type == "text":
                        text_parts.append(
                            getattr(part, "text", "").strip()
                        )
                    elif part.type == "input_audio":
                        ad = getattr(part, "input_audio", None)
                        if ad:
                            b64 = getattr(ad, "data", "")
                            fmt = getattr(ad, "format", "mp3")
                            if b64:
                                audio_blobs.append(
                                    _AudioBlob(b64, fmt)
                                )
            content = "\n".join(text_parts).strip()
        else:
            content = content.strip()

        if not content:
            break

        # Try to extract tagged content first
        tagged_prompt, tagged_lyrics, remaining = (
            _extract_tagged_content(content)
        )

        if tagged_prompt is not None or tagged_lyrics is not None:
            prompt = tagged_prompt or ""
            lyrics = tagged_lyrics or ""
            if remaining and not prompt:
                prompt = remaining
        else:
            # No tags - use heuristic detection
            if _looks_like_lyrics(content):
                lyrics = content
            else:
                prompt = content
        break

    return prompt, lyrics, audio_blobs, sample_query


def _to_generate_music_request(
    req: ChatCompletionRequest,
    prompt: str,
    lyrics: str,
    sample_query: Optional[str],
    reference_audio_path: Optional[str],
    src_audio_path: Optional[str],
    audio_codes: str = "",
):
    """
    Convert OpenRouter ChatCompletionRequest to api_server's GenerateMusicRequest.

    Audio routing depends on task_type:
      text2music:           audio[0] → reference_audio
      cover/repaint/lego/…: audio[0] → src_audio, audio[1] → reference_audio

    Uses late import to avoid circular dependency with api_server.
    """
    from acestep.api_server import GenerateMusicRequest

    audio_config = req.audio_config or AudioConfig()

    # Resolve parameters from audio_config only
    resolved_instrumental = audio_config.instrumental if audio_config.instrumental is not None else False

    # If instrumental, set lyrics to [inst]
    resolved_lyrics = lyrics
    if req.lyrics:
        resolved_lyrics = req.lyrics
    if resolved_instrumental and not resolved_lyrics:
        resolved_lyrics = "[inst]"

    # Resolve sample_mode: explicit field takes priority, then auto-detect from messages
    resolved_sample_mode = req.sample_mode
    resolved_sample_query = sample_query or ""

    # Resolve seed: pass through as-is (int or comma-separated string)
    # handler.prepare_seeds() handles both formats
    resolved_seed = req.seed if req.seed is not None else -1
    use_random_seed = req.seed is None

    return GenerateMusicRequest(
        # Text input
        prompt=prompt,
        lyrics=resolved_lyrics,
        sample_query=resolved_sample_query,
        sample_mode=resolved_sample_mode,

        # Music metadata
        bpm=audio_config.bpm,
        key_scale=audio_config.key_scale or "",
        time_signature=audio_config.time_signature or "",
        audio_duration=audio_config.duration if audio_config.duration else None,
        vocal_language=audio_config.vocal_language or "en",

        # LM parameters
        lm_temperature=req.temperature if req.temperature is not None else 0.85,
        lm_top_p=req.top_p if req.top_p is not None else 0.9,
        lm_top_k=req.top_k if req.top_k is not None else 0,
        lm_cfg_scale=req.lm_cfg_scale,
        thinking=req.thinking if req.thinking is not None else False,

        # Generation parameters
        inference_steps=req.inference_steps,
        infer_method=req.infer_method,
        guidance_scale=req.guidance_scale if req.guidance_scale is not None else 7.0,
        seed=resolved_seed,
        use_random_seed=use_random_seed,
        batch_size=req.batch_size if req.batch_size is not None else 1,

        # Task type
        task_type=req.task_type,

        # Audio paths
        reference_audio_path=reference_audio_path or None,
        src_audio_path=src_audio_path or None,

        # Audio editing
        repainting_start=req.repainting_start,
        repainting_end=req.repainting_end,
        audio_cover_strength=req.audio_cover_strength,

        # Format / CoT control
        use_format=req.use_format,
        use_cot_caption=req.use_cot_caption,
        use_cot_language=req.use_cot_language,

        # Model selection
        model=_parse_model_name(req.model),

        # Audio format
        audio_format=(audio_config.format or DEFAULT_AUDIO_FORMAT),
    )


def _build_openrouter_response(
    rec: Any,
    model_id: str,
    audio_format: str,
) -> JSONResponse:
    """Build OpenRouter non-streaming response from a completed JobRecord."""
    if rec.status != "succeeded" or not rec.result:
        error_msg = rec.error or "Generation failed"
        raise HTTPException(status_code=500, detail=error_msg)

    result = rec.result
    completion_id = _generate_completion_id()
    created_timestamp = int(time.time())

    text_content = _format_lm_content(result)

    # Encode audio
    audio_obj = None
    raw_audio_paths = result.get("raw_audio_paths", [])
    if raw_audio_paths:
        audio_path = raw_audio_paths[0]
        if audio_path and os.path.exists(audio_path):
            b64_url = _audio_to_base64_url(audio_path, audio_format)
            if b64_url:
                audio_obj = [{
                    "type": "audio_url",
                    "audio_url": {"url": b64_url},
                }]

    # Extract audio_codes from result if available
    audio_codes = result.get("audio_codes") or None

    response_data = {
        "id": completion_id,
        "object": "chat.completion",
        "created": created_timestamp,
        "model": model_id,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": text_content,
                "audio": audio_obj,
                "audio_codes": audio_codes,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }

    return JSONResponse(content=response_data)


async def _openrouter_stream_generator(
    rec: Any,
    model_id: str,
    audio_format: str,
):
    """
    SSE stream generator that reads from rec.progress_queue.

    Yields heartbeat chunks every 2 seconds while waiting for the
    queue worker to push the generation result.
    """
    completion_id = _generate_completion_id()
    created_timestamp = int(time.time())

    def _make_chunk(
        content: Optional[str] = None,
        role: Optional[str] = None,
        audio: Optional[Any] = None,
        finish_reason: Optional[str] = None,
    ) -> str:
        delta = {}
        if role:
            delta["role"] = role
        if content is not None:
            delta["content"] = content
        if audio is not None:
            delta["audio"] = audio

        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": model_id,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }],
        }
        return f"data: {json.dumps(chunk)}\n\n"

    # Initial role chunk
    yield _make_chunk(role="assistant", content="")
    await asyncio.sleep(0)

    # Wait for result with periodic heartbeats
    while True:
        try:
            msg = await asyncio.wait_for(rec.progress_queue.get(), timeout=2.0)
        except asyncio.TimeoutError:
            yield _make_chunk(content=".")
            await asyncio.sleep(0)
            continue

        msg_type = msg.get("type")

        if msg_type == "done":
            break

        elif msg_type == "error":
            yield _make_chunk(content=f"\n\nError: {msg.get('content', 'Unknown error')}")
            yield _make_chunk(finish_reason="error")
            yield "data: [DONE]\n\n"
            return

        elif msg_type == "result":
            result = msg.get("result", {})

            # Send LM content
            lm_content = _format_lm_content(result)
            yield _make_chunk(content=f"\n\n{lm_content}")
            await asyncio.sleep(0)

            # Send audio
            raw_audio_paths = result.get("raw_audio_paths", [])
            if raw_audio_paths:
                audio_path = raw_audio_paths[0]
                if audio_path and os.path.exists(audio_path):
                    b64_url = _audio_to_base64_url(audio_path, audio_format)
                    if b64_url:
                        audio_list = [{
                            "type": "audio_url",
                            "audio_url": {"url": b64_url},
                        }]
                        yield _make_chunk(audio=audio_list)
                        await asyncio.sleep(0)

            # Send audio_codes if available
            audio_codes = result.get("audio_codes")
            if audio_codes:
                yield _make_chunk(content=f"\n\n[audio_codes]{audio_codes}[/audio_codes]")
                await asyncio.sleep(0)

    # Finish
    yield _make_chunk(finish_reason="stop")
    yield "data: [DONE]\n\n"


# =============================================================================
# Router Factory
# =============================================================================

def create_openrouter_router(app_state_getter) -> APIRouter:
    """
    Create OpenRouter-compatible API router.

    Args:
        app_state_getter: Callable that returns the FastAPI app.state object

    Returns:
        APIRouter with OpenRouter-compatible endpoints
    """
    router = APIRouter(tags=["OpenRouter Compatible"])

    def _get_model_name_from_path(config_path: str) -> str:
        """Extract model name from config path."""
        if not config_path:
            return ""
        normalized = config_path.rstrip("/\\")
        return os.path.basename(normalized)

    @router.get("/v1/models", response_model=ModelsResponse)
    async def list_models():
        """List available models in OpenRouter format."""
        state = app_state_getter()
        models = []
        created_timestamp = int(time.time()) - 86400 * 30

        # Primary model
        if getattr(state, "_initialized", False):
            model_name = _get_model_name_from_path(state._config_path)
            if model_name:
                models.append(ModelInfo(
                    id=_get_model_id(model_name),
                    name=f"ACE-Step {model_name}",
                    created=created_timestamp,
                    input_modalities=["text", "audio"],
                    output_modalities=["audio", "text"],
                    context_length=4096,
                    max_output_length=300,
                    pricing=ModelPricing(
                        prompt="0", completion="0", request="0",
                    ),
                    description="AI music generation model",
                ))

        # Secondary model
        if getattr(state, "_initialized2", False) and getattr(state, "_config_path2", ""):
            model_name = _get_model_name_from_path(state._config_path2)
            if model_name:
                models.append(ModelInfo(
                    id=_get_model_id(model_name),
                    name=f"ACE-Step {model_name}",
                    created=created_timestamp,
                    input_modalities=["text", "audio"],
                    output_modalities=["audio", "text"],
                    context_length=4096,
                    max_output_length=300,
                    pricing=ModelPricing(),
                    description="AI music generation model",
                ))

        # Third model
        if getattr(state, "_initialized3", False) and getattr(state, "_config_path3", ""):
            model_name = _get_model_name_from_path(state._config_path3)
            if model_name:
                models.append(ModelInfo(
                    id=_get_model_id(model_name),
                    name=f"ACE-Step {model_name}",
                    created=created_timestamp,
                    input_modalities=["text", "audio"],
                    output_modalities=["audio", "text"],
                    context_length=4096,
                    max_output_length=300,
                    pricing=ModelPricing(),
                    description="AI music generation model",
                ))

        return ModelsResponse(data=models)

    @router.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        """
        OpenRouter-compatible chat completions endpoint for music generation.

        Submits the request to the shared asyncio.Queue and waits for completion.
        Supports both streaming (SSE) and non-streaming responses.
        """
        state = app_state_getter()

        # Check initialization
        if not getattr(state, "_initialized", False):
            raise HTTPException(
                status_code=503,
                detail=f"Model not initialized. init_error={getattr(state, '_init_error', None)}"
            )

        # Parse request
        try:
            body = await request.json()
            req = ChatCompletionRequest(**body)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid request format: {str(e)}")

        # Parse messages — audio is returned as deferred blobs,
        # no temp files are created yet.
        prompt, lyrics, audio_blobs, sample_query = (
            _parse_messages(req.messages)
        )

        # When lyrics or sample_mode is explicitly provided,
        # the message text role is already known.
        if req.lyrics or req.sample_mode:
            raw_text = prompt or sample_query or ""
            if req.lyrics:
                prompt = raw_text
                lyrics = req.lyrics
                sample_query = None
            else:
                prompt = ""
                lyrics = ""
                sample_query = raw_text

        has_audio = bool(audio_blobs)
        if (not prompt and not lyrics
                and not sample_query
                and not req.sample_mode
                and not has_audio):
            raise HTTPException(
                status_code=400,
                detail=(
                    "No valid prompt, lyrics, sample query, "
                    "or input audio found in request"
                ),
            )

        # Check queue capacity — still no temp files on disk.
        job_queue = state.job_queue
        if job_queue.full():
            raise HTTPException(
                status_code=429,
                detail="Server busy: queue is full",
            )

        # Get audio format
        audio_config = req.audio_config or AudioConfig()
        audio_format = (
            audio_config.format or DEFAULT_AUDIO_FORMAT
        )

        # Create job record first so we have a job_id for
        # cleanup registration.
        job_store = state.job_store
        rec = job_store.create()

        # Materialize audio blobs to temp files and register
        # them for cleanup in one step — no leak window.
        audio_paths = _materialize_audio_files(audio_blobs)
        if audio_paths:
            async with state.job_temp_files_lock:
                state.job_temp_files.setdefault(
                    rec.job_id, []
                ).extend(audio_paths)

        # Route audio paths based on task_type.
        reference_audio_path = None
        src_audio_path = None
        _SRC_AUDIO_TASK_TYPES = {
            "cover", "repaint", "lego",
            "extract", "complete",
        }
        if audio_paths:
            if req.task_type in _SRC_AUDIO_TASK_TYPES:
                src_audio_path = audio_paths[0]
                if len(audio_paths) > 1:
                    reference_audio_path = audio_paths[1]
            else:
                reference_audio_path = audio_paths[0]

        # Auto-convert src_audio to codes for cover mode
        resolved_audio_codes = req.audio_codes
        if (src_audio_path
                and not resolved_audio_codes
                and req.task_type == "cover"):
            handler = getattr(state, "handler", None)
            if handler and hasattr(
                handler, "convert_src_audio_to_codes"
            ):
                try:
                    codes_str = await asyncio.to_thread(
                        handler.convert_src_audio_to_codes,
                        src_audio_path,
                    )
                    if codes_str and not codes_str.startswith(
                        "❌"
                    ):
                        resolved_audio_codes = codes_str
                except Exception as exc:
                    logger.error(
                        "Auto-cover audio transcoding failed "
                        "for {}: {}",
                        src_audio_path,
                        exc,
                    )

        # Convert to GenerateMusicRequest
        gen_request = _to_generate_music_request(
            req, prompt, lyrics, sample_query,
            reference_audio_path, src_audio_path,
            audio_codes=resolved_audio_codes,
        )

        if req.stream:
            # Streaming: use progress_queue
            rec.progress_queue = asyncio.Queue()

            async with state.pending_lock:
                state.pending_ids.append(rec.job_id)

            await job_queue.put((rec.job_id, gen_request))

            return StreamingResponse(
                _openrouter_stream_generator(rec, req.model, audio_format),
                media_type="text/event-stream",
            )
        else:
            # Non-streaming: use done_event
            rec.done_event = asyncio.Event()

            async with state.pending_lock:
                state.pending_ids.append(rec.job_id)

            await job_queue.put((rec.job_id, gen_request))

            # Wait for completion with timeout
            try:
                await asyncio.wait_for(rec.done_event.wait(), timeout=GENERATION_TIMEOUT)
            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail="Generation timeout")

            return _build_openrouter_response(rec, req.model, audio_format)

    return router
