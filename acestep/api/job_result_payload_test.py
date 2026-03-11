"""Unit tests for generation success response payload helper."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from acestep.api.job_result_payload import (
    build_generation_success_response,
    normalize_metas,
)


class JobResultPayloadTests(unittest.TestCase):
    """Behavior tests for generation payload normalization and assembly."""

    def test_normalize_metas_maps_aliases_and_applies_defaults(self) -> None:
        """Metadata normalizer should preserve aliases and fill missing keys."""

        out = normalize_metas(
            {
                "key_scale": "C major",
                "time_signature": "4/4",
                "genres": "",
            }
        )
        self.assertEqual("C major", out["keyscale"])
        self.assertEqual("4/4", out["timesignature"])
        self.assertEqual("N/A", out["genres"])
        self.assertEqual("N/A", out["bpm"])
        self.assertEqual("N/A", out["duration"])

    def test_build_generation_success_response_preserves_response_contract(self) -> None:
        """Success payload helper should assemble fields with legacy shape and overrides."""

        result = SimpleNamespace(
            audios=[
                {"path": "a.wav", "params": {"seed": 11}},
                {"path": "b.wav", "params": {"seed": 22}},
            ],
            extra_outputs={"lm_metadata": {"genres": "rock"}, "time_costs": {"total": 1.2}},
            status_message="ok",
        )
        params = SimpleNamespace(
            caption="final caption",
            lyrics="final lyrics",
            cot_bpm=120,
            cot_duration=8.0,
            cot_keyscale="G major",
            cot_timesignature="3/4",
        )
        build_generation_info = MagicMock(return_value="gen-info")

        payload = build_generation_success_response(
            result=result,
            params=params,
            bpm=None,
            audio_duration=None,
            key_scale=None,
            time_signature=None,
            original_prompt="orig prompt",
            original_lyrics="orig lyrics",
            inference_steps=8,
            path_to_audio_url=lambda path: f"/v1/audio?path={path}",
            build_generation_info=build_generation_info,
            lm_model_name="lm",
            dit_model_name="dit",
        )

        self.assertEqual("/v1/audio?path=a.wav", payload["first_audio_path"])
        self.assertEqual("/v1/audio?path=b.wav", payload["second_audio_path"])
        self.assertEqual("11,22", payload["seed_value"])
        self.assertEqual("orig prompt", payload["metas"]["prompt"])
        self.assertEqual("orig lyrics", payload["metas"]["lyrics"])
        self.assertEqual(120, payload["bpm"])
        self.assertEqual(8.0, payload["duration"])
        self.assertEqual("G major", payload["keyscale"])
        self.assertEqual("3/4", payload["timesignature"])
        self.assertEqual("lm", payload["lm_model"])
        self.assertEqual("dit", payload["dit_model"])
        build_generation_info.assert_called_once()


if __name__ == "__main__":
    unittest.main()
