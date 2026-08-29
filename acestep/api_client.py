"""CLI-friendly client helpers for the legacy ACE-Step async music API."""

from __future__ import annotations

import argparse
import json
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests


SUPPORTED_TASK_TYPES = ("text2music", "cover", "cover-nofsq", "repaint")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the legacy async API client."""

    parser = argparse.ArgumentParser(description="Call the ACE-Step legacy async music API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="API base URL.")
    parser.add_argument("--api-key", default=None, help="Optional API key for Authorization header.")
    parser.add_argument("--task-type", default="text2music", choices=SUPPORTED_TASK_TYPES)
    parser.add_argument("--prompt", default="", help="Music prompt/caption.")
    parser.add_argument("--lyrics", default="", help="Lyrics text.")
    parser.add_argument("--src-audio", default=None, help="Source audio file for cover/repaint modes.")
    parser.add_argument("--reference-audio", default=None, help="Optional reference audio file.")
    parser.add_argument("--audio-duration", type=float, default=None, help="Target duration in seconds.")
    parser.add_argument("--batch-size", type=int, default=1, help="Number of samples to generate.")
    parser.add_argument("--inference-steps", type=int, default=8, help="Diffusion inference steps.")
    parser.add_argument("--guidance-scale", type=float, default=7.0, help="CFG scale.")
    parser.add_argument("--thinking", action="store_true", help="Enable 5Hz LM thinking mode.")
    parser.add_argument("--model", default=None, help="Optional DiT model name.")
    parser.add_argument("--audio-format", default="mp3", help="Output format: mp3/flac/wav/opus/aac/wav32.")
    parser.add_argument("--seed", default=None, help="Optional seed or comma-separated seeds.")
    parser.add_argument("--vocal-language", default="en", help="Lyrics language code.")
    parser.add_argument("--repainting-start", type=float, default=0.0, help="Repaint region start in seconds.")
    parser.add_argument("--repainting-end", type=float, default=None, help="Repaint region end in seconds.")
    parser.add_argument(
        "--repaint-mode",
        default="balanced",
        choices=("conservative", "balanced", "aggressive"),
        help="Repaint mode. Matches the Gradio default.",
    )
    parser.add_argument(
        "--repaint-strength",
        type=float,
        default=0.5,
        help="Repaint strength. Matches the Gradio default.",
    )
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--timeout", type=float, default=900.0, help="Polling timeout in seconds.")
    parser.add_argument("--output-dir", default="api_outputs", help="Directory for downloaded audio.")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Print returned audio URLs without downloading files.",
    )
    return parser


def build_headers(api_key: Optional[str]) -> dict[str, str]:
    """Build request headers with optional bearer authentication."""

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def validate_args(args: argparse.Namespace) -> None:
    """Validate task-specific CLI arguments before any network call."""

    if args.batch_size < 1:
        raise ValueError("--batch-size must be >= 1")
    if args.task_type in {"cover", "cover-nofsq", "repaint"} and not args.src_audio:
        raise ValueError(f"--src-audio is required for task type '{args.task_type}'")
    if args.task_type == "repaint" and args.repainting_end is None:
        raise ValueError("--repainting-end is required for repaint mode")


def build_release_task_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Convert CLI arguments into a release-task payload."""

    payload: dict[str, Any] = {
        "task_type": args.task_type,
        "prompt": args.prompt,
        "lyrics": args.lyrics,
        "thinking": args.thinking,
        "vocal_language": args.vocal_language,
        "batch_size": args.batch_size,
        "inference_steps": args.inference_steps,
        "guidance_scale": args.guidance_scale,
        "audio_format": args.audio_format,
        "repainting_start": args.repainting_start,
    }
    if args.task_type == "repaint":
        payload["repaint_mode"] = args.repaint_mode
        payload["repaint_strength"] = args.repaint_strength
    if args.audio_duration is not None:
        payload["audio_duration"] = args.audio_duration
    if args.repainting_end is not None:
        payload["repainting_end"] = args.repainting_end
    if args.model:
        payload["model"] = args.model
    if args.seed is not None:
        payload["seed"] = args.seed
        payload["use_random_seed"] = False
    return payload


