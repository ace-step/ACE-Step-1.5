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
    ) -> Tuple[AudioSample, str]:
        """Label a single sample using the LLM."""
        if sample_idx < 0 or sample_idx >= len(self.samples):
            return None, f"❌ Invalid sample index: {sample_idx}"

        sample = self.samples[sample_idx]

        has_preloaded_lyrics = sample.has_raw_lyrics() and not sample.is_instrumental
        has_csv_bpm = sample.bpm is not None
        has_csv_key = bool(sample.keyscale)

        try:
            if progress_callback:
                progress_callback(f"Processing: {sample.filename}")

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
