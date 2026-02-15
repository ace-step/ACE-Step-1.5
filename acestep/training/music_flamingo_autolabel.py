"""Music-Flamingo online autolabel client.

This module provides a robust wrapper around the Hugging Face Space
`nvidia/music-flamingo` (Gradio).

Features:
  - Endpoint discovery via `view_api(return_format="dict")` (supports schema variants)
  - Hard-prefer the `/infer` endpoint when present
  - Audio upload via `handle_file`
  - Two-step prompting: structured description + lyrics extraction

Environment variables:
  - ACESTEP_MUSIC_FLAMINGO_SPACE: Space id (default: nvidia/music-flamingo)
  - HF_TOKEN / HUGGINGFACEHUB_API_TOKEN: auth token (optional)
  - ACESTEP_MUSIC_FLAMINGO_PROMPT_DESCRIBE: override describe prompt
  - ACESTEP_MUSIC_FLAMINGO_PROMPT_DESCRIBE_FULL: override full-detail describe prompt
  - ACESTEP_MUSIC_FLAMINGO_PROMPT_LYRICS: override lyrics prompt
"""

from __future__ import annotations

import json
import os
import re
import ast
import contextlib
import io
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

from loguru import logger

try:
    # Gradio v4+ typically installs gradio_client, but keep it optional.
    from gradio_client import Client, handle_file
except Exception:  # pragma: no cover
    Client = None
    handle_file = None


DEFAULT_SPACE_ID = os.getenv("ACESTEP_MUSIC_FLAMINGO_SPACE", "nvidia/music-flamingo")

DEFAULT_PROMPT_DESCRIBE_JSON = (
    "Return STRICT JSON only (no markdown, no extra text). "
    "Keys: caption (string), genres (string, comma-separated), bpm (integer or null), "
    "keyscale (string like 'C major' or 'A minor' or null), timesignature (string like '4/4' or null), "
    "vocal_language (string or null), is_instrumental (boolean). "
    "If unknown, use null (or empty string for caption/genres). "
    "Analyze the track and fill the fields."
)

# This matches the prompt that performs best in the public Space UI.
DEFAULT_PROMPT_DESCRIBE_FULL = (
    "Write a single-paragraph track card (no line breaks), 90-120 words. Include: genre + overall vibe + broad instrumentation/production + vocals (if present). Add metadata inline exactly like: (Key: X; BPM: Y; Meter: Z) using unknown if unsure. Do NOT quote lyrics or include example lines. For themes, use one short paraphrase sentence only. Avoid: verse/chorus/drop structure, stereo imaging, EQ/compression/mastering jargon, and overly specific vocal type labels (no \"tenor/baritone\"). Output only the paragraph."
)

DEFAULT_PROMPT_LYRICS = "Extract the lyrics"

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_UNQUOTED_KEY_RE = re.compile(r"([\{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)\s*")
_SINGLE_QUOTED_STR_RE = re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'")


@dataclass
class FlamingoMeta:
    caption: str = ""
    genres: str = ""
    bpm: Optional[int] = None
    keyscale: str = ""
    timesignature: str = ""
    duration_s: Optional[int] = None
    vocal_language: str = "unknown"
    is_instrumental: bool = False


