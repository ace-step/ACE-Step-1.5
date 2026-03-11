"""Audio-path validation and upload persistence helpers for release-task flow."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from starlette.datastructures import UploadFile as StarletteUploadFile


def validate_audio_path(path: Optional[str]) -> Optional[str]:
    """Validate user-supplied audio path and block unsafe filesystem traversal.

    Args:
        path: User-supplied path value from request payload.

    Returns:
        Normalized path string for accepted values, or ``None`` for empty input.

    Raises:
        HTTPException: If absolute paths outside temp or traversal markers are detected.
    """

    if not path:
        return None

    system_temp = os.path.realpath(tempfile.gettempdir())
    requested_path = os.path.realpath(path)
    try:
        is_in_temp = os.path.commonpath([system_temp, requested_path]) == system_temp
    except ValueError:
        is_in_temp = False

    if is_in_temp:
        return requested_path

    if os.path.isabs(path):
        raise HTTPException(status_code=400, detail="absolute audio file paths are not allowed")

    normalized = os.path.normpath(path)
    if ".." in normalized.split(os.sep):
        raise HTTPException(status_code=400, detail="path traversal in audio file paths is not allowed")
    return path


async def save_upload_to_temp(upload: StarletteUploadFile, *, prefix: str) -> str:
    """Persist uploaded audio file to a temporary location.

    Args:
        upload: Uploaded file wrapper from Starlette/FastAPI.
        prefix: Filename prefix used for the temporary file.

    Returns:
        Path to the stored temporary file.

    Raises:
        Exception: Re-raises write errors after cleaning up partial files.
    """

    suffix = Path(upload.filename or "").suffix
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=suffix)
    os.close(fd)
    try:
        with open(path, "wb") as file_obj:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                file_obj.write(chunk)
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
        raise
    finally:
        try:
            await upload.close()
        except Exception:
            pass
    return path
