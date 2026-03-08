"""HTTP route for Whisper-based audio transcription and LRC generation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel


class TranscribeRequest(BaseModel):
    """Request body for POST /v1/transcribe."""

    audio_path: str
    language: str | None = None


def register_transcribe_route(
    app: FastAPI,
    verify_api_key: Callable[..., Any],
    wrap_response: Callable[..., Dict[str, Any]],
) -> None:
    """Register the ``POST /v1/transcribe`` route.

    Transcribes audio using OpenAI Whisper API and returns:
    - Word-level timestamps
    - LRC-formatted text
    - Plain lyrics text
    """

    @app.post("/v1/transcribe")
    async def transcribe_audio(
        body: TranscribeRequest,
        request: Request,
        _: None = Depends(verify_api_key),
    ):
        """Transcribe audio to lyrics with timestamps using Whisper API."""

        # Validate API key
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="OPENAI_API_KEY environment variable is not set. "
                "Set it in your environment or the app settings to use Whisper transcription.",
            )

        # Validate audio file exists
        audio_path = body.audio_path
        if not Path(audio_path).is_file():
            raise HTTPException(
                status_code=404,
                detail=f"Audio file not found: {audio_path}",
            )

        try:
            # Import transcription utilities
            from scripts.lora_data_prepare.whisper_transcription import (
                transcribe_whisper,
                words_to_lyrics,
                words_to_lrc,
            )

            # Call Whisper API
            words = transcribe_whisper(
                audio_path=audio_path,
                api_key=api_key,
                language=body.language,
            )

            if not words:
                raise HTTPException(
                    status_code=500,
                    detail="Whisper API returned no word-level timestamps.",
                )

            # Generate LRC and plain lyrics
            lrc_text = words_to_lrc(words)
            lyrics_text = words_to_lyrics(words)

            return wrap_response(
                data={
                    "words": words,
                    "lrc_text": lrc_text,
                    "lyrics_text": lyrics_text,
                }
            )

        except HTTPException:
            raise
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Transcription failed: {e}",
            )
