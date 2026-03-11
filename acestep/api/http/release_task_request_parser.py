"""Request parsing helpers for the ``/release_task`` HTTP route."""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import HTTPException, Request

from acestep.api.http.release_task_request_builder import build_generate_music_request


def _extract_non_file_form_values(form: Any) -> Dict[str, Any]:
    """Extract scalar/list form values while filtering file objects.

    Args:
        form: Starlette multipart form object.

    Returns:
        Dictionary of non-file form values preserving single vs multi-value shape.
    """

    values: Dict[str, Any] = {}
    for key in form.keys():
        non_files = [value for value in form.getlist(key) if not hasattr(value, "read")]
        if len(non_files) == 1:
            values[key] = non_files[0]
        elif len(non_files) > 1:
            values[key] = non_files
    return values


async def parse_release_task_request(
    request: Request,
    authorization: Optional[str],
    verify_token_from_request: Callable[[dict, Optional[str]], Optional[str]],
    request_parser_cls: Any,
    request_model_cls: Any,
    validate_audio_path: Callable[[Optional[str]], Optional[str]],
    save_upload_to_temp: Callable[..., Any],
    upload_file_type: type,
    default_dit_instruction: str,
    lm_default_temperature: float,
    lm_default_cfg_scale: float,
    lm_default_top_p: float,
) -> Tuple[Any, list[str]]:
    """Parse ``/release_task`` request body into request model and temp-file list.

    Args:
        request: FastAPI request carrying body/form data.
        authorization: Optional Authorization header value.
        verify_token_from_request: Legacy token validator.
        request_parser_cls: Parser class for request dictionaries.
        request_model_cls: Request model class (for example ``GenerateMusicRequest``).
        validate_audio_path: Validator for manual audio-path fields.
        save_upload_to_temp: Helper for persisting uploaded files to temp paths.
        upload_file_type: Upload class used for multipart file detection.
        default_dit_instruction: Default DiT instruction string.
        lm_default_temperature: Default LM temperature value.
        lm_default_cfg_scale: Default LM CFG scale value.
        lm_default_top_p: Default LM top-p value.

    Returns:
        Tuple of ``(request_model, temp_files)``.

    Raises:
        HTTPException: When content type is unsupported or body parsing fails.
    """

    content_type = (request.headers.get("content-type") or "").lower()
    temp_files: list[str] = []

    def _build(parser: Any, **overrides: Any) -> Any:
        """Build request model from parsed values and explicit overrides."""

        return build_generate_music_request(
            parser=parser,
            request_model_cls=request_model_cls,
            default_dit_instruction=default_dit_instruction,
            lm_default_temperature=lm_default_temperature,
            lm_default_cfg_scale=lm_default_cfg_scale,
            lm_default_top_p=lm_default_top_p,
            **overrides,
        )

    if content_type.startswith("application/json") or content_type.endswith("+json"):
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Malformed JSON payload")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON payload must be an object")
        verify_token_from_request(body, authorization)
        parser = request_parser_cls(body)
        req = _build(
            parser,
            reference_audio_path=validate_audio_path(parser.str("reference_audio_path") or None),
            src_audio_path=validate_audio_path(parser.str("src_audio_path") or None),
        )
        return req, temp_files

    if content_type.startswith("multipart/form-data"):
        try:
            form = await request.form()
            form_values = _extract_non_file_form_values(form)
            verify_token_from_request(form_values, authorization)

            ref_upload = form.get("ref_audio") or form.get("reference_audio")
            ctx_upload = form.get("ctx_audio") or form.get("src_audio")
            if isinstance(ref_upload, upload_file_type):
                reference_audio_path = await save_upload_to_temp(ref_upload, prefix="ref_audio")
                temp_files.append(reference_audio_path)
            else:
                reference_audio_path = validate_audio_path(
                    str(form.get("ref_audio_path") or form.get("reference_audio_path") or "").strip() or None
                )

            if isinstance(ctx_upload, upload_file_type):
                src_audio_path = await save_upload_to_temp(ctx_upload, prefix="ctx_audio")
                temp_files.append(src_audio_path)
            else:
                src_audio_path = validate_audio_path(
                    str(form.get("ctx_audio_path") or form.get("src_audio_path") or "").strip() or None
                )

            req = _build(
                request_parser_cls(dict(form_values)),
                reference_audio_path=reference_audio_path,
                src_audio_path=src_audio_path,
            )
            return req, temp_files
        except Exception:
            for temp_file in temp_files:
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            raise

    if content_type.startswith("application/x-www-form-urlencoded"):
        form = await request.form()
        form_dict = dict(form)
        verify_token_from_request(form_dict, authorization)
        reference_audio_path = validate_audio_path(
            str(form.get("ref_audio_path") or form.get("reference_audio_path") or "").strip() or None
        )
        src_audio_path = validate_audio_path(
            str(form.get("ctx_audio_path") or form.get("src_audio_path") or "").strip() or None
        )
        req = _build(
            request_parser_cls(form_dict),
            reference_audio_path=reference_audio_path,
            src_audio_path=src_audio_path,
        )
        return req, temp_files

    raw = await request.body()
    raw_stripped = raw.lstrip()
    if raw_stripped.startswith(b"{") or raw_stripped.startswith(b"["):
        try:
            body = json.loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="JSON payload must be an object")
            verify_token_from_request(body, authorization)
            parser = request_parser_cls(body)
            req = _build(
                parser,
                reference_audio_path=validate_audio_path(parser.str("reference_audio_path") or None),
                src_audio_path=validate_audio_path(parser.str("src_audio_path") or None),
            )
            return req, temp_files
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON body (hint: set 'Content-Type: application/json')",
            )

    if raw_stripped and b"=" in raw:
        parsed = urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True)
        flat = {key: (value[0] if isinstance(value, list) and value else value) for key, value in parsed.items()}
        verify_token_from_request(flat, authorization)
        reference_audio_path = validate_audio_path(
            str(flat.get("ref_audio_path") or flat.get("reference_audio_path") or "").strip() or None
        )
        src_audio_path = validate_audio_path(
            str(flat.get("ctx_audio_path") or flat.get("src_audio_path") or "").strip() or None
        )
        req = _build(
            request_parser_cls(flat),
            reference_audio_path=reference_audio_path,
            src_audio_path=src_audio_path,
        )
        return req, temp_files

    raise HTTPException(
        status_code=415,
        detail=(
            f"Unsupported Content-Type: {content_type or '(missing)'}; "
            "use application/json, application/x-www-form-urlencoded, or multipart/form-data"
        ),
    )
