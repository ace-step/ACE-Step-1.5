"""Tests for the legacy ACE-Step async API client helpers."""

from __future__ import annotations

import argparse
import unittest

from acestep.api_client import (
    build_release_task_payload,
    infer_output_suffix,
    parse_query_result_item,
    resolve_audio_url,
    validate_args,
)


class ApiClientValidationTests(unittest.TestCase):
    """Validate CLI argument rules for task-specific API modes."""

    def test_cover_requires_src_audio(self) -> None:
        """Cover-family tasks should require a source audio file."""

        args = argparse.Namespace(
            task_type="cover",
            src_audio=None,
            batch_size=1,
            repainting_end=None,
        )
        with self.assertRaisesRegex(ValueError, "--src-audio is required"):
            validate_args(args)

    def test_repaint_requires_end_time(self) -> None:
        """Repaint mode should require an explicit repaint end boundary."""

        args = argparse.Namespace(
            task_type="repaint",
            src_audio="input.wav",
            batch_size=1,
            repainting_end=None,
        )
        with self.assertRaisesRegex(ValueError, "--repainting-end is required"):
            validate_args(args)


class ApiClientPayloadTests(unittest.TestCase):
    """Exercise request payload building for the release-task API."""

    def test_build_release_task_payload_disables_random_seed_when_seed_given(self) -> None:
        """Explicit seeds should set ``use_random_seed`` false in the payload."""

        args = argparse.Namespace(
            task_type="text2music",
            prompt="hello",
            lyrics="",
            thinking=False,
            vocal_language="en",
            batch_size=2,
            inference_steps=8,
            guidance_scale=7.0,
            audio_format="mp3",
            repainting_start=0.0,
            repainting_end=None,
            repaint_mode="balanced",
            repaint_strength=0.5,
            audio_duration=30.0,
            model="acestep-v15-xl-turbo",
            seed="42,43",
        )
        payload = build_release_task_payload(args)
        self.assertEqual("42,43", payload["seed"])
        self.assertFalse(payload["use_random_seed"])
        self.assertEqual(2, payload["batch_size"])

    def test_build_release_task_payload_includes_gradio_repaint_defaults(self) -> None:
        """Repaint requests should send the same default mode/strength as Gradio."""

        args = argparse.Namespace(
            task_type="repaint",
            prompt="repair the chorus",
            lyrics="[Instrumental]",
            thinking=False,
            vocal_language="en",
            batch_size=1,
            inference_steps=8,
            guidance_scale=7.0,
            audio_format="mp3",
            repainting_start=0.0,
            repainting_end=12.0,
            repaint_mode="balanced",
            repaint_strength=0.5,
            audio_duration=None,
            model=None,
            seed=None,
        )
        payload = build_release_task_payload(args)
        self.assertEqual("balanced", payload["repaint_mode"])
        self.assertEqual(0.5, payload["repaint_strength"])


class ApiClientResultParsingTests(unittest.TestCase):
    """Verify legacy query-result parsing and audio URL helpers."""

    def test_parse_query_result_item_handles_batch_audio_list(self) -> None:
        """Batch-sized generations should parse into one entry per returned audio."""

        item = {
            "result": (
                '[{"file":"/v1/audio?path=%2Ftmp%2Fa.mp3","status":1},'
                '{"file":"/v1/audio?path=%2Ftmp%2Fb.mp3","status":1}]'
            )
        }
        result = parse_query_result_item(item)
        self.assertEqual(2, len(result))
        self.assertEqual("/v1/audio?path=%2Ftmp%2Fb.mp3", result[1]["file"])

    def test_audio_url_helpers_preserve_relative_path_and_suffix(self) -> None:
        """Relative ``/v1/audio`` URLs should resolve and keep output suffixes."""

        file_url = "/v1/audio?path=%2Ftmp%2Fapi_audio%2Fdemo.flac"
        self.assertEqual("http://127.0.0.1:8001/v1/audio?path=%2Ftmp%2Fapi_audio%2Fdemo.flac", resolve_audio_url("http://127.0.0.1:8001", file_url))
        self.assertEqual(".flac", infer_output_suffix(file_url))


if __name__ == "__main__":
    unittest.main()
