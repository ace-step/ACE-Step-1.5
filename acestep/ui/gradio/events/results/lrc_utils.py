"""LRC parsing, VTT conversion, subtitle updates, and LRC file I/O.

Handles all LRC/VTT subtitle processing for the results UI including
parsing, merging short lines, generating VTT files, and the on-demand
LRC generation handler.
"""
import os
import re
import datetime
import tempfile
import time as time_module
from typing import Dict, Any, Optional, List

import gradio as gr
from loguru import logger

from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.events.results.generation_info import DEFAULT_RESULTS_DIR


def parse_lrc_to_subtitles(lrc_text: str, total_duration: Optional[float] = None) -> List[Dict[str, Any]]:
    """Parse LRC lyrics text to Gradio subtitles format with smart post-processing.

    Merges lines that start very close to each other so they don't disappear
    too quickly in the subtitle display.

    Args:
        lrc_text: LRC format lyrics string.
        total_duration: Total audio duration in seconds.

    Returns:
        List of subtitle dictionaries with 'text' and 'timestamp' keys.
    """
    if not lrc_text or not lrc_text.strip():
        return []

    timestamp_pattern = r'\[(\d{2}):(\d{2})\.(\d{2,3})\]'
    raw_entries = []

    for line in lrc_text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        timestamps = re.findall(timestamp_pattern, line)
        if not timestamps:
            continue
        text = re.sub(timestamp_pattern, '', line).strip()
        if not text:
            continue

        start_minutes, start_seconds, start_cs = timestamps[0]
        cs = int(start_cs)
        start_time = (
            int(start_minutes) * 60 + int(start_seconds)
            + (cs / 100.0 if len(start_cs) == 2 else cs / 1000.0)
        )

        end_time = None
        if len(timestamps) >= 2:
            end_min, end_sec, end_cs_str = timestamps[1]
            cs_end = int(end_cs_str)
            end_time = (
                int(end_min) * 60 + int(end_sec)
                + (cs_end / 100.0 if len(end_cs_str) == 2 else cs_end / 1000.0)
            )

        raw_entries.append({'start': start_time, 'explicit_end': end_time, 'text': text})

    raw_entries.sort(key=lambda x: x['start'])
    if not raw_entries:
        return []

    # Merge lines closer than MIN_DISPLAY_DURATION seconds
    MIN_DISPLAY_DURATION = 2.0
    merged_entries: list = []
    i = 0
    while i < len(raw_entries):
        cur = raw_entries[i]
        combined_text = cur['text']
        combined_start = cur['start']
        combined_explicit_end = cur['explicit_end']
        next_idx = i + 1

        while next_idx < len(raw_entries):
            nxt = raw_entries[next_idx]
            if nxt['start'] - combined_start < MIN_DISPLAY_DURATION:
                combined_text += "\n" + nxt['text']
                if nxt['explicit_end']:
                    combined_explicit_end = nxt['explicit_end']
                next_idx += 1
            else:
                break

        merged_entries.append({
            'start': combined_start,
            'explicit_end': combined_explicit_end,
            'text': combined_text,
        })
        i = next_idx

    # Build final subtitles list
    subtitles = []
    for idx, entry in enumerate(merged_entries):
        start = entry['start']
        if entry['explicit_end'] is not None:
            end = entry['explicit_end']
        elif idx + 1 < len(merged_entries):
            end = merged_entries[idx + 1]['start']
        elif total_duration is not None and total_duration > start:
            end = total_duration
        else:
            end = start + 5.0
        if end <= start:
            end = start + 3.0
        subtitles.append({'text': entry['text'], 'timestamp': [start, end]})

    return subtitles


