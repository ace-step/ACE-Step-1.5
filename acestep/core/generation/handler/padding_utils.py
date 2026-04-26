"""Padding helpers for handler batch preparation."""

import torch
from loguru import logger


class PaddingMixin:
    """Mixin containing repaint/lego padding helpers.

    Depends on host members:
    - Method: ``create_target_wavs`` (provided by ``TaskUtilsMixin`` in this decomposition).
    """

    def prepare_padding_info(
        self,
        actual_batch_size,
        processed_src_audio,
        audio_duration,
        repainting_start,
        repainting_end,
        is_repaint_task,
        is_lego_task,
        is_cover_task,
        can_use_repainting,
    ):
        """Prepare padded target wavs and repaint coordinates for each batch item."""
        try:
            target_wavs_batch = []
            # Store padding info for each batch item to adjust repainting coordinates
            padding_info_batch = []
            for i in range(actual_batch_size):
                if processed_src_audio is not None:
                    if is_cover_task:
                        # Cover task: Use src_audio directly without padding
                        batch_target_wavs = processed_src_audio
                        padding_info_batch.append({"left_padding_duration": 0.0, "right_padding_duration": 0.0})
                    elif is_repaint_task or is_lego_task:
                        # Repaint/lego task: May need padding for outpainting
                        src_audio_duration = processed_src_audio.shape[-1] / 48000.0

                        # Determine actual end time
                        if repainting_end is None or repainting_end < 0:
                            actual_end = src_audio_duration
                        else:
                            actual_end = repainting_end

                        left_padding_duration = max(0, -repainting_start) if repainting_start is not None else 0
                        right_padding_duration = max(0, actual_end - src_audio_duration)

                        # Create padded audio
                        left_padding_frames = int(left_padding_duration * 48000)
                        right_padding_frames = int(right_padding_duration * 48000)

                        if left_padding_frames > 0 or right_padding_frames > 0:
                            # Pad the src audio
                            batch_target_wavs = torch.nn.functional.pad(
                                processed_src_audio, (left_padding_frames, right_padding_frames), "constant", 0
                            )
                        else:
                            batch_target_wavs = processed_src_audio

                        # Store padding info for coordinate adjustment
                        padding_info_batch.append(
                            {
                                "left_padding_duration": left_padding_duration,
                                "right_padding_duration": right_padding_duration,
                            }
                        )
                    else:
                        # Other tasks: Use src_audio directly without padding
                        batch_target_wavs = processed_src_audio
                        padding_info_batch.append({"left_padding_duration": 0.0, "right_padding_duration": 0.0})
                else:
                    padding_info_batch.append({"left_padding_duration": 0.0, "right_padding_duration": 0.0})
                    if audio_duration is not None and float(audio_duration) > 0:
                        batch_target_wavs = self.create_target_wavs(float(audio_duration))
                    else:
                        # Fall back to a sensible default instead of a random duration.
                        # Random durations caused garbage output when duration=-1 was
                        # passed without LM auto-detection (see issue #929).
                        fallback_duration = 120.0
                        logger.warning(
                            "[padding] No valid audio_duration provided (got {}); "
                            "using fallback duration {:.0f}s.",
                            audio_duration,
                            fallback_duration,
                        )
                        batch_target_wavs = self.create_target_wavs(fallback_duration)
                target_wavs_batch.append(batch_target_wavs)

            # Stack target_wavs into batch tensor
            # Ensure all tensors have the same shape by padding to max length
            max_frames = max(wav.shape[-1] for wav in target_wavs_batch)
            padded_target_wavs = []
            for wav in target_wavs_batch:
                if wav.shape[-1] < max_frames:
                    pad_frames = max_frames - wav.shape[-1]
                    padded_wav = torch.nn.functional.pad(wav, (0, pad_frames), "constant", 0)
                    padded_target_wavs.append(padded_wav)
                else:
                    padded_target_wavs.append(wav)

            target_wavs_tensor = torch.stack(padded_target_wavs, dim=0)  # [batch_size, 2, frames]

            if can_use_repainting:
                # Repaint task: Set repainting parameters
                if repainting_start is None:
                    repainting_start_batch = None
                elif isinstance(repainting_start, (int, float)):
                    if processed_src_audio is not None:
                        adjusted_start = repainting_start + padding_info_batch[0]["left_padding_duration"]
                        repainting_start_batch = [adjusted_start] * actual_batch_size
                    else:
                        repainting_start_batch = [repainting_start] * actual_batch_size
                else:
                    # List input - adjust each item
                    repainting_start_batch = []
                    for i in range(actual_batch_size):
                        if processed_src_audio is not None:
                            adjusted_start = repainting_start[i] + padding_info_batch[i]["left_padding_duration"]
                            repainting_start_batch.append(adjusted_start)
                        else:
                            repainting_start_batch.append(repainting_start[i])

                # Handle repainting_end - use src audio duration if not specified or negative
                if processed_src_audio is not None:
                    # If src audio is provided, use its duration as default end
                    src_audio_duration = processed_src_audio.shape[-1] / 48000.0
                    if repainting_end is None or repainting_end < 0:
                        # Use src audio duration (before padding), then adjust for padding
                        adjusted_end = src_audio_duration + padding_info_batch[0]["left_padding_duration"]
                        repainting_end_batch = [adjusted_end] * actual_batch_size
                    else:
                        # Adjust repainting_end to be relative to padded audio
                        adjusted_end = repainting_end + padding_info_batch[0]["left_padding_duration"]
                        repainting_end_batch = [adjusted_end] * actual_batch_size
                else:
                    # No src audio - repainting doesn't make sense without it
                    if repainting_end is None or repainting_end < 0:
                        repainting_end_batch = None
                    elif isinstance(repainting_end, (int, float)):
                        repainting_end_batch = [repainting_end] * actual_batch_size
                    else:
                        # List input - adjust each item
                        repainting_end_batch = []
                        for i in range(actual_batch_size):
                            repainting_end_batch.append(repainting_end[i])
            else:
                # All other tasks (cover, text2music, extract, complete): No repainting
                # Only repaint and lego tasks should have repainting parameters
                repainting_start_batch = None
                repainting_end_batch = None

            return repainting_start_batch, repainting_end_batch, target_wavs_tensor
        except (TypeError, ValueError, RuntimeError, IndexError):
            logger.exception("[prepare_padding_info] Error preparing padding information")
            fallback = torch.stack([self.create_target_wavs(30.0) for _ in range(actual_batch_size)], dim=0)
            return None, None, fallback
