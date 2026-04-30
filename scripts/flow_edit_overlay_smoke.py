"""Flow-edit overlay smoke test (#1156, post-redesign).

Drives ``inference.generate_music`` with ``task_type='cover'`` +
``flow_edit_morph=True`` so the V_delta overlay layers on top of the
existing cover dispatch.  This is the architecturally correct shape:
the user's caption/lyrics are the *target*; the overlay's
``flow_edit_source_caption`` / ``flow_edit_source_lyrics`` describe
the original audio.

Run on jieyue (or any GPU host):

    cd /root/data/repo/gongjunmin/workspace/ACE-Step-1.5
    conda activate acestep_v15_train
    CUDA_VISIBLE_DEVICES=1 python scripts/flow_edit_overlay_smoke.py

Outputs go to ``flow_edit_test_outputs/overlay_*.wav``.
"""

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

import torch
import torchaudio
from loguru import logger

from acestep.handler import AceStepHandler
from acestep.inference import GenerationConfig, GenerationParams, generate_music
from acestep.llm_inference import LLMHandler

OUT = REPO / "flow_edit_test_outputs"
OUT.mkdir(exist_ok=True)
SEED = 42
DIT_CONFIG = "acestep-v15-sft"

ex = json.loads((REPO / "examples/text2music/example_01.json").read_text())
src_path = OUT / f"baseline_01_seed{SEED}.wav"
assert src_path.exists(), f"missing baseline wav at {src_path}; run flow_edit_smoke_test.py first"

NEW_VERSE1 = (
    "[Verse 1]\n清晨阳光洒在花园里\n鸟儿欢唱迎接早晨\n"
    "露珠闪耀在叶尖上\n微风轻拂带来安宁\n"
    "远方传来悠扬钢琴声\n阳光穿过透明的窗户\n"
    "花香弥漫在空气中\n心情舒畅自由飞翔\n"
)
ORIG_VERSE1 = (
    "[Verse 1]\n黑夜里的风吹过耳畔\n甜蜜时光转瞬即万\n"
    "脚步飘摇在星光上\n心追节奏心跳狂乱\n"
    "耳边传来电吉他呼唤\n手指轻触碰点流点燃\n"
    "梦在云端任它蔓延\n疯狂跳跃自由无间\n"
)
TGT_LYRICS = ex["lyrics"].replace(ORIG_VERSE1, NEW_VERSE1)
assert TGT_LYRICS != ex["lyrics"], "verse-1 replace marker not found"

logger.info(f"Initializing DiT ({DIT_CONFIG})")
dit = AceStepHandler()
_, ok = dit.initialize_service(
    project_root=str(REPO), config_path=DIT_CONFIG, device="cuda",
    use_flash_attention=False, compile_model=False,
    offload_to_cpu=False, offload_dit_to_cpu=False, quantization=None,
    use_mlx_dit=False,
)
assert ok
llm = LLMHandler()


def run(label, n_min, n_max, n_avg, infer_steps=60, shift=3.0, guidance_scale=15.0):
    p = GenerationParams(
        # text2music task — silence-derived context for prepare_condition,
        # real src_latents only used for zt formation in the sampling loop.
        task_type="text2music",
        src_audio=str(src_path),
        caption=ex["caption"],          # target = original style (keep melody)
        lyrics=TGT_LYRICS,              # target = NEW lyrics
        # Flow-edit overlay — describes the source side for V_src.
        flow_edit_morph=True,
        flow_edit_source_caption=ex["caption"],
        flow_edit_source_lyrics=ex["lyrics"],
        flow_edit_n_min=n_min,
        flow_edit_n_max=n_max,
        flow_edit_n_avg=n_avg,
        instrumental=False,
        vocal_language=ex.get("language", "en"),
        bpm=ex.get("bpm"),
        keyscale=ex.get("keyscale", ""),
        timesignature=str(ex.get("timesignature", "")),
        duration=float(ex.get("duration", 120)),
        inference_steps=infer_steps,
        seed=SEED,
        guidance_scale=guidance_scale,
        shift=shift,
        thinking=False,
    )
    cfg = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[SEED])
    logger.info(f"[{label}] n_min={n_min} n_max={n_max} n_avg={n_avg}")
    t0 = time.time()
    r = generate_music(dit, llm, p, cfg, save_dir=str(OUT))
    dt = time.time() - t0
    if not r.success:
        logger.error(f"[{label}] FAILED: {r.error}")
        return
    audio = r.audios[0]
    out_path = OUT / f"overlay_{label}.wav"
    if isinstance(audio, dict) and "tensor" in audio:
        torchaudio.save(str(out_path), audio["tensor"].to(torch.float32),
                        audio.get("sample_rate", 48000))
    logger.info(f"[{label}] {dt:.1f}s -> {out_path}")


# Match ACE-Step 1.0 defaults exactly: shift=3.0 (FlowMatchEulerDiscreteScheduler
# default), guidance=15, infer=60, n_min=0, n_max=1, n_avg=1.
run("v10_shift3", 0.0, 1.0, 1, infer_steps=60, shift=3.0)
# Sanity: shift=1.0 (uniform schedule) for comparison.
run("v10_shift1", 0.0, 1.0, 1, infer_steps=60, shift=1.0)
