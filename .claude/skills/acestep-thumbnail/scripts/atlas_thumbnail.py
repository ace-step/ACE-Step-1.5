#!/usr/bin/env python3
"""Generate an ACE-Step thumbnail with the Atlas Cloud image API."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_ROOT = "https://api.atlascloud.ai"
CATALOG_URL = f"{API_ROOT}/api/v1/models"
DEFAULT_MODEL = "google/nano-banana-pro/text-to-image-developer"
USER_AGENT = "acestep-thumbnail/1.0"


def _json_request(
    request: urllib.request.Request, *, transient_retries: int = 0
) -> dict[str, Any]:
    """Send JSON, retrying only transient GET failures when requested."""
    for attempt in range(transient_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if attempt >= transient_retries or exc.code not in {429, 500, 502, 503, 504}:
                raise
        except urllib.error.URLError:
            if attempt >= transient_retries:
                raise
        time.sleep(2**attempt)
    raise RuntimeError("request retry loop exhausted")


def validate_model(model: str) -> None:
    """Confirm the configured model is currently enabled in the Atlas catalog."""
    data = _json_request(urllib.request.Request(CATALOG_URL, headers={"User-Agent": USER_AGENT}))
    models = data.get("data", data)
    if isinstance(models, dict):
        models = models.get("models") or models.get("items") or []
    match = next((item for item in models if item.get("model") == model), None)
    if not match or match.get("type") != "Image" or match.get("display_console") is False:
        raise RuntimeError(f"Atlas image model is not currently available: {model}")


def submit(key: str, payload: dict[str, Any]) -> str:
    """Submit exactly one billable image generation request and return its id."""
    request = urllib.request.Request(
        f"{API_ROOT}/api/v1/model/generateImage",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    data = _json_request(request)
    body = data.get("data", data)
    prediction_id = body.get("id") if isinstance(body, dict) else None
    if not prediction_id:
        raise RuntimeError("Atlas generation response did not include a prediction id")
    return str(prediction_id)


def poll(key: str, prediction_id: str, timeout: int, interval: float) -> str:
    """Poll a prediction until completion and return the first output URL."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        request = urllib.request.Request(
            f"{API_ROOT}/api/v1/model/prediction/{prediction_id}",
            headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT},
        )
        data = _json_request(request, transient_retries=3)
        body = data.get("data", data)
        status = str(body.get("status", "")).lower()
        outputs = body.get("outputs") or []
        if status in {"completed", "succeeded"} and outputs:
            return str(outputs[0])
        if status in {"failed", "canceled", "cancelled"}:
            raise RuntimeError(f"Atlas prediction ended with status: {status}")
        time.sleep(interval)
    raise TimeoutError(f"Atlas prediction timed out after {timeout} seconds")


def download(url: str, output: Path) -> Path:
    """Download one generated image and atomically place it with the correct suffix."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read()
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        suffix = ".png"
    elif content.startswith(b"\xff\xd8\xff"):
        suffix = ".jpg"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        suffix = ".webp"
    else:
        raise RuntimeError("Atlas output is not a recognized PNG, JPEG, or WebP image")
    if output.suffix.lower() not in {suffix, ".jpeg" if suffix == ".jpg" else suffix}:
        output = output.with_suffix(suffix)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(output)
    return output


def main() -> None:
    """Parse CLI arguments and run the Atlas thumbnail workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--resolution", choices=("1k", "2k", "4k"), default="1k")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--poll-interval", type=float, default=2)
    args = parser.parse_args()
    key = os.environ.get("ATLASCLOUD_API_KEY") or os.environ.get("ATLAS_CLOUD_API_KEY")
    if not key:
        parser.error("set ATLASCLOUD_API_KEY before using --provider atlas")
    validate_model(args.model)
    prediction_id = submit(
        key,
        {
            "model": args.model,
            "prompt": args.prompt,
            "aspect_ratio": args.aspect_ratio,
            "resolution": args.resolution,
        },
    )
    output = download(poll(key, prediction_id, args.timeout, args.poll_interval), args.output)
    print(output.resolve())


if __name__ == "__main__":
    main()