def submit_generation_task(
    session: requests.Session,
    base_url: str,
    api_key: Optional[str],
    payload: dict[str, Any],
    src_audio: Optional[str] = None,
    reference_audio: Optional[str] = None,
) -> str:
    """Submit a generation task and return the queued task ID."""

    with ExitStack() as stack:
        files = {}
        data = {key: str(value) for key, value in payload.items()}
        if src_audio:
            files["src_audio"] = stack.enter_context(open(src_audio, "rb"))
        if reference_audio:
            files["reference_audio"] = stack.enter_context(open(reference_audio, "rb"))
        response = session.post(
            f"{base_url.rstrip('/')}/release_task",
            headers=build_headers(api_key),
            data=data,
            files=files or None,
            timeout=120,
        )
    response.raise_for_status()
    body = response.json()
    task_id = (((body or {}).get("data")) or {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"release_task did not return a task_id: {body}")
    return str(task_id)


def parse_query_result_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse the legacy stringified ``result`` field into a list payload."""

    raw_result = item.get("result", "[]")
    if isinstance(raw_result, list):
        return raw_result
    if not isinstance(raw_result, str):
        return []
    try:
        parsed = json.loads(raw_result)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def poll_task_result(
    session: requests.Session,
    base_url: str,
    api_key: Optional[str],
    task_id: str,
    poll_interval: float,
    timeout: float,
) -> list[dict[str, Any]]:
    """Poll ``/query_result`` until the task succeeds or fails."""

    deadline = time.time() + timeout
    last_progress = None
    while time.time() < deadline:
        response = session.post(
            f"{base_url.rstrip('/')}/query_result",
            headers={"Content-Type": "application/json", **build_headers(api_key)},
            json={"task_id_list": [task_id]},
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        items = (body or {}).get("data") or []
        if not items:
            time.sleep(poll_interval)
            continue
        task = items[0]
        status = int(task.get("status", 0))
        progress_text = task.get("progress_text")
        if progress_text and progress_text != last_progress and status == 0:
            print(progress_text)
            last_progress = progress_text
        if status == 1:
            return parse_query_result_item(task)
        if status == 2:
            raise RuntimeError(f"task failed: {task}")
        time.sleep(poll_interval)
    raise TimeoutError(f"task {task_id} did not finish within {timeout} seconds")


def resolve_audio_url(base_url: str, file_url: str) -> str:
    """Resolve relative audio URLs returned by the API against the base URL."""

    return urljoin(f"{base_url.rstrip('/')}/", file_url)


def infer_output_suffix(audio_url: str) -> str:
    """Infer a file suffix from the ``/v1/audio?path=...`` URL query."""

    parsed = urlparse(audio_url)
    query_path = parse_qs(parsed.query).get("path", [""])[0]
    suffix = Path(query_path).suffix
    return suffix or ".bin"


def download_audio_files(
    session: requests.Session,
    base_url: str,
    audio_items: list[dict[str, Any]],
    output_dir: str,
    task_id: str,
) -> list[Path]:
    """Download generated audio files to the requested output directory."""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for index, item in enumerate(audio_items):
        file_url = str(item.get("file", "")).strip()
        if not file_url:
            continue
        response = session.get(resolve_audio_url(base_url, file_url), timeout=300)
        response.raise_for_status()
        output_path = out_dir / f"{task_id}_{index}{infer_output_suffix(file_url)}"
        output_path.write_bytes(response.content)
        saved_paths.append(output_path)
    return saved_paths


def main(argv: Optional[list[str]] = None) -> int:
    """Run the legacy async music API client from the command line."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
        payload = build_release_task_payload(args)
        with requests.Session() as session:
            task_id = submit_generation_task(
                session=session,
                base_url=args.base_url,
                api_key=args.api_key,
                payload=payload,
                src_audio=args.src_audio,
                reference_audio=args.reference_audio,
            )
            print(f"task_id: {task_id}")
            results = poll_task_result(
                session=session,
                base_url=args.base_url,
                api_key=args.api_key,
                task_id=task_id,
                poll_interval=args.poll_interval,
                timeout=args.timeout,
            )
            print(f"returned_audio_count: {len(results)}")
            if args.no_download:
                for index, item in enumerate(results):
                    print(f"audio[{index}]: {item.get('file', '')}")
            else:
                saved = download_audio_files(
                    session=session,
                    base_url=args.base_url,
                    audio_items=results,
                    output_dir=args.output_dir,
                    task_id=task_id,
                )
                for path in saved:
                    print(f"saved: {path}")
        return 0
    except Exception as exc:
        print(f"error: {exc}")
        return 1
