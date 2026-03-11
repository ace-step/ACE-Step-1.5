"""HTTP integration tests for the audio file route."""

import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from starlette.responses import Response

from acestep.api.http.audio_route import register_audio_route


async def _verify_api_key(authorization: str | None = Header(None)) -> None:
    """Validate fixed bearer token for audio route integration tests."""

    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


class AudioRouteHttpTests(unittest.TestCase):
    """Integration tests covering real HTTP requests for ``GET /v1/audio``."""

    def test_requires_authentication(self):
        """GET /v1/audio should return 401 without Authorization header."""

        app = FastAPI()
        app.state.temp_audio_dir = str(Path.cwd())
        register_audio_route(app=app, verify_api_key=_verify_api_key)
        client = TestClient(app)
        response = client.get("/v1/audio", params={"path": str(Path.cwd() / "x.mp3")})
        self.assertEqual(401, response.status_code)

    def test_serves_audio_file_with_authorization(self):
        """GET /v1/audio should return file bytes for authorized requests."""

        app = FastAPI()
        file_path = Path.cwd() / "ok.mp3"
        app.state.temp_audio_dir = str(Path.cwd())
        register_audio_route(app=app, verify_api_key=_verify_api_key)
        client = TestClient(app)
        with mock.patch("acestep.api.http.audio_route.Path.is_file", return_value=True), mock.patch(
            "fastapi.responses.FileResponse",
            return_value=Response(content=b"fake-audio", media_type="audio/mpeg"),
        ):
            response = client.get(
                "/v1/audio",
                params={"path": str(file_path)},
                headers={"Authorization": "Bearer test-token"},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(b"fake-audio", response.content)


if __name__ == "__main__":
    unittest.main()
