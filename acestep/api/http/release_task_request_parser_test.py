"""Unit tests for release-task request parsing helper."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from acestep.api.http.release_task_request_parser import parse_release_task_request


class _FakeParser:
    """Minimal parser stub exposing typed accessors used by parser helper."""

    def __init__(self, values: dict) -> None:
        """Store deterministic key/value pairs for parser methods."""

        self._values = values

    def get(self, key: str):
        """Return raw value for ``key`` from parser payload."""

        return self._values.get(key)

    def str(self, key: str, default: str = "") -> str:
        """Return string value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        return default if value is None else str(value)

    def bool(self, key: str, default: bool = False) -> bool:
        """Return boolean value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def int(self, key: str, default=None):
        """Return integer value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        return default if value is None else int(value)

    def float(self, key: str, default=None):
        """Return float value for ``key`` with default fallback."""

        value = self._values.get(key, default)
        return default if value is None else float(value)


class _FakeRequest:
    """Minimal request stub supporting async json/form/body accessors."""

    def __init__(
        self,
        content_type: str,
        *,
        json_data=None,
        json_error: Exception | None = None,
        form_data=None,
        raw_body: bytes = b"",
    ) -> None:
        """Initialize request payloads for targeted parser-path tests."""

        self.headers = {"content-type": content_type}
        self._json_data = json_data
        self._json_error = json_error
        self._form_data = form_data
        self._raw_body = raw_body

    async def json(self):
        """Return deterministic JSON payload for this test request."""

        if self._json_error is not None:
            raise self._json_error
        return self._json_data

    async def form(self):
        """Return deterministic form payload for this test request."""

        return self._form_data

    async def body(self):
        """Return deterministic raw request bytes for this test request."""

        return self._raw_body


class ReleaseTaskRequestParserTests(unittest.TestCase):
    """Behavior tests for low-level parsing helper used by `/release_task`."""

    def test_json_payload_must_be_object(self):
        """Parser should reject JSON payloads that are not objects."""

        request = _FakeRequest("application/json", json_data=["not-object"])

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                parse_release_task_request(
                    request=request,
                    authorization=None,
                    verify_token_from_request=lambda *_: None,
                    request_parser_cls=_FakeParser,
                    request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
                    validate_audio_path=lambda path: path,
                    save_upload_to_temp=lambda *_args, **_kwargs: "",
                    upload_file_type=type("Upload", (), {}),
                    default_dit_instruction="instruction",
                    lm_default_temperature=0.85,
                    lm_default_cfg_scale=2.5,
                    lm_default_top_p=0.9,
                )
            )

        self.assertEqual(400, ctx.exception.status_code)
        self.assertIn("JSON payload must be an object", str(ctx.exception.detail))

    def test_missing_content_type_with_urlencoded_body_is_supported(self):
        """Parser should support key/value raw bodies when content-type is missing."""

        request = _FakeRequest(
            "",
            raw_body=b"ai_token=test-token&prompt=hello&reference_audio_path=ref.wav",
        )
        called = {"verified": False}

        def _verify_token(payload, _authorization):
            """Record auth verification and assert parsed body contains token."""

            called["verified"] = True
            self.assertEqual("test-token", payload.get("ai_token"))

        req, temp_files = asyncio.run(
            parse_release_task_request(
                request=request,
                authorization=None,
                verify_token_from_request=_verify_token,
                request_parser_cls=_FakeParser,
                request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
                validate_audio_path=lambda path: path,
                save_upload_to_temp=lambda *_args, **_kwargs: "",
                upload_file_type=type("Upload", (), {}),
                default_dit_instruction="instruction",
                lm_default_temperature=0.85,
                lm_default_cfg_scale=2.5,
                lm_default_top_p=0.9,
            )
        )

        self.assertTrue(called["verified"])
        self.assertEqual("hello", req.prompt)
        self.assertEqual("ref.wav", req.reference_audio_path)
        self.assertEqual([], temp_files)

    def test_application_json_malformed_payload_returns_400(self):
        """Parser should return HTTP 400 when JSON body parsing fails."""

        request = _FakeRequest(
            "application/json",
            json_error=json.JSONDecodeError("Expecting value", "x", 0),
        )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                parse_release_task_request(
                    request=request,
                    authorization=None,
                    verify_token_from_request=lambda *_: None,
                    request_parser_cls=_FakeParser,
                    request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
                    validate_audio_path=lambda path: path,
                    save_upload_to_temp=lambda *_args, **_kwargs: "",
                    upload_file_type=type("Upload", (), {}),
                    default_dit_instruction="instruction",
                    lm_default_temperature=0.85,
                    lm_default_cfg_scale=2.5,
                    lm_default_top_p=0.9,
                )
            )

        self.assertEqual(400, ctx.exception.status_code)
        self.assertEqual("Malformed JSON payload", ctx.exception.detail)

    def test_multipart_cleanup_removes_uploaded_temp_files_on_error(self):
        """Parser should remove uploaded temp files when multipart parsing fails."""

        class _Upload:
            """Minimal upload marker type for multipart form branch."""

            def read(self):
                """Expose read attribute for file-like filtering."""

                return b""

        class _FakeForm:
            """Minimal multipart form object with key/get/getlist semantics."""

            def __init__(self) -> None:
                """Store deterministic multipart values for this test."""

                self._values = {
                    "ai_token": "test-token",
                    "ref_audio": _Upload(),
                    "ctx_audio_path": "bad-path",
                }

            def keys(self):
                """Return iterable form keys."""

                return self._values.keys()

            def getlist(self, key: str):
                """Return list-shaped values for the requested key."""

                value = self._values.get(key)
                if value is None:
                    return []
                return value if isinstance(value, list) else [value]

            def get(self, key: str):
                """Return scalar value for the requested key."""

                return self._values.get(key)

        async def _save_upload_to_temp(_upload, *, prefix: str) -> str:
            """Return deterministic temp file path for uploaded payload."""

            return f"/tmp/{prefix}_123.wav"

        def _validate_audio_path(path: str | None) -> str | None:
            """Raise on the sentinel bad path to force cleanup flow."""

            if path == "bad-path":
                raise HTTPException(status_code=400, detail="bad path")
            return path

        request = _FakeRequest("multipart/form-data; boundary=x", form_data=_FakeForm())

        with mock.patch("acestep.api.http.release_task_request_parser.os.remove") as remove_mock:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    parse_release_task_request(
                        request=request,
                        authorization=None,
                        verify_token_from_request=lambda *_: None,
                        request_parser_cls=_FakeParser,
                        request_model_cls=lambda **kwargs: SimpleNamespace(**kwargs),
                        validate_audio_path=_validate_audio_path,
                        save_upload_to_temp=_save_upload_to_temp,
                        upload_file_type=_Upload,
                        default_dit_instruction="instruction",
                        lm_default_temperature=0.85,
                        lm_default_cfg_scale=2.5,
                        lm_default_top_p=0.9,
                    )
                )

        self.assertEqual(400, ctx.exception.status_code)
        remove_mock.assert_called_once_with("/tmp/ref_audio_123.wav")


if __name__ == "__main__":
    unittest.main()