def _strip_status_prefix(text: str) -> str:
    """The Space often prefixes output with a status line and a blank line."""
    if not text:
        return ""
    parts = text.split("\n\n", 1)
    return parts[1].strip() if len(parts) == 2 else text.strip()


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    m = _JSON_RE.search(text)
    if not m:
        return None

    block = m.group(0).strip()

    # 1) Try strict JSON first.
    try:
        return json.loads(block)
    except Exception:
        pass

    # 2) Try to parse a Python-literal dict (already-quoted keys, single quotes, True/False/None).
    try:
        obj = ast.literal_eval(block)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 3) Normalize the common "pseudo JSON" returned by some LMs:
    #    {caption: '...', genres: ['a','b'], bpm: 120.5, is_instrumental: False}
    normalized = block
    # Quote bare keys
    normalized = re.sub(r"([\{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', normalized)
    # Convert single-quoted strings to double-quoted strings
    normalized = _SINGLE_QUOTED_STR_RE.sub(lambda m: '"' + m.group(1).replace('\\"', '"').replace('"', '\\"') + '"', normalized)
    # Convert Python literals to JSON literals
    normalized = normalized.replace("None", "null").replace("True", "true").replace("False", "false")

    try:
        return json.loads(normalized)
    except Exception:
        pass

    # 4) Last-resort: regex extraction for common fields.
    #    This prevents dumping the entire dict-like string into the caption textbox
    #    when the model returns something JSON-ish but not machine-parseable.

    def _rx_str(key: str) -> Optional[str]:
        # Matches key: 'value'  OR  'key': "value"  OR  "key": 'value'
        m = re.search(
            rf"(?:\"{key}\"|'{key}'|{key})\s*:\s*(\"[^\"]*\"|'[^']*')",
            block,
            re.DOTALL,
        )
        if not m:
            return None
        v = m.group(1).strip()
        return v.strip('"').strip("'").strip()

    def _rx_num(*keys: str) -> Optional[float]:
        for key in keys:
            m = re.search(rf"(?:\"{key}\"|'{key}'|{key})\s*:\s*([0-9]+(?:\.[0-9]+)?)", block)
            if m:
                try:
                    return float(m.group(1))
                except Exception:
                    pass
        return None

    def _rx_bool(*keys: str) -> Optional[bool]:
        for key in keys:
            m = re.search(
                rf"(?:\"{key}\"|'{key}'|{key})\s*:\s*(true|false|True|False|0|1)",
                block,
            )
            if m:
                val = m.group(1)
                return val in {"true", "True", "1"}
        return None

    def _rx_list_str(key: str) -> Optional[str]:
        # genres: ['a', 'b']  OR  "genres": ["a","b"]
        m = re.search(rf"(?:\"{key}\"|'{key}'|{key})\s*:\s*\[(.*?)\]", block, re.DOTALL)
        if not m:
            return None
        inner = m.group(1)
        # Collect quoted items
        items = re.findall(r"\"([^\"]+)\"|'([^']+)'", inner)
        flat = [a or b for (a, b) in items if (a or b)]
        return ", ".join(dict.fromkeys([s.strip() for s in flat if s.strip()]))

    caption = _rx_str("caption") or _rx_str("description") or _rx_str("summary")
    genres = _rx_list_str("genres") or _rx_list_str("genre") or _rx_str("genres") or _rx_str("genre")
    bpm = _rx_num("bpm", "tempo")
    keyscale = _rx_str("keyscale") or _rx_str("key")
    timesig = _rx_str("timesignature") or _rx_str("time_signature") or _rx_str("meter")
    vlang = _rx_str("vocal_language") or _rx_str("language") or _rx_str("lang")
    instr = _rx_bool("is_instrumental", "instrumental")

    if any(v is not None and v != "" for v in [caption, genres, bpm, keyscale, timesig, vlang, instr]):
        out: Dict[str, Any] = {}
        if caption:
            out["caption"] = caption
        if genres:
            out["genres"] = genres
        if bpm is not None:
            out["bpm"] = bpm
        if keyscale:
            out["keyscale"] = keyscale
        if timesig:
            out["timesignature"] = timesig
        if vlang:
            out["vocal_language"] = vlang
        if instr is not None:
            out["is_instrumental"] = instr
        return out

    return None


def _coerce_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = re.sub(r"[^\d]", "", v)
        return int(s) if s else None
    return None


def _first_nonempty(d: Dict[str, Any], keys: list[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return None


def _boolish(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes", "y", "instrumental"}
    return False


_NBSP_CHARS = "\u00a0\u202f\u2007"


def _norm_ws(s: str) -> str:
    """Normalize whitespace (including NBSP-like chars) for regex stability."""
    if not s:
        return ""
    for ch in _NBSP_CHARS:
        s = s.replace(ch, " ")
    return s


# -----------------------------------------------------------------------------
# Lightweight language detection from lyrics (no external deps)
# -----------------------------------------------------------------------------

_LANG_STOPWORDS: Dict[str, set[str]] = {
    # Minimal, high-signal stopwords. This is intentionally small and cheap.
    "en": {"the", "and", "you", "i", "to", "a", "of", "in", "is", "it", "me", "my", "on", "for", "we"},
    "it": {"che", "non", "io", "tu", "mi", "ti", "si", "ma", "per", "con", "una", "un", "sono", "sei"},
    "es": {"que", "no", "yo", "tu", "me", "te", "si", "pero", "por", "con", "una", "un", "soy", "eres"},
    "fr": {"que", "ne", "pas", "je", "tu", "il", "elle", "nous", "vous", "pour", "avec", "une", "un", "est"},
    "de": {"und", "ich", "du", "nicht", "ein", "eine", "ist", "wir", "ihr", "sie", "für", "mit"},
    "pt": {"que", "não", "eu", "tu", "você", "me", "te", "para", "com", "uma", "um", "é", "somos"},
}


def detect_language_from_lyrics(lyrics: str) -> str:
    """Best-effort language detection from lyrics.

    Returns a VALID_LANGUAGES-compatible code (e.g. 'en') or 'unknown'.
    This is a heuristic, but it is usually better than leaving 'unknown'
    when we have clear, non-instrumental lyrics.
    """
    if not lyrics:
        return "unknown"
    txt = lyrics.strip()
    if not txt or txt.lower() == "[instrumental]":
        return "unknown"

    # Tokenize cheaply.
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", txt.lower())
    if len(words) < 15:
        return "unknown"

    scores: Dict[str, int] = {k: 0 for k in _LANG_STOPWORDS.keys()}
    for w in words[:5000]:
        for lang, sw in _LANG_STOPWORDS.items():
            if w in sw:
                scores[lang] += 1

    best = max(scores.items(), key=lambda kv: kv[1])
    # Require a minimum margin and absolute count to avoid random ties.
    sorted_scores = sorted(scores.values(), reverse=True)
    if best[1] >= 4 and (len(sorted_scores) < 2 or best[1] >= sorted_scores[1] + 2):
        return best[0]
    return "unknown"


def _pick_genre_from_description(desc: str) -> str:
    """Best-effort genre extraction from the first sentence/line."""
    if not desc:
        return ""
    text = _norm_ws(desc).strip()
    first = re.split(r"[\n\.]+", text, maxsplit=1)[0]
    m = re.search(r"This track is\s+(?:an?|the)\s+(.+?)(?:\s+(?:piece|track))\b", first, re.IGNORECASE)
    phrase = m.group(1).strip() if m else ""
    if not phrase:
        # Another common pattern: "This is a <genre> ..."
        m2 = re.search(r"This\s+(?:track\s+)?is\s+(?:an?|the)\s+(.+?)\b", first, re.IGNORECASE)
        phrase = m2.group(1).strip() if m2 else ""

    if not phrase:
        return ""

    # Heuristic: prefer trailing Title-Case words (e.g., "uplifting Progressive House")
    words = phrase.replace("—", " ").replace("-", " ").split()
    tail = []
    for w in reversed(words):
        if w and (w[0].isupper() or w.isupper()):
            tail.append(w)
        else:
            if tail:
                break
    if len(tail) >= 1:
        g = " ".join(reversed(tail)).strip()
        # Avoid silly single adjectives
        if len(g.split()) >= 1 and len(g) >= 3:
            return g

    # Fallback: last two words
    return " ".join(words[-2:]).strip() if len(words) >= 2 else phrase


def _parse_meta_from_full_text(desc: str) -> FlamingoMeta:
    """Parse bpm/key/timesig/language/instrumental from the verbose description text."""
    text = _norm_ws(desc)

    # BPM: "≈90.91 BPM" or "at 176 BPM"
    bpm = None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*BPM\b", text, re.IGNORECASE)
    if m:
        try:
            bpm = int(round(float(m.group(1))))
        except Exception:
            bpm = None

    # Key: "in C minor" / "in Ab major" (support ASCII and Unicode accidentals).
    keyscale = ""
    m = re.search(r"\b(?:in|key of|key)\s+([A-G](?:#|b|♯|♭)?)\s*(major|minor)\b", text, re.IGNORECASE)
    if m:
        note = m.group(1) or ""
        # Normalize Unicode accidentals to ASCII for ACE-Step validation.
        note = note.replace("♯", "#").replace("♭", "b")
        note = (note[0].upper() + note[1:]) if note else ""
        keyscale = f"{note} {m.group(2).lower()}"

    # Time signature: store the numerator only (ACE-Step expects [2/3/4/6]).
    # Prefer explicit meters, but fall back to common textual cues.
    timesig = ""
    m = re.search(r"\b(\d+)\s*/\s*(\d+)\b", text)
    if m:
        timesig = str(m.group(1))
    else:
        if re.search(r"\bfour[-\s]?on[-\s]?the[-\s]?floor\b", text, re.IGNORECASE):
            timesig = "4"
        elif re.search(r"\bwaltz\b", text, re.IGNORECASE):
            timesig = "3"
        else:
            m68 = re.search(r"\b(\d+)\s*/\s*8\b", text)
            if m68 and m68.group(1) == "6":
                timesig = "6"

    # Keep only common meters supported by ACE-Step.
    if timesig and timesig not in {"2", "3", "4", "6"}:
        timesig = ""

    # Duration: often present as "258.76 seconds" or "duration ... seconds".
    duration_s: Optional[int] = None
    dm = re.search(r"\b(?:duration(?:\s+of\s+the\s+piece\s+is)?\s+is\s+)?([0-9]+(?:\.[0-9]+)?)\s*seconds\b", text, re.IGNORECASE)
    if dm:
        try:
            duration_s = int(round(float(dm.group(1))))
        except Exception:
            duration_s = None

    # Language: return ISO codes (see acestep/constants.py: VALID_LANGUAGES)
    vlang = "unknown"
    lang_map = {
        "english": "en",
        "italian": "it",
        "spanish": "es",
        "french": "fr",
        "german": "de",
        "portuguese": "pt",
        "russian": "ru",
        "japanese": "ja",
        "korean": "ko",
        "chinese": "zh",
        "mandarin": "zh",
        "cantonese": "yue",
        "arabic": "ar",
        "hindi": "hi",
    }
    m = re.search(
        r"\b(?:in|language)\s+(English|Italian|Spanish|French|German|Portuguese|Russian|Japanese|Korean|Chinese|Mandarin|Cantonese|Arabic|Hindi)\b",
        text,
        re.IGNORECASE,
    )
    if m:
        vlang = lang_map.get(m.group(1).strip().lower(), "unknown")

    # Instrumental detection.
    instr = False
    if re.search(r"\b(instrumental|no\s+vocals|without\s+vocals)\b", text, re.IGNORECASE):
        instr = True
    # If the description explicitly talks about vocals, prefer non-instrumental.
    if re.search(r"\b(vocal|vocals|singer|singing)\b", text, re.IGNORECASE):
        instr = False

    genres = _pick_genre_from_description(desc)

    return FlamingoMeta(
        caption=desc.strip(),
        genres=genres,
        bpm=bpm,
        keyscale=keyscale,
        timesignature=timesig,
        duration_s=duration_s,
        vocal_language=vlang,
        is_instrumental=instr,
    )


class MusicFlamingoLabeler:
    """Client for the Hugging Face Space `nvidia/music-flamingo`."""

    _singleton: Optional["MusicFlamingoLabeler"] = None

    def __init__(
        self,
        space_id: str = DEFAULT_SPACE_ID,
        hf_token: Optional[str] = None,
        timeout_s: int = 600,
    ):
        if Client is None:
            raise RuntimeError(
                "gradio_client is not available. Install it with: pip install gradio-client"
            )
        self.space_id = space_id
        self.hf_token = hf_token or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        self.timeout_s = int(timeout_s)
        self._client: Optional[Client] = None
        self._endpoint: Dict[str, Any] = {}

    @classmethod
    def get(cls) -> "MusicFlamingoLabeler":
        if cls._singleton is None:
            cls._singleton = MusicFlamingoLabeler()
        return cls._singleton

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        logger.info(f"[MusicFlamingo] Connecting to Space: {self.space_id}")
        # gradio_client likes to print a big "Usage Info" block when calling view_api().
        # We suppress stdout/stderr here so button-clicks don't spam the terminal.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self._client = Client(
                self.space_id,
                token=self.hf_token,
                httpx_kwargs={"timeout": self.timeout_s},
                verbose=False,
            )
            try:
                api = self._client.view_api(return_format="dict", print_info=False)
            except TypeError:
                # Older gradio_client doesn't support print_info
                api = self._client.view_api(return_format="dict")
        self._endpoint = self._pick_infer_endpoint(api)

    @staticmethod
    def _spec_inputs(spec: Dict[str, Any]):
        """Gradio client schema differs by version: use inputs/outputs OR parameters/returns."""
        if "inputs" in spec:
            return spec.get("inputs", []) or []
        return spec.get("parameters", []) or []

    @staticmethod
    def _spec_outputs(spec: Dict[str, Any]):
        if "outputs" in spec:
            return spec.get("outputs", []) or []
        return spec.get("returns", []) or []

    def _pick_infer_endpoint(self, api_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Prefer the named endpoint '/infer' if present; otherwise use a heuristic."""
        endpoints: list[Dict[str, Any]] = []

        if isinstance(api_dict, dict):
            named = api_dict.get("named_endpoints")
            if isinstance(named, dict):
                for api_name, spec in named.items():
                    spec = dict(spec)
                    spec["api_name"] = api_name if str(api_name).startswith("/") else f"/{api_name}"
                    endpoints.append(spec)

            unnamed = api_dict.get("unnamed_endpoints")
            if isinstance(unnamed, list):
                endpoints.extend(unnamed)

        # 1) Hard-prefer '/infer' (this Space exposes it)
        for spec in endpoints:
            if str(spec.get("api_name", "")).strip().lower() == "/infer":
                logger.info("[MusicFlamingo] Discovered endpoint via api_name='/infer'")
                return spec

        # 2) Heuristic fallback
        best = None
        for spec in endpoints:
            fn_name = str(spec.get("fn_name", "")).lower()
            api_name = str(spec.get("api_name", "")).lower()
            inputs = self._spec_inputs(spec)
            outputs = self._spec_outputs(spec)
            if len(inputs) == 3 and len(outputs) >= 1:
                if "infer" in fn_name or "infer" in api_name:
                    best = spec
                    break

        if best is None:
            for spec in endpoints:
                if len(self._spec_inputs(spec)) == 3:
                    best = spec
                    break

        if best is None:
            available = [str(s.get("api_name") or s.get("fn_name") or "<?>") for s in endpoints]
            raise RuntimeError(
                "Could not discover the infer() endpoint for music-flamingo. "
                f"Available endpoints: {available}"
            )

        logger.info(
            f"[MusicFlamingo] Using endpoint: api_name={best.get('api_name')} fn_index={best.get('fn_index')}"
        )
        return best

    def _call(self, audio_path: str, prompt: str) -> str:
        self._ensure_client()
        assert self._client is not None

        api_name = self._endpoint.get("api_name")
        fn_index = self._endpoint.get("fn_index")

        # Space inputs: (audio_path, youtube_url, prompt_text). Leave youtube_url empty.
        audio_payload = handle_file(audio_path) if handle_file is not None else audio_path

        try:
            if api_name:
                out = self._client.predict(audio_payload, "", prompt, api_name=api_name)
            else:
                out = self._client.predict(audio_payload, "", prompt, fn_index=fn_index)
        except Exception as e:
            raise RuntimeError(f"music-flamingo call failed: {e}") from e

        return out if isinstance(out, str) else str(out)

    def describe_json(self, audio_path: str) -> FlamingoMeta:
        """Return best-effort structured metadata.

        The model may or may not comply with strict JSON. We try:
          1) Parse JSON
          2) Map common alias keys
          3) Fall back to a synthetic caption (or the raw text)
        """
        prompt = os.getenv("ACESTEP_MUSIC_FLAMINGO_PROMPT_DESCRIBE", DEFAULT_PROMPT_DESCRIBE_JSON)
        raw = _strip_status_prefix(self._call(audio_path, prompt))
        data = _extract_json(raw)

        if not data:
            # No JSON found: store everything as caption.
            return FlamingoMeta(caption=raw)

        caption = _first_nonempty(data, ["caption", "description", "summary", "analysis", "text"])
        genres = _first_nonempty(data, ["genres", "genre", "style", "tags"])
        bpm = _first_nonempty(data, ["bpm", "tempo", "tempo_bpm"])
        keyscale = _first_nonempty(data, ["keyscale", "key", "musical_key"])
        timesig = _first_nonempty(data, ["timesignature", "time_signature", "meter"])
        vlang = _first_nonempty(data, ["vocal_language", "language", "lang"])
        instr = _first_nonempty(data, ["is_instrumental", "instrumental", "isInstrumental"])

        # Normalize common types returned by models.
        if isinstance(genres, (list, tuple)):
            genres = ", ".join([str(x).strip() for x in genres if str(x).strip()])

        meta = FlamingoMeta(
            caption=str(caption or "").strip(),
            genres=str(genres or "").strip(),
            bpm=_coerce_int(bpm),
            keyscale=str(keyscale or "").strip(),
            timesignature=str(timesig or "").strip(),
            vocal_language=str(vlang or "unknown").strip() or "unknown",
            is_instrumental=_boolish(instr),
        )

        # If the JSON didn't provide a usable caption, synthesize one.
        if not meta.caption:
            parts = []
            if meta.genres:
                parts.append(f"Genres: {meta.genres}")
            if meta.bpm is not None:
                parts.append(f"Tempo: {meta.bpm} BPM")
            if meta.keyscale:
                parts.append(f"Key: {meta.keyscale}")
            if meta.timesignature:
                parts.append(f"TimeSig: {meta.timesignature}")
            if meta.vocal_language and meta.vocal_language != "unknown":
                parts.append(f"Language: {meta.vocal_language}")
            if parts:
                meta.caption = " | ".join(parts)
            else:
                # Last resort: store raw JSON text to avoid blank captions.
                meta.caption = raw

        return meta

    def describe_full(self, audio_path: str) -> FlamingoMeta:
        """Return the full, multi-paragraph description as caption.

        The public Space UI returns a detailed, narrative answer for the default prompt.
        For dataset authoring, it is often more useful to store that entire answer in
        `caption`, while still extracting bpm/key/etc. from the same text.
        """
        prompt = os.getenv("ACESTEP_MUSIC_FLAMINGO_PROMPT_DESCRIBE_FULL", DEFAULT_PROMPT_DESCRIBE_FULL)
        raw = _strip_status_prefix(self._call(audio_path, prompt))
        # Keep the full text in the caption field.
        meta = _parse_meta_from_full_text(raw)
        meta.caption = raw.strip()
        return meta

    def extract_lyrics(self, audio_path: str) -> str:
        prompt = os.getenv("ACESTEP_MUSIC_FLAMINGO_PROMPT_LYRICS", DEFAULT_PROMPT_LYRICS)
        raw = _strip_status_prefix(self._call(audio_path, prompt)).strip()
        if raw:
            return raw

        # Retry once with a more explicit instruction (some models occasionally return an empty string).
        retry_prompt = "Extract the lyrics. If instrumental, output exactly: [Instrumental]"
        raw2 = _strip_status_prefix(self._call(audio_path, retry_prompt)).strip()
        return raw2