def _format_vtt_timestamp(seconds: float) -> str:
    """Format seconds to VTT timestamp ``HH:MM:SS.mmm``."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def lrc_to_vtt_file(lrc_text: str, total_duration: float = None) -> Optional[str]:
    """Convert LRC text to a VTT subtitle file and return its path.

    Args:
        lrc_text: LRC format lyrics string.
        total_duration: Total audio duration in seconds.

    Returns:
        Path to the generated VTT file, or ``None`` on failure.
    """
    if not lrc_text or not lrc_text.strip():
        return None
    subtitles = parse_lrc_to_subtitles(lrc_text, total_duration=total_duration)
    if not subtitles:
        return None

    vtt_lines = ["WEBVTT", ""]
    for i, sub in enumerate(subtitles):
        vtt_lines.append(str(i + 1))
        vtt_lines.append(
            f"{_format_vtt_timestamp(sub['timestamp'][0])} --> {_format_vtt_timestamp(sub['timestamp'][1])}"
        )
        vtt_lines.append(sub['text'])
        vtt_lines.append("")

    try:
        vtt_output_dir = os.path.join(DEFAULT_RESULTS_DIR, "subtitles")
        os.makedirs(vtt_output_dir, exist_ok=True)
        ts = int(time_module.time())
        vtt_filename = f"subtitles_{ts}_{datetime.datetime.now().strftime('%H%M%S')}.vtt"
        vtt_path = os.path.join(vtt_output_dir, vtt_filename).replace("\\", "/")
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(vtt_lines))
        return vtt_path
    except Exception as e:
        logger.error(f"[lrc_to_vtt_file] Failed to create VTT file: {e}")
        return None


def update_audio_subtitles_from_lrc(lrc_text: str, audio_duration: float = None):
    """Update Audio component subtitles from LRC text via a VTT file.

    Args:
        lrc_text: LRC format lyrics string.
        audio_duration: Optional audio duration for last-line end time.

    Returns:
        ``gr.update`` with the subtitles path (or ``None`` to clear).
    """
    if not lrc_text or not lrc_text.strip():
        return gr.update(subtitles=None)
    vtt_path = lrc_to_vtt_file(lrc_text, total_duration=audio_duration)
    return gr.update(subtitles=vtt_path)


def save_lrc_to_file(lrc_text):
    """Save LRC text to a downloadable ``.lrc`` file.

    Args:
        lrc_text: The LRC text content to save.

    Returns:
        ``gr.update`` for the File component with the ``.lrc`` file path.
    """
    if not lrc_text or not lrc_text.strip():
        gr.Warning("No LRC content to save.")
        return gr.skip()
    try:
        tmp_dir = tempfile.mkdtemp()
        lrc_path = os.path.join(tmp_dir, "lyrics.lrc")
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lrc_text)
        gr.Info("LRC file ready for download.")
        return gr.update(value=lrc_path, visible=True)
    except Exception as e:
        gr.Warning(f"Error saving LRC file: {e}")
        return gr.skip()


def generate_lrc_handler(dit_handler, sample_idx, current_batch_index, batch_queue, vocal_language, inference_steps):
    """Generate LRC timestamps for a specific audio sample.

    Retrieves cached generation data from *batch_queue* and calls the
    handler's ``get_lyric_timestamp`` method.  Only updates ``lrc_display``;
    audio subtitles are refreshed via a separate ``.change()`` event.

    Args:
        dit_handler: DiT handler instance.
        sample_idx: 1-based sample index (1-8).
        current_batch_index: Current batch index in *batch_queue*.
        batch_queue: Dictionary storing all batch generation data.
        vocal_language: Language code for lyrics.
        inference_steps: Number of inference steps used.

    Returns:
        Tuple of ``(lrc_display_update, details_accordion_update, batch_queue)``.
    """
    import torch  # noqa: F401 – kept for tensor slicing

    if current_batch_index not in batch_queue:
        return gr.skip(), gr.skip(), batch_queue

    batch_data = batch_queue[current_batch_index]
    extra_outputs = batch_data.get("extra_outputs", {})

    if not extra_outputs:
        return gr.update(value=t("messages.lrc_no_extra_outputs"), visible=True), gr.skip(), batch_queue

    pred_latents = extra_outputs.get("pred_latents")
    encoder_hidden_states = extra_outputs.get("encoder_hidden_states")
    encoder_attention_mask = extra_outputs.get("encoder_attention_mask")
    context_latents = extra_outputs.get("context_latents")
    lyric_token_idss = extra_outputs.get("lyric_token_idss")

    if any(x is None for x in [pred_latents, encoder_hidden_states, encoder_attention_mask, context_latents, lyric_token_idss]):
        return gr.update(value=t("messages.lrc_missing_tensors"), visible=True), gr.skip(), batch_queue

    idx0 = sample_idx - 1
    if idx0 >= pred_latents.shape[0]:
        return gr.update(value=t("messages.lrc_sample_not_exist"), visible=True), gr.skip(), batch_queue

    try:
        params = batch_data.get("generation_params", {})
        audio_duration = params.get("audio_duration", -1)
        if audio_duration is None or audio_duration <= 0:
            audio_duration = pred_latents.shape[1] / 25.0

        result = dit_handler.get_lyric_timestamp(
            pred_latent=pred_latents[idx0:idx0 + 1],
            encoder_hidden_states=encoder_hidden_states[idx0:idx0 + 1],
            encoder_attention_mask=encoder_attention_mask[idx0:idx0 + 1],
            context_latents=context_latents[idx0:idx0 + 1],
            lyric_token_ids=lyric_token_idss[idx0:idx0 + 1],
            total_duration_seconds=float(audio_duration),
            vocal_language=vocal_language or "en",
            inference_steps=int(inference_steps),
            seed=42,
        )

        if result.get("success"):
            lrc_text = result.get("lrc_text", "")
            if not lrc_text:
                return gr.update(value=t("messages.lrc_empty_result"), visible=True), gr.skip(), batch_queue

            if "lrcs" not in batch_queue[current_batch_index]:
                batch_queue[current_batch_index]["lrcs"] = [""] * 8
            batch_queue[current_batch_index]["lrcs"][idx0] = lrc_text

            vtt_path = lrc_to_vtt_file(lrc_text, total_duration=float(audio_duration))
            if "subtitles" not in batch_queue[current_batch_index]:
                batch_queue[current_batch_index]["subtitles"] = [None] * 8
            batch_queue[current_batch_index]["subtitles"][idx0] = vtt_path

            return gr.update(value=lrc_text, visible=True), gr.skip(), batch_queue
        else:
            error_msg = result.get("error", "Unknown error")
            return gr.update(value=f"❌ {error_msg}", visible=True), gr.skip(), batch_queue

    except Exception as e:
        logger.exception("[generate_lrc_handler] Error generating LRC")
        return gr.update(value=f"❌ Error: {str(e)}", visible=True), gr.skip(), batch_queue
