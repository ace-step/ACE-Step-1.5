import os
from typing import Optional, Tuple

from loguru import logger

from .label_utils import get_audio_codes, parse_int
from .models import AudioSample


class LabelSingleMixin:
    """Label a single sample."""

    def label_sample(
        self,
        sample_idx: int,
        dit_handler,
        llm_handler,
        format_lyrics: bool = False,
        transcribe_lyrics: bool = False,
        skip_metas: bool = False,
        progress_callback=None,
        provider_override: Optional[str] = None,
    ) -> Tuple[AudioSample, str]:
        """Label a single sample using the LLM."""
        if sample_idx < 0 or sample_idx >= len(self.samples):
            return None, f"❌ Invalid sample index: {sample_idx}"

        sample = self.samples[sample_idx]

        has_preloaded_lyrics = sample.has_raw_lyrics() and not sample.is_instrumental
        has_csv_bpm = sample.bpm is not None
        has_csv_key = bool(sample.keyscale)

        provider = (provider_override or os.getenv("ACESTEP_AUTOLABEL_PROVIDER", "local")).strip().lower()
        use_music_flamingo = provider in {"music-flamingo", "music_flamingo", "flamingo", "nvidia"}

        try:
            if progress_callback:
                progress_callback(f"Processing: {sample.filename}")

            # ===== Provider: Music-Flamingo (online) =====
            if use_music_flamingo:
                if progress_callback:
                    progress_callback(f"Labeling with Music-Flamingo: {sample.filename}")

                from acestep.training.music_flamingo_autolabel import MusicFlamingoLabeler
                from acestep.constants import (
                    BPM_MIN,
                    BPM_MAX,
                    DURATION_MIN,
                    DURATION_MAX,
                    VALID_KEYSCALES,
                    VALID_TIME_SIGNATURES,
                    VALID_LANGUAGES,
                )
                from acestep.training.music_flamingo_autolabel import detect_language_from_lyrics

                mf = MusicFlamingoLabeler.get()
                # Use a compact track-card prompt for the Space.
                # This produces a single-paragraph caption suitable for training.
                meta = mf.describe_full(sample.audio_path)

                if meta.caption:
                    sample.caption = meta.caption
                if meta.genres:
                    sample.genre = meta.genres

                if not skip_metas:
                    if not has_csv_bpm and meta.bpm is not None and BPM_MIN <= meta.bpm <= BPM_MAX:
                        sample.bpm = meta.bpm
                    if not has_csv_key and meta.keyscale and meta.keyscale in VALID_KEYSCALES:
                        sample.keyscale = meta.keyscale
                    if meta.timesignature:
                        try:
                            ts = int(str(meta.timesignature).strip())
                        except Exception:
                            ts = None
                        if ts in VALID_TIME_SIGNATURES:
                            sample.timesignature = str(ts)

                    # Duration is already computed when loading audio, but if Music-Flamingo
                    # provides it, keep it consistent (within supported range).
                    if meta.duration_s is not None:
                        d = int(meta.duration_s)
                        if DURATION_MIN <= d <= DURATION_MAX:
                            sample.duration = d

                sample.language = (meta.vocal_language or "unknown").strip() or "unknown"
                if sample.language not in VALID_LANGUAGES:
                    sample.language = "unknown"

                # Lyrics behavior:
                # - If instrumental: force [Instrumental]
                # - If transcribe_lyrics: always extract from audio via Music-Flamingo
                # - Else: prefer raw lyrics if present, otherwise extract from audio
                if sample.is_instrumental or meta.is_instrumental:
                    sample.is_instrumental = True
                    sample.lyrics = "[Instrumental]"
                    sample.formatted_lyrics = ""
                    status_suffix = "(music-flamingo, instrumental)"
                else:
                    if transcribe_lyrics or not has_preloaded_lyrics:
                        lyrics = mf.extract_lyrics(sample.audio_path)
                        sample.lyrics = lyrics
                        sample.formatted_lyrics = lyrics
                        status_suffix = "(music-flamingo, lyrics extracted)"
                    else:
                        sample.lyrics = sample.raw_lyrics
                        sample.formatted_lyrics = ""
                        status_suffix = "(music-flamingo, using raw lyrics)"

                # If we have real lyrics but language is still unknown, infer from lyrics text.
                if (
                    sample.language == "unknown"
                    and not sample.is_instrumental
                    and sample.lyrics
                    and sample.lyrics.strip()
                    and sample.lyrics.strip().lower() != "[instrumental]"
                ):
                    inferred = detect_language_from_lyrics(sample.lyrics)
                    if inferred in VALID_LANGUAGES:
                        sample.language = inferred

                sample.labeled = True
                self.samples[sample_idx] = sample

                status_msg = f"✅ Labeled: {sample.filename}"
                if skip_metas:
                    status_msg += " (skip metas)"
                if status_suffix:
                    status_msg += f" {status_suffix}"
                return sample, status_msg

            # ===== Provider: Local LM (default) =====
            audio_codes = get_audio_codes(sample.audio_path, dit_handler)

            if not audio_codes:
                return sample, f"❌ Failed to encode audio: {sample.filename}"

            if progress_callback:
                progress_callback(f"Generating metadata for: {sample.filename}")

            if format_lyrics and has_preloaded_lyrics:
                from acestep.inference import format_sample

                result = format_sample(
                    llm_handler=llm_handler,
                    caption="",
                    lyrics=sample.raw_lyrics,
                    user_metadata=None,
                    temperature=0.85,
                    use_constrained_decoding=True,
                )

                if not result.success:
                    return sample, f"❌ LLM format failed: {result.error}"

                sample.caption = result.caption or ""
                if not skip_metas:
                    if not has_csv_bpm:
                        sample.bpm = result.bpm
                    if not has_csv_key:
                        sample.keyscale = result.keyscale or ""
                    sample.timesignature = result.timesignature or ""
                sample.language = result.language or "unknown"
                sample.formatted_lyrics = result.lyrics or ""
                sample.lyrics = sample.formatted_lyrics if sample.formatted_lyrics else sample.raw_lyrics

                status_suffix = "(lyrics formatted by LM)"

            else:
                metadata, status = llm_handler.understand_audio_from_codes(
                    audio_codes=audio_codes,
                    temperature=0.7,
                    use_constrained_decoding=True,
                )

                if not metadata:
                    return sample, f"❌ LLM labeling failed: {status}"

                sample.caption = metadata.get("caption", "")
                sample.genre = metadata.get("genres", "")

                if not skip_metas:
                    if not has_csv_bpm:
                        sample.bpm = parse_int(metadata.get("bpm"))
                    if not has_csv_key:
                        sample.keyscale = metadata.get("keyscale", "")
                    sample.timesignature = metadata.get("timesignature", "")

                sample.language = metadata.get("vocal_language", "unknown")

                llm_lyrics = metadata.get("lyrics", "")

                if sample.is_instrumental:
                    sample.lyrics = "[Instrumental]"
                    sample.language = "unknown"
                    sample.formatted_lyrics = ""
                    status_suffix = "(instrumental)"
                elif transcribe_lyrics:
                    sample.formatted_lyrics = llm_lyrics
                    sample.lyrics = llm_lyrics
                    status_suffix = "(lyrics transcribed by LM)"
                elif has_preloaded_lyrics:
                    sample.lyrics = sample.raw_lyrics
                    sample.formatted_lyrics = ""
                    status_suffix = "(using raw lyrics)"
                else:
                    sample.lyrics = llm_lyrics
                    sample.formatted_lyrics = llm_lyrics
                    status_suffix = ""

            sample.labeled = True
            self.samples[sample_idx] = sample

            status_msg = f"✅ Labeled: {sample.filename}"
            if skip_metas:
                status_msg += " (skip metas)"
            if status_suffix:
                status_msg += f" {status_suffix}"

            return sample, status_msg

        except Exception as e:
            logger.exception(f"Error labeling sample {sample.filename}")
            return sample, f"❌ Error: {str(e)}"
