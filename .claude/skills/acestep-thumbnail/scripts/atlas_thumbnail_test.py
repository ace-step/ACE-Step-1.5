"""Tests for the optional Atlas Cloud thumbnail backend."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

MODULE_PATH = Path(__file__).with_name("atlas_thumbnail.py")
SPEC = importlib.util.spec_from_file_location("atlas_thumbnail", MODULE_PATH)
atlas = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(atlas)


class Response:
    """Small context-managed response fixture."""

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode()


class AtlasThumbnailTest(unittest.TestCase):
    """Cover successful routing, failure behavior, and output validation."""

    def test_submit_uses_one_non_retried_post(self) -> None:
        request_json = MagicMock(return_value={"data": {"id": "prediction-1"}})
        with patch.object(atlas, "_json_request", request_json):
            prediction_id = atlas.submit("secret", {"model": "example", "prompt": "cover"})
        self.assertEqual(prediction_id, "prediction-1")
        self.assertEqual(request_json.call_args.args[0].get_method(), "POST")
        self.assertEqual(request_json.call_args.kwargs, {})

    def test_poll_uses_bounded_prediction_get_retries(self) -> None:
        request_json = MagicMock(
            side_effect=[
                {"data": {"status": "processing", "outputs": []}},
                {"data": {"status": "completed", "outputs": ["https://image.test/a.png"]}},
            ]
        )
        with patch.object(atlas, "_json_request", request_json), patch.object(atlas.time, "sleep"):
            output = atlas.poll("secret", "prediction-1", timeout=10, interval=0)
        self.assertEqual(output, "https://image.test/a.png")
        self.assertTrue(
            all(
                call.kwargs["transient_retries"] == 3 and "deadline" in call.kwargs
                for call in request_json.call_args_list
            )
        )

    def test_request_never_runs_past_the_deadline(self) -> None:
        clock = [0.0]
        timeouts: list[float] = []
        sleeps: list[float] = []

        def fake_urlopen(_request: object, timeout: float) -> object:
            timeouts.append(timeout)
            clock[0] += timeout
            raise atlas.urllib.error.URLError("unreachable")

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock[0] += seconds

        request = atlas.urllib.request.Request("https://api.atlascloud.ai/x")
        with patch.object(atlas.urllib.request, "urlopen", fake_urlopen), patch.object(
            atlas.time, "sleep", fake_sleep
        ), patch.object(atlas.time, "monotonic", lambda: clock[0]):
            with self.assertRaises((atlas.urllib.error.URLError, TimeoutError)):
                atlas._json_request(request, transient_retries=3, deadline=2.0)
        self.assertLessEqual(clock[0], 2.0)
        self.assertTrue(all(value <= 2.0 for value in timeouts))
        self.assertLessEqual(len(timeouts), 4)

    def test_request_without_deadline_keeps_the_default_timeout(self) -> None:
        seen: list[float] = []

        def fake_urlopen(_request: object, timeout: float) -> Response:
            seen.append(timeout)
            return Response({"ok": True})

        request = atlas.urllib.request.Request("https://api.atlascloud.ai/x")
        with patch.object(atlas.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(atlas._json_request(request), {"ok": True})
        self.assertEqual(seen, [60.0])

    def test_download_writes_recognized_image_atomically(self) -> None:
        image = b"\x89PNG\r\n\x1a\n" + b"content"
        with tempfile.TemporaryDirectory() as directory, patch.object(
            atlas.urllib.request, "urlopen", return_value=Response(image)
        ):
            output = Path(directory) / "cover.png"
            actual = atlas.download("https://image.test/a.png", output)
            self.assertEqual(actual, output)
            self.assertEqual(output.read_bytes(), image)
            self.assertFalse(output.with_suffix(".png.tmp").exists())

    def test_download_corrects_a_mismatched_jpeg_suffix(self) -> None:
        image = b"\xff\xd8\xff" + b"content"
        with tempfile.TemporaryDirectory() as directory, patch.object(
            atlas.urllib.request, "urlopen", return_value=Response(image)
        ):
            requested = Path(directory) / "cover.png"
            actual = atlas.download("https://image.test/a.jpg", requested)
            self.assertEqual(actual, requested.with_suffix(".jpg"))
            self.assertEqual(actual.read_bytes(), image)
            self.assertFalse(requested.exists())


if __name__ == "__main__":
    unittest.main()
