"""A small instrumental studio in front of ACE-Step.

The page takes one prompt, makes the requested number of vocal-free tracks,
and saves a WAV master plus an MP3 for each one.
"""

from __future__ import annotations

import sys
import threading
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "studio") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio"))

import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from plan import (
    DEFAULT_QUALITY,
    MAX_TRACKS,
    QUALITY_PRESETS,
    choose_parallel_batch,
    folder_name_for_prompt,
    instrumental_caption,
    normalize_quality,
)

OUTPUT_ROOT = ROOT / "studio_outputs"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ACE-Step Studio")
app.mount("/files", StaticFiles(directory=str(OUTPUT_ROOT)), name="files")

_state_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_engine = {
    "ready": False,
    "message": "Starting the studio…",
    "model": "",
    "is_xl": False,
    "dit": None,
    "llm": None,
}


class GenerateRequest(BaseModel):
    prompt: str
    count: int = Field(default=1, ge=1, le=MAX_TRACKS)
    quality: str = DEFAULT_QUALITY


def _preferred_model() -> str:
    """Use the XL turbo weights when they are fully present."""
    xl = ROOT / "checkpoints" / "acestep-v15-xl-turbo"
    xl_weights = list(xl.glob("*.safetensors")) if xl.is_dir() else []
    if len(xl_weights) >= 4:
        return "acestep-v15-xl-turbo"
    return "acestep-v15-turbo"


def _free_vram_gb() -> float:
    if not torch.cuda.is_available():
        return 0.0
    free_bytes, _ = torch.cuda.mem_get_info()
    return free_bytes / (1024 ** 3)


def _load_models() -> None:
    from acestep.gpu_config import get_gpu_config
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler

    model_name = _preferred_model()
    gpu = get_gpu_config()
    quantization = "int8_weight_only" if gpu.quantization_default else None
    _engine["message"] = f"Loading {model_name}…"
    _engine["model"] = model_name
    _engine["is_xl"] = "xl" in model_name

    dit = AceStepHandler()
    status, ok = dit.initialize_service(
        project_root=str(ROOT),
        config_path=model_name,
        device="auto",
        use_flash_attention=False,
        compile_model=False,
        offload_to_cpu=gpu.offload_to_cpu_default,
        offload_dit_to_cpu=gpu.offload_dit_to_cpu_default,
        quantization=quantization,
    )
    if not ok:
        _engine["message"] = f"Could not load the audio model: {status}"
        return

    llm = LLMHandler()
    lm_status, lm_ok = llm.initialize(
        checkpoint_dir=str(ROOT / "checkpoints"),
        lm_model_path="acestep-5Hz-lm-1.7B",
        backend="pt",
        device="auto",
        offload_to_cpu=gpu.offload_to_cpu_default,
        dtype=None,
    )
    if not lm_ok:
        _engine["message"] = f"Could not load the planner model: {lm_status}"
        return

    _engine["dit"] = dit
    _engine["llm"] = llm
    _engine["ready"] = True
    _engine["message"] = (
        f"Ready. Audio model {model_name}, planner acestep-5Hz-lm-1.7B. "
        "Files are saved in studio_outputs."
    )


def _save_pair(tensor, sample_rate: int, folder: Path, index: int, quality: str) -> dict:
    from acestep.audio_utils import AudioSaver

    preset = QUALITY_PRESETS[quality]
    stem = f"track-{index:02d}"
    wav_path = folder / f"{stem}.wav"
    mp3_path = folder / f"{stem}.mp3"
    saver = AudioSaver(default_format=preset["wav_format"])
    saver.save_audio(
        tensor,
        wav_path,
        sample_rate=sample_rate,
        format=preset["wav_format"],
        channels_first=True,
    )
    saver.save_audio(
        tensor,
        mp3_path,
        sample_rate=sample_rate,
        format="mp3",
        channels_first=True,
        mp3_bitrate=preset["mp3_bitrate"],
        mp3_sample_rate=preset["mp3_sample_rate"],
    )
    return {"wav": wav_path, "mp3": mp3_path}


