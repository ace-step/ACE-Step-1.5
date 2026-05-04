"""Library tab backend: scan, rate, and delete generated songs."""

import json
import os
import tempfile
from datetime import datetime

from loguru import logger

from acestep.ui.gradio.events.results.generation_info import DEFAULT_RESULTS_DIR

RATINGS_FILE = os.path.join(DEFAULT_RESULTS_DIR, "ratings.json")
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".opus", ".aac"}


# ── Ratings persistence ───────────────────────────────────────────────────────

def _load_ratings() -> dict:
    try:
        if os.path.exists(RATINGS_FILE):
            with open(RATINGS_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                logger.error(f"[Library] Ratings file is not a dict (got {type(payload).__name__}), ignoring: {RATINGS_FILE}")
                return {}
            return payload
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"[Library] Failed to load ratings from {RATINGS_FILE}: {e}")
    return {}


def _save_ratings(ratings: dict) -> None:
    os.makedirs(DEFAULT_RESULTS_DIR, exist_ok=True)
    dir_ = os.path.dirname(RATINGS_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(ratings, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, RATINGS_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── Helpers ───────────────────────────────────────────────────────────────────

def rating_stars(rating: int) -> str:
    """Return a star-string representation for a 0-5 rating."""
    if not rating:
        return "—"
    return "★" * int(rating) + "☆" * (5 - int(rating))


def _format_date(ts: int) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError) as e:
        logger.debug(f"[Library] Could not format timestamp {ts}: {e}")
        return "Unknown"


# ── Core library operations ───────────────────────────────────────────────────

def scan_library(sort_by: str = "date", min_rating: int = 0) -> list:
    """Scan gradio_outputs for all generated audio files.

    Walks the entire gradio_outputs tree recursively so that files in any
    subdirectory structure are discovered.  The date shown for each file is
    derived from its filesystem mtime, which is accurate regardless of the
    parent directory's name.

    Args:
        sort_by: One of "date" (newest first), "name" (A-Z), "rating" (highest first).
        min_rating: If > 0, exclude songs with a lower rating (unrated = 0).

    Returns:
        List of song dicts, each with keys:
            path, stem, date_str, ts, bpm, caption, rating, metadata.
    """
    if not os.path.exists(DEFAULT_RESULTS_DIR):
        return []

    ratings = _load_ratings()
    songs = []

    for root, _dirs, files in os.walk(DEFAULT_RESULTS_DIR):
        for filename in files:
            stem, ext = os.path.splitext(filename)
            if ext.lower() not in AUDIO_EXTENSIONS:
                continue

            native_path = os.path.join(root, filename)
            audio_path = os.path.normpath(native_path).replace("\\", "/")
            json_path = os.path.normpath(
                os.path.join(root, stem + ".json")
            ).replace("\\", "/")

            try:
                ts = int(os.path.getmtime(native_path))
            except OSError as e:
                logger.debug(f"[Library] Could not read mtime for {native_path}: {e}")
                ts = 0

            metadata: dict = {}
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        _loaded = json.load(f)
                    if isinstance(_loaded, dict):
                        metadata = _loaded
                except (json.JSONDecodeError, OSError) as e:
                    logger.error(f"[Library] Failed to load sidecar {json_path}: {e}")

            rating = ratings.get(audio_path, 0)
            if min_rating > 0 and rating < min_rating:
                continue

            caption = metadata.get("caption", "") or ""
            caption_preview = (caption[:80] + "…") if len(caption) > 80 else caption

            raw_bpm = metadata.get("cot_bpm") or metadata.get("bpm")
            try:
                bpm_display = str(int(raw_bpm)) if raw_bpm else "auto"
            except (ValueError, TypeError):
                bpm_display = "auto"

            songs.append({
                "path": audio_path,
                "stem": stem,
                "date_str": _format_date(ts),
                "ts": ts,
                "bpm": bpm_display,
                "caption": caption_preview,
                "rating": rating,
                "metadata": metadata,
            })

    # Apply sort
    if sort_by == "name":
        songs.sort(key=lambda s: s["stem"].lower())
    elif sort_by == "rating":
        songs.sort(key=lambda s: s["rating"], reverse=True)
    else:
        # "date" — sort by actual mtime, newest first
        songs.sort(key=lambda s: s["ts"], reverse=True)

    return songs


def get_library_rows(songs: list) -> list:
    """Convert a song list to rows suitable for gr.Dataframe."""
    return [
        [s["stem"], s["date_str"], rating_stars(s["rating"])]
        for s in songs
    ]


def set_rating(audio_path: str, rating) -> None:
    """Persist a 1-5 star rating for the given audio path."""
    ratings = _load_ratings()
    if rating is not None and int(rating) > 0:
        ratings[audio_path] = int(rating)
    else:
        ratings.pop(audio_path, None)
    _save_ratings(ratings)


def delete_song(audio_path: str) -> tuple:
    """Delete audio + companion sidecar files and remove stored rating.

    Returns:
        (success: bool, message: str)
    """
    try:
        real = os.path.realpath(audio_path)
        root = os.path.realpath(DEFAULT_RESULTS_DIR)
        try:
            if os.path.commonpath([real, root]) != root:
                return False, "❌ Refused: path outside library root"
        except ValueError:
            return False, "❌ Refused: path outside library root"
        if os.path.splitext(real)[1].lower() not in AUDIO_EXTENSIONS:
            return False, "❌ Refused: not a supported audio file"
        if os.path.isfile(real):
            os.remove(real)
        stem = os.path.splitext(real)[0]
        for sidecar in [".json", ".repaint_latents.npy", ".vtt"]:
            sidecar_path = stem + sidecar
            if os.path.exists(sidecar_path):
                os.remove(sidecar_path)
        # Remove the parent folder if it is now empty
        parent = os.path.dirname(real)
        if parent and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
        ratings = _load_ratings()
        ratings.pop(audio_path, None)
        _save_ratings(ratings)
        return True, f"🗑️ Deleted: **{os.path.basename(audio_path)}**"
    except Exception as exc:
        return False, f"❌ Delete failed: {exc}"
