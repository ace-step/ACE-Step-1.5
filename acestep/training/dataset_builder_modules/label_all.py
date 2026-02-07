from typing import List, Tuple

from .models import AudioSample


class LabelAllMixin:
    """Label all samples in the dataset."""

    def label_all_samples(
        self,
        dit_handler,
        llm_handler,
        format_lyrics: bool = False,
        transcribe_lyrics: bool = False,
        skip_metas: bool = False,
        only_unlabeled: bool = False,
        progress_callback=None,
    ) -> Tuple[List[AudioSample], str]:
        """Label all samples in the dataset."""
        if not self.samples:
            return [], "❌ No samples to label. Please scan a directory first."

        if only_unlabeled:
            samples_to_label = [
                (i, s) for i, s in enumerate(self.samples) if not s.labeled or not s.caption
            ]
        else:
            samples_to_label = [(i, s) for i, s in enumerate(self.samples)]

        if not samples_to_label:
            return self.samples, "✅ All samples already labeled"

        success_count = 0
        fail_count = 0
        total = len(samples_to_label)

        for idx, (i, sample) in enumerate(samples_to_label):
            if progress_callback:
                progress_callback(f"Labeling {idx+1}/{total}: {sample.filename}")

            _, status = self.label_sample(
                i,
                dit_handler,
                llm_handler,
                format_lyrics,
                transcribe_lyrics,
                skip_metas,
                progress_callback,
            )

            if "✅" in status:
                success_count += 1
            else:
                fail_count += 1

        status_msg = f"✅ Labeled {success_count}/{total} samples"
        if fail_count > 0:
            status_msg += f" ({fail_count} failed)"
        if only_unlabeled:
            status_msg += f" (unlabeled only, {len(self.samples)} total)"

        return self.samples, status_msg
