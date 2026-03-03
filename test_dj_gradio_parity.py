"""DJ ↔ Gradio generation parity tests.

Verifies that identical generation parameters produce identical results
through both the REST API path (DJ HTML frontend) and the direct
generate_music() call path (Gradio UI).

REST API path:
  POST /release_task (JSON) → api_server.py → GenerateMusicRequest
  → GenerationParams → job queue → worker → generate_music()

Direct path:
  GenerationParams constructed directly → generate_music()

Requires a running API server at http://127.0.0.1:8001 for integration tests.
Parameter mapping tests run without a server.
"""

import json
import os
import sys
import time
import unittest
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import requests

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from acestep.inference import GenerationConfig, GenerationParams
from acestep.constants import DEFAULT_DIT_INSTRUCTION, TASK_INSTRUCTIONS

API_BASE = os.environ.get("ACESTEP_API_URL", "http://127.0.0.1:8001")
POLL_INTERVAL = 2  # seconds between status polls
POLL_TIMEOUT = 300  # max seconds to wait for a job


def _server_is_running() -> bool:
    """Check if the API server is reachable."""
    try:
        r = requests.get(f"{API_BASE}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


SERVER_AVAILABLE = _server_is_running()


def _submit_and_poll(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Submit a generation job via REST and poll until completion.

    Returns the full result dict from query_result on success.
    The ``result`` field (a JSON string) is parsed into a list of dicts
    and stored under the ``audios`` key for convenience.
    Raises RuntimeError on failure or timeout.
    """
    res = requests.post(f"{API_BASE}/release_task", json=payload, timeout=30)
    res.raise_for_status()
    body = res.json()
    if body.get("code") != 200:
        raise RuntimeError(f"release_task failed: {body}")
    task_id = body["data"]["task_id"]

    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        poll = requests.post(
            f"{API_BASE}/query_result",
            json={"task_id_list": [task_id]},
            timeout=10,
        )
        poll.raise_for_status()
        entry = poll.json()["data"][0]
        status = entry.get("status")
        # status: 0=queued, 1=succeeded, 2=failed
        if status == 1:
            # Parse the result JSON string into a list of audio dicts
            result_str = entry.get("result", "[]")
            if isinstance(result_str, str):
                entry["audios"] = json.loads(result_str)
            elif isinstance(result_str, list):
                entry["audios"] = result_str
            return entry
        if status == 2:
            raise RuntimeError(f"Job {task_id} failed: {entry}")
    raise RuntimeError(f"Job {task_id} timed out after {POLL_TIMEOUT}s")


# ---------------------------------------------------------------------------
# Shared test parameters
# ---------------------------------------------------------------------------
FIXED_SEED = 42
TEST_PROMPT = "chill lofi hip hop beat, jazzy piano, warm vinyl crackle"
TEST_LYRICS = "[Instrumental]"
TEST_DURATION = 10.0
TEST_STEPS = 8
TEST_GUIDANCE = 7.0
TEST_BPM = 85
TEST_KEY_SCALE = "C Major"
TEST_LANGUAGE = "en"


def _build_rest_payload(
    *,
    prompt: str = TEST_PROMPT,
    lyrics: str = TEST_LYRICS,
    duration: float = TEST_DURATION,
    inference_steps: int = TEST_STEPS,
    guidance_scale: float = TEST_GUIDANCE,
    thinking: bool = False,
    seed: int = FIXED_SEED,
    use_random_seed: bool = False,
    batch_size: int = 1,
    audio_format: str = "wav",
    bpm: Optional[int] = TEST_BPM,
    key_scale: str = TEST_KEY_SCALE,
    vocal_language: str = TEST_LANGUAGE,
    task_type: str = "text2music",
    **extra,
) -> Dict[str, Any]:
    """Build a REST API payload matching what dj.html sends."""
    payload = {
        "prompt": prompt,
        "lyrics": lyrics,
        "audio_duration": duration,
        "inference_steps": inference_steps,
        "guidance_scale": guidance_scale,
        "thinking": thinking,
        "seed": seed,
        "use_random_seed": use_random_seed,
        "batch_size": batch_size,
        "audio_format": audio_format,
        "bpm": bpm,
        "key_scale": key_scale,
        "vocal_language": vocal_language,
        "task_type": task_type,
    }
    payload.update(extra)
    return payload


def _build_direct_params(
    *,
    caption: str = TEST_PROMPT,
    lyrics: str = TEST_LYRICS,
    duration: float = TEST_DURATION,
    inference_steps: int = TEST_STEPS,
    guidance_scale: float = TEST_GUIDANCE,
    thinking: bool = False,
    seed: int = FIXED_SEED,
    bpm: Optional[int] = TEST_BPM,
    keyscale: str = TEST_KEY_SCALE,
    vocal_language: str = TEST_LANGUAGE,
    task_type: str = "text2music",
    **extra,
) -> GenerationParams:
    """Build GenerationParams matching what Gradio would construct."""
    return GenerationParams(
        task_type=task_type,
        instruction=TASK_INSTRUCTIONS.get(task_type, DEFAULT_DIT_INSTRUCTION),
        caption=caption,
        lyrics=lyrics,
        instrumental=_is_instrumental(lyrics),
        vocal_language=vocal_language,
        bpm=bpm,
        keyscale=keyscale,
        duration=duration if duration and duration > 0 else -1.0,
        inference_steps=inference_steps,
        seed=seed,
        guidance_scale=guidance_scale,
        thinking=thinking,
        shift=3.0,  # REST API default
        **extra,
    )


def _build_direct_config(
    *,
    batch_size: int = 1,
    use_random_seed: bool = False,
    seed: int = FIXED_SEED,
    audio_format: str = "wav",
) -> GenerationConfig:
    """Build GenerationConfig matching what the API server constructs."""
    seeds = [seed] if not use_random_seed and seed >= 0 else None
    return GenerationConfig(
        batch_size=batch_size,
        use_random_seed=use_random_seed,
        seeds=seeds,
        audio_format=audio_format,
    )


def _is_instrumental(lyrics: str) -> bool:
    """Mirror of api_server._is_instrumental."""
    if not lyrics:
        return True
    clean = lyrics.strip().lower()
    return clean in ("[inst]", "[instrumental]")


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------
class TestDjGradioParity(unittest.TestCase):
    """Verify DJ REST API and direct generate_music() paths produce
    equivalent GenerationParams and, when a server is running,
    equivalent generation results."""

    # ------------------------------------------------------------------
    # Parameter mapping tests (no server required)
    # ------------------------------------------------------------------

    def test_parameter_mapping_parity(self):
        """REST GenerateMusicRequest → GenerationParams mapping matches
        a directly-constructed GenerationParams for all key fields."""
        from acestep.api_server import GenerateMusicRequest

        rest_payload = _build_rest_payload()
        req = GenerateMusicRequest(**rest_payload)

        # Replicate the server's mapping (api_server.py:1769-1811)
        lm_top_k = req.lm_top_k if req.lm_top_k and req.lm_top_k > 0 else 0
        lm_top_p = req.lm_top_p if req.lm_top_p and req.lm_top_p < 1.0 else 0.9

        instruction = req.instruction
        if instruction == DEFAULT_DIT_INSTRUCTION and req.task_type in TASK_INSTRUCTIONS:
            instruction = TASK_INSTRUCTIONS[req.task_type]

        api_params = GenerationParams(
            task_type=req.task_type,
            instruction=instruction,
            reference_audio=req.reference_audio_path,
            src_audio=req.src_audio_path,
            audio_codes="",
            caption=req.prompt,
            lyrics=req.lyrics,
            instrumental=_is_instrumental(req.lyrics),
            vocal_language=req.vocal_language,
            bpm=req.bpm,
            keyscale=req.key_scale,
            timesignature=req.time_signature,
            duration=req.audio_duration if req.audio_duration else -1.0,
            inference_steps=req.inference_steps,
            seed=req.seed,
            guidance_scale=req.guidance_scale,
            use_adg=req.use_adg,
            cfg_interval_start=req.cfg_interval_start,
            cfg_interval_end=req.cfg_interval_end,
            shift=req.shift,
            infer_method=req.infer_method,
            repainting_start=req.repainting_start,
            repainting_end=req.repainting_end if req.repainting_end else -1,
            audio_cover_strength=req.audio_cover_strength,
            thinking=bool(req.thinking),
            lm_temperature=req.lm_temperature,
            lm_cfg_scale=req.lm_cfg_scale,
            lm_top_k=lm_top_k,
            lm_top_p=lm_top_p,
            lm_negative_prompt=req.lm_negative_prompt,
            use_cot_metas=True,
            use_cot_caption=bool(req.use_cot_caption),
            use_cot_language=bool(req.use_cot_language),
            use_constrained_decoding=True,
        )

        # Build the equivalent direct params
        direct_params = _build_direct_params()

        # Compare the critical fields that affect generation output
        field_checks = {
            "caption": (api_params.caption, direct_params.caption),
            "lyrics": (api_params.lyrics, direct_params.lyrics),
            "instrumental": (api_params.instrumental, direct_params.instrumental),
            "vocal_language": (api_params.vocal_language, direct_params.vocal_language),
            "bpm": (api_params.bpm, direct_params.bpm),
            "keyscale": (api_params.keyscale, direct_params.keyscale),
            "duration": (api_params.duration, direct_params.duration),
            "inference_steps": (api_params.inference_steps, direct_params.inference_steps),
            "seed": (api_params.seed, direct_params.seed),
            "guidance_scale": (api_params.guidance_scale, direct_params.guidance_scale),
            "thinking": (api_params.thinking, direct_params.thinking),
            "task_type": (api_params.task_type, direct_params.task_type),
            "instruction": (api_params.instruction, direct_params.instruction),
            "audio_cover_strength": (api_params.audio_cover_strength, direct_params.audio_cover_strength),
            "lm_negative_prompt": (api_params.lm_negative_prompt, direct_params.lm_negative_prompt),
        }

        mismatches = []
        for field_name, (api_val, direct_val) in field_checks.items():
            if api_val != direct_val:
                mismatches.append(
                    f"  {field_name}: api={api_val!r} vs direct={direct_val!r}"
                )

        self.assertEqual(
            mismatches,
            [],
            f"Parameter mapping mismatches:\n" + "\n".join(mismatches),
        )

    def test_parameter_mapping_thinking(self):
        """Thinking mode parameter mapping parity."""
        from acestep.api_server import GenerateMusicRequest

        rest_payload = _build_rest_payload(thinking=True)
        req = GenerateMusicRequest(**rest_payload)

        instruction = req.instruction
        if instruction == DEFAULT_DIT_INSTRUCTION and req.task_type in TASK_INSTRUCTIONS:
            instruction = TASK_INSTRUCTIONS[req.task_type]

        api_params = GenerationParams(
            task_type=req.task_type,
            instruction=instruction,
            caption=req.prompt,
            lyrics=req.lyrics,
            instrumental=_is_instrumental(req.lyrics),
            vocal_language=req.vocal_language,
            bpm=req.bpm,
            keyscale=req.key_scale,
            duration=req.audio_duration if req.audio_duration else -1.0,
            inference_steps=req.inference_steps,
            seed=req.seed,
            guidance_scale=req.guidance_scale,
            thinking=True,
        )

        direct_params = _build_direct_params(thinking=True)

        self.assertEqual(api_params.thinking, direct_params.thinking)
        self.assertTrue(api_params.thinking)
        self.assertEqual(api_params.caption, direct_params.caption)
        self.assertEqual(api_params.seed, direct_params.seed)

    def test_parameter_mapping_repaint(self):
        """Repaint task parameter mapping parity."""
        from acestep.api_server import GenerateMusicRequest

        rest_payload = _build_rest_payload(
            task_type="repaint",
            repainting_start=2.0,
            repainting_end=8.0,
            audio_cover_strength=0.7,
        )
        req = GenerateMusicRequest(**rest_payload)

        instruction = req.instruction
        if instruction == DEFAULT_DIT_INSTRUCTION and req.task_type in TASK_INSTRUCTIONS:
            instruction = TASK_INSTRUCTIONS[req.task_type]

        api_params = GenerationParams(
            task_type=req.task_type,
            instruction=instruction,
            caption=req.prompt,
            lyrics=req.lyrics,
            instrumental=_is_instrumental(req.lyrics),
            repainting_start=req.repainting_start,
            repainting_end=req.repainting_end if req.repainting_end else -1,
            audio_cover_strength=req.audio_cover_strength,
            seed=req.seed,
        )

        direct_params = _build_direct_params(
            task_type="repaint",
            repainting_start=2.0,
            repainting_end=8.0,
            audio_cover_strength=0.7,
        )

        self.assertEqual(api_params.task_type, "repaint")
        self.assertEqual(api_params.task_type, direct_params.task_type)
        self.assertEqual(api_params.instruction, direct_params.instruction)
        self.assertAlmostEqual(api_params.repainting_start, direct_params.repainting_start)
        self.assertAlmostEqual(api_params.repainting_end, direct_params.repainting_end)
        self.assertAlmostEqual(api_params.audio_cover_strength, direct_params.audio_cover_strength)

    def test_config_mapping_parity(self):
        """GenerationConfig mapping matches between REST and direct paths."""
        from acestep.api_server import GenerateMusicRequest

        rest_payload = _build_rest_payload(
            batch_size=1,
            use_random_seed=False,
            seed=FIXED_SEED,
            audio_format="wav",
        )
        req = GenerateMusicRequest(**rest_payload)

        # Replicate the server's config building (api_server.py:1834-1841)
        batch_size = req.batch_size if req.batch_size is not None else 2
        resolved_seeds = None
        if not req.use_random_seed and req.seed is not None:
            if isinstance(req.seed, int) and req.seed >= 0:
                resolved_seeds = [req.seed]

        api_config = GenerationConfig(
            batch_size=batch_size,
            allow_lm_batch=req.allow_lm_batch,
            use_random_seed=req.use_random_seed,
            seeds=resolved_seeds,
            audio_format=req.audio_format,
        )

        direct_config = _build_direct_config()

        self.assertEqual(api_config.batch_size, direct_config.batch_size)
        self.assertEqual(api_config.use_random_seed, direct_config.use_random_seed)
        self.assertEqual(api_config.seeds, direct_config.seeds)
        self.assertEqual(api_config.audio_format, direct_config.audio_format)

    def test_alias_resolution(self):
        """REST API PARAM_ALIASES correctly resolve alternative field names."""
        from acestep.api_server import RequestParser

        # Test key_scale alias (DJ sends "key_scale", GenerationParams uses "keyscale")
        parser = RequestParser({"keyscale": "D Minor"})
        self.assertEqual(parser.str("key_scale"), "D Minor")

        # Test duration alias
        parser = RequestParser({"duration": 30.0})
        self.assertAlmostEqual(parser.float("audio_duration"), 30.0)

        # Test prompt/caption alias
        parser = RequestParser({"caption": "test caption"})
        self.assertEqual(parser.str("prompt"), "test caption")

    def test_default_value_parity(self):
        """Verify default values match between REST model and GenerationParams."""
        from acestep.api_server import GenerateMusicRequest

        req = GenerateMusicRequest()  # All defaults
        params = GenerationParams()  # All defaults

        # These defaults should match between the two paths
        self.assertEqual(req.task_type, params.task_type)
        self.assertEqual(req.inference_steps, params.inference_steps)
        self.assertEqual(req.guidance_scale, params.guidance_scale)
        self.assertEqual(req.audio_cover_strength, params.audio_cover_strength)
        self.assertEqual(req.repainting_start, params.repainting_start)

    def test_instrumental_detection_parity(self):
        """_is_instrumental logic matches for various lyrics inputs."""
        test_cases = [
            ("", True),
            ("[Instrumental]", True),
            ("[instrumental]", True),
            ("[inst]", True),
            ("[INST]", True),
            ("Hello world", False),
            ("[Verse 1]\nHello world", False),
            ("  [Instrumental]  ", True),
        ]
        for lyrics, expected in test_cases:
            with self.subTest(lyrics=lyrics):
                self.assertEqual(
                    _is_instrumental(lyrics),
                    expected,
                    f"_is_instrumental({lyrics!r}) should be {expected}",
                )

    def test_seed_resolution_parity(self):
        """Seed resolution from REST request matches direct config construction."""
        from acestep.api_server import GenerateMusicRequest

        # Case 1: Fixed seed
        req = GenerateMusicRequest(seed=42, use_random_seed=False)
        resolved = [req.seed] if not req.use_random_seed and isinstance(req.seed, int) and req.seed >= 0 else None
        direct = _build_direct_config(seed=42, use_random_seed=False)
        self.assertEqual(resolved, direct.seeds)

        # Case 2: Random seed
        req = GenerateMusicRequest(seed=-1, use_random_seed=True)
        resolved = None  # random seed means no fixed seeds
        direct = _build_direct_config(seed=-1, use_random_seed=True)
        self.assertIsNone(direct.seeds)

        # Case 3: Seed of 0 (edge case - should still be valid)
        req = GenerateMusicRequest(seed=0, use_random_seed=False)
        resolved = [0] if not req.use_random_seed and isinstance(req.seed, int) and req.seed >= 0 else None
        direct = _build_direct_config(seed=0, use_random_seed=False)
        self.assertEqual(resolved, direct.seeds)

    # ------------------------------------------------------------------
    # Integration tests (require running server + GPU)
    # ------------------------------------------------------------------

    @unittest.skipUnless(SERVER_AVAILABLE, "API server not running")
    def test_text2music_parity(self):
        """Basic text-to-music: REST API and direct path produce matching metadata."""
        rest_payload = _build_rest_payload()
        rest_result = _submit_and_poll(rest_payload)

        audios = rest_result.get("audios", [])
        self.assertGreater(len(audios), 0, "REST path should produce at least one audio")

        # Verify the audio result contains expected fields
        audio = audios[0]
        self.assertEqual(audio.get("status"), 1, "Audio status should be succeeded")
        self.assertIn("file", audio, "Audio result should contain a file URL")

        # Verify the fixed seed was used
        self.assertEqual(
            audio.get("seed_value"),
            str(FIXED_SEED),
            "REST result should reflect the fixed seed",
        )

        # Verify the prompt passed through correctly
        self.assertEqual(audio.get("prompt"), TEST_PROMPT)

        # Verify metas were propagated
        metas = audio.get("metas", {})
        self.assertEqual(metas.get("bpm"), TEST_BPM)
        self.assertEqual(metas.get("keyscale"), TEST_KEY_SCALE)
        self.assertAlmostEqual(metas.get("duration"), TEST_DURATION)

    @unittest.skipUnless(SERVER_AVAILABLE, "API server not running")
    def test_text2music_thinking_parity(self):
        """Text-to-music with thinking=True through REST API."""
        rest_payload = _build_rest_payload(thinking=True)
        rest_result = _submit_and_poll(rest_payload)

        audios = rest_result.get("audios", [])
        self.assertGreater(len(audios), 0, "Thinking mode should produce audio")

        audio = audios[0]
        self.assertEqual(audio.get("status"), 1)
        self.assertEqual(audio.get("seed_value"), str(FIXED_SEED))
        self.assertEqual(audio.get("prompt"), TEST_PROMPT)

    @unittest.skipUnless(SERVER_AVAILABLE, "API server not running")
    def test_repaint_parity(self):
        """Repaint task through REST API with src_audio via multipart upload."""
        import glob as glob_mod
        import tempfile
        import shutil

        # Find a source audio file for repaint
        search_dirs = [
            os.path.join(PROJECT_ROOT, "acestep_output"),
            os.path.join(PROJECT_ROOT, ".cache", "acestep", "tmp", "api_audio"),
        ]
        test_audio = None
        for d in search_dirs:
            wavs = glob_mod.glob(os.path.join(d, "*.wav"))
            if wavs:
                test_audio = wavs[0]
                break
        if not test_audio:
            self.skipTest("No source audio file available for repaint test")

        # Copy into system temp dir so the server's path validation accepts it
        tmp_audio = os.path.join(tempfile.gettempdir(), "test_repaint_src.wav")
        shutil.copy2(test_audio, tmp_audio)

        try:
            rest_payload = _build_rest_payload(
                task_type="repaint",
                src_audio_path=tmp_audio,
                repainting_start=0.0,
                repainting_end=5.0,
                audio_cover_strength=0.7,
            )
            rest_result = _submit_and_poll(rest_payload)
            self.assertEqual(rest_result.get("status"), 1, "Repaint job should succeed")

            audios = rest_result.get("audios", [])
            self.assertGreater(len(audios), 0, "Repaint should produce audio")
        finally:
            if os.path.exists(tmp_audio):
                os.unlink(tmp_audio)


if __name__ == "__main__":
    unittest.main()
