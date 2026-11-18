"""Queue four 10-track instrumental batches, one batch at a time.

Talks to the studio already running on port 7870. A second batch starts
only after the previous one finishes, so the GPU is not shared.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:7870"
LOG = Path(__file__).resolve().parents[1] / "studio_outputs" / "overnight.log"
POLL_SECONDS = 20

PROMPTS = [
    (
        "village-morning",
        "Peaceful Indian village morning lo-fi instrumental. Imagine sitting on a traditional village veranda, sipping hot filter coffee as the first golden rays of sunlight fall across green fields. Gentle bansuri flute melodies, delicate sitar plucks, soft santoor accents and subtle Indian veena textures. Relaxed, mellow tabla rhythms blended with warm lo-fi hip hop beats, jazzy Rhodes piano chords, deep soft bass and gentle vinyl crackle. Beautiful birdsong, distant rooster calls, a faint morning breeze and subtle village ambience. Nostalgic, warm, earthy and deeply comforting. A beautiful blend of South Indian rural atmosphere and contemporary chillhop. Slow, laid-back groove, 78 BPM, dreamy melodic progression, organic acoustic textures, soothing and immersive. Entirely instrumental, no vocals, no chanting, no spoken words.",
    ),
    (
        "cafe-evening",
        "Relaxed Indian café lo-fi instrumental for a peaceful evening. Soft acoustic guitar, mellow electric piano, delicate bansuri flute phrases, occasional sitar flourishes, understated tabla and brushed percussion. Gentle hip hop drum loops, warm bassline, jazzy seventh chords, subtle vinyl crackle and ambient city rain sounds. Beautiful repeating melodies, understated Indian musical motifs, laid-back rhythm and cozy nostalgic atmosphere. Contemporary Indian chill beats, organic and effortlessly groovy. 82 BPM. No vocals, no lyrics.",
    ),
    (
        "classical-fusion",
        "A sophisticated Indian classical lo-fi instrumental fusion. Delicate sitar improvisations, soulful sarod melodies, expressive bansuri flute, gentle tanpura drone and intricate but restrained tabla percussion. Blended with mellow lo-fi hip hop beats, jazzy Rhodes piano, warm sub bass, dusty vinyl textures and soft atmospheric pads. Indian ragas interpreted through a contemporary chillhop soundscape. Meditative yet groovy, soulful, elegant and cinematic. Organic acoustic instruments with modern studio production. 75 BPM. Instrumental only.",
    ),
    (
        "monsoon-boom-bap",
        "Indian lo-fi hip hop instrumental, deeply atmospheric and soulful. Warm mellow electric piano chords blended with expressive bansuri flute melodies, gentle sitar plucks, subtle sarangi textures and soft Indian classical tabla rhythms. Laid-back boom bap drum groove, dusty vinyl crackle, warm analog tape saturation, deep rounded bass, jazzy chord progressions and dreamy ambient textures. Subtle monsoon rain ambience. Nostalgic, peaceful, intimate and emotionally rich. Modern chillhop production infused with authentic Indian musical soul. Smooth transitions, evolving instrumental layers, beautiful melodic hooks, relaxed groove, immersive soundscape. 80 BPM. Entirely instrumental, no vocals, no chanting, no spoken words.",
    ),
]


def log(message: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def request(method: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_until_ready() -> None:
    for _ in range(60):
        try:
            status = request("GET", "/api/status")
        except (urllib.error.URLError, TimeoutError) as exc:
            log(f"studio not reachable yet: {exc}")
            time.sleep(10)
            continue
        log(status.get("message", ""))
        if status.get("ready"):
            return
        time.sleep(10)
    raise SystemExit("studio did not become ready")


def run_batch(name: str, prompt: str) -> None:
    created = request(
        "POST",
        "/api/generate",
        {"prompt": prompt, "count": 10, "quality": "high"},
    )
    job_id = created["job_id"]
    log(f"{name} started job {job_id}")
    while True:
        job = request("GET", f"/api/jobs/{job_id}")
        state = job.get("state")
        tracks = len(job.get("tracks") or [])
        log(
            f"{name} {state} {int((job.get('progress') or 0) * 100)}% "
            f"saved {tracks}/10 | {job.get('detail') or job.get('message')}"
        )
        if state == "done":
            log(f"{name} finished in {job.get('detail')}")
            return
        if state == "error":
            log(f"{name} failed: {job.get('detail')}")
            return
        time.sleep(POLL_SECONDS)


def main() -> None:
    log("overnight run starting")
    wait_until_ready()
    for name, prompt in PROMPTS:
        try:
            run_batch(name, prompt)
        except Exception as exc:
            log(f"{name} request failed: {exc}")
    log("overnight run finished")


if __name__ == "__main__":
    main()
