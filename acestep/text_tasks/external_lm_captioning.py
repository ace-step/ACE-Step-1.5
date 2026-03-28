"""Caption and metadata helpers for external LM formatting flows."""

from __future__ import annotations

from typing import Any

from loguru import logger

from .external_lm_captioning_fallback_locale import build_localized_fallback_caption

_FILTERED_METADATA_SENTINELS = {"", "unknown", "none", "n/a", "default"}


def normalized_caption(text: str) -> str:
    """Return a normalized caption string for retry and equality checks."""

    return " ".join((text or "").strip().lower().split())


def caption_needs_retry(*, original_caption: str, generated_caption: str) -> bool:
    """Return whether the generated caption looks like a non-enhanced echo."""

    normalized_original = normalized_caption(original_caption)
    normalized_generated = normalized_caption(generated_caption)
    if not normalized_generated:
        return True
    if normalized_generated == normalized_original:
        return True
    return len(normalized_generated.split()) < max(6, len(normalized_original.split()) + 3)


def apply_user_metadata_overrides(*, plan: Any, user_metadata: dict[str, Any]) -> Any:
    """Preserve user-supplied metadata over any parsed provider drift."""

    user_metadata = user_metadata or {}
    if not user_metadata:
        return plan
    if user_metadata.get("bpm") not in (None, ""):
        try:
            plan.bpm = int(float(user_metadata["bpm"]))
        except (TypeError, ValueError) as exc:
            logger.debug("Ignoring invalid external LM bpm override {!r}: {}", user_metadata["bpm"], exc)
    if user_metadata.get("duration") not in (None, ""):
        try:
            plan.duration = float(user_metadata["duration"])
        except (TypeError, ValueError) as exc:
            logger.debug(
                "Ignoring invalid external LM duration override {!r}: {}",
                user_metadata["duration"],
                exc,
            )
    if user_metadata.get("keyscale"):
        keyscale = str(user_metadata["keyscale"]).strip()
        plan.keyscale = keyscale
        plan.key_scale = keyscale
    if user_metadata.get("timesignature"):
        timesignature = str(user_metadata["timesignature"]).strip()
        plan.timesignature = timesignature
        plan.time_signature = timesignature
    if user_metadata.get("language"):
        language = str(user_metadata["language"]).strip()
        plan.language = language
        plan.vocal_language = language
    return plan


def build_fallback_caption(*, caption: str, user_metadata: dict[str, Any]) -> str:
    """Return the local retry fallback built from the user's caption and metadata.

    This path is used when the external provider returns an empty, unchanged, or still-too-short
    caption after one retry attempt, so format mode remains usable without silently echoing the
    original input back as the enhanced caption.
    """

    return build_localized_fallback_caption(caption=caption, user_metadata=user_metadata or {})


def build_format_request_intent(
    *,
    caption: str,
    lyrics: str,
    user_metadata: dict[str, Any],
) -> str:
    """Build the format-mode user intent string for external provider requests."""

    user_metadata = user_metadata or {}
    intent_parts = [
        "Please format and enrich the following for ACE-Step generation.",
        f"Caption: {caption or ''}",
        f"Lyrics: {lyrics or ''}",
    ]
    for key in ("bpm", "duration", "keyscale", "timesignature", "language"):
        value = user_metadata.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.lower() in _FILTERED_METADATA_SENTINELS:
                continue
            intent_parts.append(f"{key}: {normalized}")
            continue
        if value is not None:
            intent_parts.append(f"{key}: {value}")
    return "\n".join(intent_parts)