def _generate_wave(caption: str, count: int, job: dict, done: int):
    from acestep.inference import GenerationConfig, GenerationParams, generate_music

    def progress(*args, **kwargs):
        message = kwargs.get("desc")
        if message is None and len(args) > 1 and not isinstance(args[1], (int, float)):
            message = args[1]
        if message:
            job["detail"] = str(message)
        if args and isinstance(args[0], (int, float)) and job["count"]:
            frac = max(0.0, min(1.0, float(args[0])))
            job["progress"] = (done + frac * count) / job["count"]

    params = GenerationParams(
        caption=caption,
        lyrics="[Instrumental]",
        instrumental=True,
        thinking=True,
        use_cot_caption=True,
        use_cot_metas=True,
        use_cot_language=False,
        inference_steps=8,
        duration=-1,
    )
    config = GenerationConfig(
        batch_size=count,
        allow_lm_batch=count > 1,
        use_random_seed=True,
        lm_batch_chunk_size=count,
        audio_format="wav32",
    )
    return generate_music(
        _engine["dit"],
        _engine["llm"],
        params,
        config,
        save_dir=None,
        progress=progress,
    )


def _output_folder(prompt: str) -> Path:
    """Create a new folder named from a short summary of the prompt."""
    base = folder_name_for_prompt(prompt)
    candidate = base
    number = 2
    while (OUTPUT_ROOT / candidate).exists():
        candidate = f"{base}-{number}"
        number += 1
    folder = OUTPUT_ROOT / candidate
    folder.mkdir(parents=True)
    return folder


def _run_job(job_id: str) -> None:
    job = _jobs[job_id]
    folder = _output_folder(job["prompt"])
    job["folder"] = folder.name
    try:
        caption = instrumental_caption(job["prompt"])
        remaining = job["count"]
        done = 0
        parallel = choose_parallel_batch(_free_vram_gb(), remaining, _engine["is_xl"])
        while done < job["count"]:
            wave = min(parallel, job["count"] - done)
            start = done + 1
            end = done + wave
            span = f"track {start}" if wave == 1 else f"tracks {start}–{end}"
            mode = "together" if wave > 1 else "one at a time"
            job["message"] = f"Generating {span} of {job['count']} ({mode})"
            job["progress"] = done / job["count"]
            try:
                result = _generate_wave(caption, wave, job, done)
            except RuntimeError as exc:
                if wave > 1 and "out of memory" in str(exc).lower():
                    torch.cuda.empty_cache()
                    parallel = 1
                    job["detail"] = "Not enough GPU memory for a batch. Continuing one track at a time."
                    continue
                raise
            if not result.success or not result.audios:
                raise RuntimeError(result.error or result.status_message or "Generation failed")
            for audio in result.audios:
                done += 1
                saved = _save_pair(
                    audio["tensor"],
                    int(audio["sample_rate"]),
                    folder,
                    done,
                    job["quality"],
                )
                job["tracks"].append(
                    {
                        "index": done,
                        "wav": f"/files/{folder.name}/{saved['wav'].name}",
                        "mp3": f"/files/{folder.name}/{saved['mp3'].name}",
                    }
                )
                job["progress"] = done / job["count"]
                job["message"] = f"Saved track {done} of {job['count']}"
            torch.cuda.empty_cache()
        job["state"] = "done"
        job["progress"] = 1
        job["message"] = f"Finished {job['count']} track{'s' if job['count'] != 1 else ''}."
        job["detail"] = str(folder)
    except Exception as exc:
        job["state"] = "error"
        job["message"] = "Generation failed"
        job["detail"] = str(exc)
        traceback.print_exc()


@app.get("/")
def index():
    return FileResponse(ROOT / "studio" / "index.html")


@app.get("/api/status")
def status():
    return {
        "ready": _engine["ready"],
        "message": _engine["message"],
        "model": _engine["model"],
        "default_quality": DEFAULT_QUALITY,
        "qualities": [
            {"id": key, "label": value["label"]}
            for key, value in QUALITY_PRESETS.items()
        ],
    }


@app.post("/api/generate")
def generate(body: GenerateRequest):
    if not _engine["ready"]:
        return _error(_engine["message"], 409)
    try:
        instrumental_caption(body.prompt)
    except ValueError as exc:
        return _error(str(exc), 400)
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "prompt": body.prompt.strip(),
        "count": body.count,
        "quality": normalize_quality(body.quality),
        "state": "running",
        "progress": 0,
        "message": "Queued",
        "detail": "",
        "tracks": [],
    }
    with _state_lock:
        _jobs[job_id] = job
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return _error("Unknown job", 404)
    return job


def _error(message: str, code: int):
    from fastapi.responses import JSONResponse

    return JSONResponse({"error": message}, status_code=code)


@app.on_event("startup")
def startup():
    threading.Thread(target=_load_models, daemon=True).start()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7870, log_level="info")
