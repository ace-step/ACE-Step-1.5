"""Unit tests for audio path validation and temp upload persistence helpers."""

import asyncio
import os
import unittest
from unittest import mock

from fastapi import HTTPException

from acestep.api.http.release_task_audio_paths import save_upload_to_temp, validate_audio_path


class _FakeUpload:
    """Minimal async upload stub for exercising temp-file persistence behavior."""

    def __init__(self, payload: bytes, filename: str = "clip.wav") -> None:
        """Store upload payload bytes and filename metadata."""

        self._payload = payload
        self._offset = 0
        self.filename = filename
        self.closed = False

    async def read(self, size: int) -> bytes:
        """Return next payload chunk, emulating Starlette UploadFile reads."""

        if self._offset >= len(self._payload):
            return b""
        end = min(self._offset + size, len(self._payload))
        chunk = self._payload[self._offset:end]
        self._offset = end
        return chunk

    async def close(self) -> None:
        """Mark fake upload as closed."""

        self.closed = True


class ReleaseTaskAudioPathsTests(unittest.TestCase):
    """Behavior tests for path-validation and upload-persistence helpers."""

    def test_validate_audio_path_rejects_absolute_non_temp_path(self):
        """Validator should reject absolute paths outside the system temp directory."""

        with self.assertRaises(HTTPException) as ctx:
            validate_audio_path(os.path.abspath(os.path.join(os.getcwd(), "outside.wav")))
        self.assertEqual(400, ctx.exception.status_code)
        self.assertIn("absolute audio file paths are not allowed", str(ctx.exception.detail))

    def test_validate_audio_path_rejects_traversal_sequences(self):
        """Validator should reject relative paths containing traversal markers."""

        with self.assertRaises(HTTPException) as ctx:
            validate_audio_path("../unsafe.wav")
        self.assertEqual(400, ctx.exception.status_code)
        self.assertIn("path traversal", str(ctx.exception.detail))

    def test_save_upload_to_temp_writes_file_and_closes_upload(self):
        """Uploader helper should stream bytes through mocked file writes and close upload."""

        upload = _FakeUpload(payload=b"abc123", filename="sample.wav")
        with mock.patch(
            "acestep.api.http.release_task_audio_paths.tempfile.mkstemp",
            return_value=(123, "mock/path/sample.wav"),
        ), mock.patch("acestep.api.http.release_task_audio_paths.os.close") as close_mock, mock.patch(
            "acestep.api.http.release_task_audio_paths.open",
            new_callable=mock.mock_open,
        ) as open_mock:
            saved_path = asyncio.run(save_upload_to_temp(upload, prefix="ref_audio"))

        self.assertEqual("mock/path/sample.wav", saved_path)
        close_mock.assert_called_once_with(123)
        open_mock.assert_called_once_with("mock/path/sample.wav", "wb")
        open_mock().write.assert_called_once_with(b"abc123")
        self.assertTrue(upload.closed)


if __name__ == "__main__":
    unittest.main()
