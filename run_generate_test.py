#!/usr/bin/env python3
"""Quick smoke test: generate 2 full songs via generate_music() with LM."""

import json
import os
import sys
import time

os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)

sys.path.insert(0, os.path.dirname(__file__))

from loguru import logger
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music

PROJECT_ROOT = os.path.dirname(__file__)
CHECKPOINT_DIR = os.path.join(PROJECT_ROOT, "checkpoints")
SAVE_DIR = os.path.join(PROJECT_ROOT, "output", "test_generate")
EXAMPLES = [
    os.path.join(PROJECT_ROOT, "examples", "text2music", "example_01.json"),
    os.path.join(PROJECT_ROOT, "examples", "text2music", "example_10.json"),
]


def main():
    os.makedirs(SAVE_DIR, exist_ok=True)

    # ---- 1. Init DiT handler (turbo) ----
    logger.info("Initializing DiT handler (turbo)...")
    t0 = time.time()
    dit_handler = AceStepHandler()
    status_msg, success = dit_handler.initialize_service(
        project_root=PROJECT_ROOT,
        config_path="acestep-v15-turbo",
        device="auto",
        offload_to_cpu=False,
    )
    if not success:
        logger.error(f"DiT init failed: {status_msg}")
        sys.exit(1)
    logger.info(f"DiT loaded in {time.time() - t0:.1f}s — {status_msg}")

    # ---- 2. Init LLM handler (0.6B, MLX) ----
    logger.info("Initializing LLM handler (0.6B, MLX)...")
    t0 = time.time()
    llm_handler = LLMHandler()
    status_msg, success = llm_handler.initialize(
        checkpoint_dir=CHECKPOINT_DIR,
        lm_model_path="acestep-5Hz-lm-0.6B",
        backend="mlx",
        device="auto",
        offload_to_cpu=False,
        dtype=None,
    )
    if not success:
        logger.error(f"LLM init failed: {status_msg}")
        sys.exit(1)
    logger.info(f"LLM loaded in {time.time() - t0:.1f}s — {status_msg}")

    # ---- 3. Generate songs ----
    for i, example_path in enumerate(EXAMPLES):
        logger.info(f"\n{'='*60}")
        logger.info(f"Generating song {i+1}/{len(EXAMPLES)}: {os.path.basename(example_path)}")
        logger.info(f"{'='*60}")

        with open(example_path, "r", encoding="utf-8") as f:
            ex = json.load(f)

        params = GenerationParams(
            task_type="text2music",
            thinking=True,
            caption=ex.get("caption", ""),
            lyrics=ex.get("lyrics", ""),
            bpm=ex.get("bpm"),
            keyscale=ex.get("keyscale", ""),
            timesignature=ex.get("timesignature", ""),
            vocal_language=ex.get("language", "en"),
            duration=ex.get("duration"),
            inference_steps=8,
            guidance_scale=1.0,
            seed=-1,
        )

        config = GenerationConfig(
            batch_size=1,
            audio_format="wav",
        )

        t0 = time.time()
        result = generate_music(
            dit_handler,
            llm_handler,
            params=params,
            config=config,
            save_dir=SAVE_DIR,
        )
        elapsed = time.time() - t0

        if result.success:
            logger.info(f"Song {i+1} OK — {elapsed:.1f}s")
            for audio in result.audios:
                logger.info(f"  -> {audio.get('path', '(in-memory)')}")
        else:
            logger.error(f"Song {i+1} FAILED — {elapsed:.1f}s — {result.status_message}")

    logger.info("\nDone. Output dir: " + SAVE_DIR)


if __name__ == "__main__":
    main()
