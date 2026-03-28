"""Localized fallback-caption text for external LM formatting helpers."""

from __future__ import annotations

from typing import Any

_FALLBACK_TEMPLATES = {
    "en": {
        "default_source": "music piece",
        "intro": (
            "{source} unfolds as a fuller arranged track with a clear intro, developing verses,"
        ),
        "arrangement": "a stronger chorus or drop, and a shaped outro that resolves the energy naturally.",
        "bpm": "The groove stays anchored around {bpm} BPM.",
        "timesignature": "The arrangement holds a {timesignature} pulse throughout.",
        "keyscale": "The harmony centers on {keyscale}.",
        "duration": "The structure is paced for roughly {duration} seconds.",
        "mix": "The mix should grow from a more focused opening into a fuller, more energetic peak before easing out.",
    },
    "he": {
        "default_source": "הקטע הזה",
        "intro": "{source} נפרש לרצועה מעובדת ומלאה יותר, עם פתיחה ברורה ובתים שמתפתחים,",
        "arrangement": "פזמון או דרופ חזקים יותר, ואאוטרו שסוגר את האנרגיה באופן טבעי.",
        "bpm": "הגרוב נשאר מעוגן סביב {bpm} BPM.",
        "timesignature": "העיבוד שומר על דופק של {timesignature} לאורך כל הדרך.",
        "keyscale": "ההרמוניה מתמקדת ב-{keyscale}.",
        "duration": "המבנה מתוכנן לאורך של כ-{duration} שניות.",
        "mix": "המיקס צריך לצמוח מפתיחה ממוקדת יותר אל שיא מלא ואנרגטי יותר לפני שהוא נרגע.",
    },
    "ja": {
        "default_source": "この楽曲",
        "intro": "{source}は、明確なイントロから展開するヴァースへ進み、",
        "arrangement": "より力強いサビまたはドロップと、自然に熱量を着地させるアウトロを備えた、より構成的な楽曲として広がっていく。",
        "bpm": "{bpm} BPM前後のグルーヴで全体を支える。",
        "timesignature": "全体は{timesignature}の拍子感を保つ。",
        "keyscale": "和声の中心は{keyscale}。",
        "duration": "全体の尺はおよそ{duration}秒を想定する。",
        "mix": "ミックスは引き締まった導入から始まり、より厚く高揚したピークへ向かって広がり、最後は自然に落ち着く。",
    },
    "zh": {
        "default_source": "这首作品",
        "intro": "{source}会展开为一首编排更完整的作品，具有清晰的前奏和逐步发展的主歌，",
        "arrangement": "更强的副歌或 drop，以及自然收束能量的结尾。",
        "bpm": "律动大致稳定在 {bpm} BPM。",
        "timesignature": "整体保持 {timesignature} 拍的律动。",
        "keyscale": "和声中心围绕 {keyscale} 展开。",
        "duration": "整体结构按大约 {duration} 秒来铺陈。",
        "mix": "混音应从较克制的开场逐步发展到更饱满、更有能量的峰值，再自然收束。",
    },
}


def build_localized_fallback_caption(*, caption: str, user_metadata: dict[str, Any]) -> str:
    """Return localized fallback caption prose for supported language codes."""

    template = _FALLBACK_TEMPLATES[_resolve_fallback_language(user_metadata)]
    source = (caption or "").strip().rstrip(".") or template["default_source"]
    parts = [template["intro"].format(source=source), template["arrangement"]]

    bpm = user_metadata.get("bpm")
    duration = user_metadata.get("duration")
    keyscale = user_metadata.get("keyscale")
    timesignature = user_metadata.get("timesignature")
    if bpm not in (None, ""):
        parts.append(template["bpm"].format(bpm=bpm))
    if timesignature:
        parts.append(template["timesignature"].format(timesignature=timesignature))
    if keyscale:
        parts.append(template["keyscale"].format(keyscale=keyscale))
    if duration not in (None, ""):
        parts.append(template["duration"].format(duration=duration))
    parts.append(template["mix"])
    return " ".join(parts)


def _resolve_fallback_language(user_metadata: dict[str, Any]) -> str:
    """Return the supported fallback-caption language key for user metadata."""

    raw_language = str(
        user_metadata.get("language") or user_metadata.get("vocal_language") or ""
    ).strip().lower()
    normalized_language = raw_language.replace("_", "-")
    if normalized_language.startswith("ja"):
        return "ja"
    if normalized_language.startswith("zh"):
        return "zh"
    if normalized_language.startswith("he") or normalized_language.startswith("iw"):
        return "he"
    return "en"
