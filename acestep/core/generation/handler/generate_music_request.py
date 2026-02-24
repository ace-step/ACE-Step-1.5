"""Input and preflight helpers for ``generate_music`` orchestration."""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import torch
from loguru import logger

from acestep.constants import TASK_INSTRUCTIONS


class GenerateMusicRequestMixin:
    """Prepare normalized ``generate_music`` inputs before service execution."""

    def _resolve_generate_music_progress(
        self,
        progress: Optional[Callable[..., Any]],
    ) -> Callable[..., Any]:
        """Return a callable progress callback, defaulting to no-op."""
        if progress is not None:
            return progress

        def _progress(*args: Any, **kwargs: Any) -> Any:
            """No-op callback for non-UI call sites."""
            _ = args, kwargs
            return None

        return _progress

    def _validate_generate_music_readiness(self) -> Optional[Dict[str, Any]]:
        """Return standardized error payload when model components are unavailable."""
        if self.model is None or self.vae is None or self.text_tokenizer is None or self.text_encoder is None:
            return {
                "audios": [],
                "status_message": "\u274c Model not fully initialized. Please initialize all components first.",
                "extra_outputs": {},
                "success": False,
                "error": "Model not fully initialized",
            }
        return None

    def _has_non_empty_audio_codes(self, value: Union[str, List[str]]) -> bool:
        """Return ``True`` when at least one non-empty audio-code string is present."""
        if isinstance(value, list):
            return any((x or "").strip() for x in value)
        return bool(value and str(value).strip())

    def _resolve_generate_music_task(
        self,
        task_type: str,
        audio_code_string: Union[str, List[str]],
        instruction: str,
    ) -> Tuple[str, str]:
        """Auto-switch text2music to cover task when audio codes are provided."""
        if task_type == "text2music" and self._has_non_empty_audio_codes(audio_code_string):
            return "cover", TASK_INSTRUCTIONS["cover"]
        return task_type, instruction

    def _prepare_generate_music_runtime(
        self,
        batch_size: Optional[int],
        audio_duration: Optional[float],
        repainting_end: Optional[float],
        seed: Optional[Union[str, float, int]],
        use_random_seed: bool,
    ) -> Dict[str, Any]:
        """Prepare runtime batch/seed/duration values for generation."""
        self.current_offload_cost = 0.0
        actual_batch_size = batch_size if batch_size is not None else self.batch_size
        actual_batch_size = max(1, actual_batch_size)
        actual_batch_size = self._vram_guard_reduce_batch(actual_batch_size, audio_duration=audio_duration)
        actual_seed_list, seed_value_for_ui = self.prepare_seeds(actual_batch_size, seed, use_random_seed)

        if audio_duration is not None and float(audio_duration) <= 0:
            audio_duration = None
        if repainting_end is not None and float(repainting_end) < 0:
            repainting_end = None

        return {
            "actual_batch_size": actual_batch_size,
            "actual_seed_list": actual_seed_list,
            "seed_value_for_ui": seed_value_for_ui,
            "audio_duration": audio_duration,
            "repainting_end": repainting_end,
        }

    def _prepare_reference_and_source_audio(
        self,
        reference_audio: Optional[str],
        src_audio: Optional[str],
        audio_code_string: Union[str, List[str]],
        actual_batch_size: int,
        task_type: str,
    ) -> Tuple[Optional[List[List[torch.Tensor]]], Optional[torch.Tensor], Optional[Dict[str, Any]]]:
        """Prepare reference/source audio tensors and return early error payload when invalid."""
        if reference_audio is not None:
            logger.info("[generate_music] Processing reference audio...")
            processed_ref_audio = self.process_reference_audio(reference_audio)
            if processed_ref_audio is None:
                return None, None, {
                    "audios": [],
                    "status_message": (
                        "Reference audio is invalid, unreadable, or silent. "
                        "Please upload a valid audible audio file."
                    ),
                    "extra_outputs": {},
                    "success": False,
                    "error": "Invalid reference audio",
                }
            refer_audios = [[processed_ref_audio] for _ in range(actual_batch_size)]
        else:
            refer_audios = [[torch.zeros(2, 30 * self.sample_rate)] for _ in range(actual_batch_size)]

        processed_src_audio = None
        if task_type == "text2music":
            if src_audio is not None:
                logger.info("[generate_music] text2music task does not use src_audio, ignoring")
        elif src_audio is not None:
            if self._has_non_empty_audio_codes(audio_code_string):
                logger.info("[generate_music] Audio codes provided, ignoring src_audio and using codes instead")
            else:
                logger.info("[generate_music] Processing source audio...")
                processed_src_audio = self.process_src_audio(src_audio)
                if processed_src_audio is None:
                    logger.error("[generate_music] Source audio is invalid after processing")
                    return None, None, {
                        "audios": [],
                        "status_message": (
                            "Source audio is invalid, unreadable, or silent. "
                            "Please upload a valid audible audio file."
                        ),
                        "extra_outputs": {},
                        "success": False,
                        "error": "Invalid source audio",
                    }

        return refer_audios, processed_src_audio, None

    def _prepare_generate_music_service_inputs(
        self,
        actual_batch_size: int,
        processed_src_audio: Optional[torch.Tensor],
        audio_duration: Optional[float],
        captions: str,
        lyrics: str,
        vocal_language: str,
        instruction: str,
        bpm: Optional[int],
        key_scale: str,
        time_signature: str,
        task_type: str,
        audio_code_string: Union[str, List[str]],
        repainting_start: float,
        repainting_end: Optional[float],
    ) -> Dict[str, Any]:
        """Prepare service inputs (batch text, repaint spans, and optional code hints)."""
        captions_batch, instructions_batch, lyrics_batch, vocal_languages_batch, metas_batch = self.prepare_batch_data(
            actual_batch_size,
            processed_src_audio,
            audio_duration,
            captions,
            lyrics,
            vocal_language,
            instruction,
            bpm,
            key_scale,
            time_signature,
        )

        is_repaint_task, is_lego_task, is_cover_task, can_use_repainting = self.determine_task_type(task_type, audio_code_string)
        repainting_start_batch, repainting_end_batch, target_wavs_tensor = self.prepare_padding_info(
            actual_batch_size,
            processed_src_audio,
            audio_duration,
            repainting_start,
            repainting_end,
            is_repaint_task,
            is_lego_task,
            is_cover_task,
            can_use_repainting,
        )
        audio_code_hints_batch = None
        if self._has_non_empty_audio_codes(audio_code_string):
            if isinstance(audio_code_string, list):
                audio_code_hints_batch = audio_code_string
            else:
                audio_code_hints_batch = [audio_code_string] * actual_batch_size

        return {
            "captions_batch": captions_batch,
            "instructions_batch": instructions_batch,
            "lyrics_batch": lyrics_batch,
            "vocal_languages_batch": vocal_languages_batch,
            "metas_batch": metas_batch,
            "repainting_start_batch": repainting_start_batch,
            "repainting_end_batch": repainting_end_batch,
            "target_wavs_tensor": target_wavs_tensor,
            "audio_code_hints_batch": audio_code_hints_batch,
            "should_return_intermediate": task_type == "text2music",
        }

