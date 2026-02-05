"""
Results Handlers Module
Contains event handlers and helper functions related to result display, scoring, and batch management
"""
import os
import json
import datetime
import math
import re
import tempfile
import shutil
import zipfile
import time as time_module
import sys
from typing import Dict, Any, Optional, List
import gradio as gr
from loguru import logger
from acestep.gradio_ui.i18n import t
from acestep.gradio_ui.events.generation_handlers import parse_and_validate_timesteps
from acestep.inference import generate_music, GenerationParams, GenerationConfig
from acestep.audio_utils import save_audio
from acestep.gpu_config import (
    get_global_gpu_config,
    check_duration_limit,
    check_batch_size_limit,
)

# Platform detection for Windows-specific fixes
IS_WINDOWS = sys.platform == "win32"

# Global results directory inside project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_RESULTS_DIR = os.path.join(PROJECT_ROOT, "gradio_outputs").replace("\\", "/")
os.makedirs(DEFAULT_RESULTS_DIR, exist_ok=True)


def parse_lrc_to_subtitles(lrc_text: str, total_duration: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    Parse LRC lyrics text to Gradio subtitles format with SMART POST-PROCESSING.
    
    Fixes the issue where lines starting very close to each other (e.g. Intro/Verse tags)
    disappear too quickly. It merges short lines into the subsequent line.
    
    Args:
        lrc_text: LRC format lyrics string
        total_duration: Total audio duration in seconds
        
    Returns:
        List of subtitle dictionaries
    """
    if not lrc_text or not lrc_text.strip():
        return []
    
    # Regex patterns for LRC timestamps
    timestamp_pattern = r'\[(\d{2}):(\d{2})\.(\d{2,3})\]'
    
    raw_entries = []
    lines = lrc_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        timestamps = re.findall(timestamp_pattern, line)
        if not timestamps:
            continue
        
        text = re.sub(timestamp_pattern, '', line).strip()
        # Even if text is empty, we might want to capture the timestamp to mark an end,
        # but for subtitles, empty text usually means silence or instrumental.
        # We keep it if it has text, or if it looks like a functional tag.
        if not text:
            continue
            
        # Parse start time
        start_minutes, start_seconds, start_centiseconds = timestamps[0]
        cs = int(start_centiseconds)
        # Handle 2-digit (1/100) vs 3-digit (1/1000)
        start_time = int(start_minutes) * 60 + int(start_seconds) + (cs / 100.0 if len(start_centiseconds) == 2 else cs / 1000.0)
        
        # Determine explicit end time if present (e.g. [start][end]text)
        end_time = None
        if len(timestamps) >= 2:
            end_minutes, end_seconds, end_centiseconds = timestamps[1]
            cs_end = int(end_centiseconds)
            end_time = int(end_minutes) * 60 + int(end_seconds) + (cs_end / 100.0 if len(end_centiseconds) == 2 else cs_end / 1000.0)
            
        raw_entries.append({
            'start': start_time,
            'explicit_end': end_time,
            'text': text
        })
    
    # Sort by start time
    raw_entries.sort(key=lambda x: x['start'])
    
    if not raw_entries:
        return []

    # --- POST-PROCESSING: MERGE SHORT LINES ---
    # Threshold: If a line displays for less than X seconds before the next line, merge them.
    MIN_DISPLAY_DURATION = 2.0  # seconds
    
    merged_entries = []
    i = 0
    while i < len(raw_entries):
        current = raw_entries[i]
        
        # Look ahead to see if we need to merge multiple lines
        # We act as an accumulator
        combined_text = current['text']
        combined_start = current['start']
        # Default end is strictly the explicit end, or we figure it out later
        combined_explicit_end = current['explicit_end'] 
        
        next_idx = i + 1
        
        # While there is a next line, and the gap between current start and next start is too small
        while next_idx < len(raw_entries):
            next_entry = raw_entries[next_idx]
            gap = next_entry['start'] - combined_start
            
            # If the gap is smaller than threshold (and the next line doesn't start way later)
            # We merge 'current' into 'next' visually by stacking text
            if gap < MIN_DISPLAY_DURATION:
                # Merge text
                # If text is wrapped in brackets [], likely a tag, separate with space
                # If regular lyrics, maybe newline? Let's use newline for clarity in subtitles.
                combined_text += "\n" + next_entry['text']
                
                # The explicit end becomes the next entry's explicit end (if any), 
                # effectively extending the block
                if next_entry['explicit_end']:
                    combined_explicit_end = next_entry['explicit_end']
                
                # Consume this next entry
                next_idx += 1
            else:
                # Gap is big enough, stop merging
                break
        
        # Add the (potentially merged) entry
        merged_entries.append({
            'start': combined_start,
            'explicit_end': combined_explicit_end,
            'text': combined_text
        })
        
        # Move loop index
        i = next_idx

    # --- GENERATE FINAL SUBTITLES ---
    subtitles = []
    for i, entry in enumerate(merged_entries):
        start = entry['start']
        text = entry['text']
        
        # Determine End Time
        if entry['explicit_end'] is not None:
            end = entry['explicit_end']
        else:
            # If no explicit end, use next line's start
            if i + 1 < len(merged_entries):
                end = merged_entries[i + 1]['start']
            else:
                # Last line
                if total_duration is not None and total_duration > start:
                    end = total_duration
                else:
                    end = start + 5.0  # Default duration for last line
        
        # Final safety: Ensure end > start
        if end <= start:
            end = start + 3.0
            
        subtitles.append({
            'text': text,
            'timestamp': [start, end]
        })
        
    return subtitles


def _format_vtt_timestamp(seconds: float) -> str:
    """
    Format seconds to VTT timestamp format: HH:MM:SS.mmm
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted timestamp string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def lrc_to_vtt_file(lrc_text: str, total_duration: float = None) -> Optional[str]:
    """
    Convert LRC text to a VTT file and return the file path.
    
    This creates a WebVTT subtitle file that Gradio can use as a native
    <track src="..."> element, which is more stable than JS-based subtitle injection.
    
    VTT format example:
    WEBVTT
    
    00:00:00.000 --> 00:00:05.000
    First subtitle line
    
    00:00:05.000 --> 00:00:10.000
    Second subtitle line
    
    Args:
        lrc_text: LRC format lyrics string
        total_duration: Total audio duration in seconds (used for last line's end time)
        
    Returns:
        Path to the generated VTT file, or None if conversion fails
    """
    if not lrc_text or not lrc_text.strip():
        return None
    
    # Parse LRC to subtitles data
    subtitles = parse_lrc_to_subtitles(lrc_text, total_duration=total_duration)
    
    if not subtitles:
        return None
    
    # Build VTT content
    vtt_lines = ["WEBVTT", ""]  # VTT header with blank line
    
    for i, subtitle in enumerate(subtitles):
        start_time = subtitle['timestamp'][0]
        end_time = subtitle['timestamp'][1]
        text = subtitle['text']
        
        # Add cue with index (optional but helpful for debugging)
        vtt_lines.append(str(i + 1))
        vtt_lines.append(f"{_format_vtt_timestamp(start_time)} --> {_format_vtt_timestamp(end_time)}")
        vtt_lines.append(text)
        vtt_lines.append("")  # Blank line between cues
    
    vtt_content = "\n".join(vtt_lines)

    # Create local directory and save VTT file
    try:
        timestamp = int(time_module.time())
        vtt_output_dir = os.path.join(DEFAULT_RESULTS_DIR, "subtitles")
        os.makedirs(vtt_output_dir, exist_ok=True)

        # Use unique name for cache-busting
        vtt_filename = f"subtitles_{timestamp}_{datetime.datetime.now().strftime('%H%M%S')}.vtt"
        vtt_path = os.path.join(vtt_output_dir, vtt_filename).replace("\\", "/")

        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write(vtt_content)
        return vtt_path
    except Exception as e:
        logger.error(f"[lrc_to_vtt_file] Failed to create VTT file: {e}")
        return None


def _build_generation_info(
    lm_metadata: Optional[Dict[str, Any]],
    time_costs: Dict[str, float],
    seed_value: str,
    inference_steps: int,
    num_audios: int,
) -> str:
    """Build generation info string from result data.
    
    Args:
        lm_metadata: LM-generated metadata dictionary
        time_costs: Unified time costs dictionary
        seed_value: Seed value string
        inference_steps: Number of inference steps
        num_audios: Number of generated audios
        
    Returns:
        Formatted generation info string
    """
    info_parts = []
    
    # Part 1: Per-track average time (prominently displayed at the top)
    # Only count model time (LM + DiT), not post-processing like audio conversion
    if time_costs and num_audios > 0:
        lm_total = time_costs.get('lm_total_time', 0.0)
        dit_total = time_costs.get('dit_total_time_cost', 0.0)
        model_total = lm_total + dit_total
        if model_total > 0:
            avg_time_per_track = model_total / num_audios
            avg_section = f"**🎯 Average Time per Track: {avg_time_per_track:.2f}s** ({num_audios} track(s))"
            info_parts.append(avg_section)
    
    # Part 2: LM-generated metadata (if available)
    if lm_metadata:
        metadata_lines = []
        if lm_metadata.get('bpm'):
            metadata_lines.append(f"- **BPM:** {lm_metadata['bpm']}")
        if lm_metadata.get('caption'):
            metadata_lines.append(f"- **Refined Caption:** {lm_metadata['caption']}")
        if lm_metadata.get('lyrics'):
            metadata_lines.append(f"- **Refined Lyrics:** {lm_metadata['lyrics']}")
        if lm_metadata.get('duration'):
            metadata_lines.append(f"- **Duration:** {lm_metadata['duration']} seconds")
        if lm_metadata.get('keyscale'):
            metadata_lines.append(f"- **Key Scale:** {lm_metadata['keyscale']}")
        if lm_metadata.get('language'):
            metadata_lines.append(f"- **Language:** {lm_metadata['language']}")
        if lm_metadata.get('timesignature'):
            metadata_lines.append(f"- **Time Signature:** {lm_metadata['timesignature']}")
        
        if metadata_lines:
            metadata_section = "**🤖 LM-Generated Metadata:**\n" + "\n".join(metadata_lines)
            info_parts.append(metadata_section)
    
    # Part 3: Time costs breakdown (formatted and beautified)
    if time_costs:
        time_lines = []
        
        # LM time costs
        lm_phase1 = time_costs.get('lm_phase1_time', 0.0)
        lm_phase2 = time_costs.get('lm_phase2_time', 0.0)
        lm_total = time_costs.get('lm_total_time', 0.0)
        
        if lm_total > 0:
            time_lines.append("**🧠 LM Time:**")
            if lm_phase1 > 0:
                time_lines.append(f"  - Phase 1 (CoT): {lm_phase1:.2f}s")
            if lm_phase2 > 0:
                time_lines.append(f"  - Phase 2 (Codes): {lm_phase2:.2f}s")
            time_lines.append(f"  - Total: {lm_total:.2f}s")
        
        # DiT time costs
        dit_encoder = time_costs.get('dit_encoder_time_cost', 0.0)
        dit_model = time_costs.get('dit_model_time_cost', 0.0)
        dit_vae_decode = time_costs.get('dit_vae_decode_time_cost', 0.0)
        dit_offload = time_costs.get('dit_offload_time_cost', 0.0)
        dit_total = time_costs.get('dit_total_time_cost', 0.0)
        if dit_total > 0:
            time_lines.append("\n**🎵 DiT Time:**")
            if dit_encoder > 0:
                time_lines.append(f"  - Encoder: {dit_encoder:.2f}s")
            if dit_model > 0:
                time_lines.append(f"  - Model: {dit_model:.2f}s")
            if dit_vae_decode > 0:
                time_lines.append(f"  - VAE Decode: {dit_vae_decode:.2f}s")
            if dit_offload > 0:
                time_lines.append(f"  - Offload: {dit_offload:.2f}s")
            time_lines.append(f"  - Total: {dit_total:.2f}s")
        
        # Post-processing time costs
        audio_conversion_time = time_costs.get('audio_conversion_time', 0.0)
        auto_score_time = time_costs.get('auto_score_time', 0.0)
        auto_lrc_time = time_costs.get('auto_lrc_time', 0.0)
        
        if audio_conversion_time > 0 or auto_score_time > 0 or auto_lrc_time > 0:
            time_lines.append("\n**🔧 Post-processing Time:**")
            if audio_conversion_time > 0:
                time_lines.append(f"  - Audio Conversion: {audio_conversion_time:.2f}s")
            if auto_score_time > 0:
                time_lines.append(f"  - Auto Score: {auto_score_time:.2f}s")
            if auto_lrc_time > 0:
                time_lines.append(f"  - Auto LRC: {auto_lrc_time:.2f}s")
        
        if time_lines:
            time_section = "\n".join(time_lines)
            info_parts.append(time_section)
    
    # Part 4: Generation summary
    summary_lines = [
        "**🎵 Generation Complete**",
        f"  - **Seeds:** {seed_value}",
        f"  - **Steps:** {inference_steps}",
        f"  - **Audio Count:** {num_audios} audio(s)",
    ]
    info_parts.append("\n".join(summary_lines))
    
    # Part 5: Pipeline total time (at the end)
    pipeline_total = time_costs.get('pipeline_total_time', 0.0) if time_costs else 0.0
    if pipeline_total > 0:
        info_parts.append(f"**⏱️ Total Time: {pipeline_total:.2f}s**")
    
    # Combine all parts
    return "\n\n".join(info_parts)


def store_batch_in_queue(
    batch_queue,
    batch_index,
    audio_paths,
    generation_info,
    seeds,
    codes=None,
    scores=None,
    allow_lm_batch=False,
    batch_size=2,
    generation_params=None,
    lm_generated_metadata=None,
    extra_outputs=None,
    status="completed"
):
    """Store batch results in queue with ALL generation parameters
    
    Args:
        codes: Audio codes used for generation (list for batch mode, string for single mode)
        scores: List of score displays for each audio (optional)
        allow_lm_batch: Whether batch LM mode was used for this batch
        batch_size: Batch size used for this batch
        generation_params: Complete dictionary of ALL generation parameters used
        lm_generated_metadata: LM-generated metadata for scoring (optional)
        extra_outputs: Dictionary containing pred_latents, encoder_hidden_states, etc. for LRC generation
    """
    batch_queue[batch_index] = {
        "status": status,
        "audio_paths": audio_paths,
        "generation_info": generation_info,
        "seeds": seeds,
        "codes": codes,  # Store codes used for this batch
        "scores": scores if scores else [""] * 8,  # Store scores, default to empty
        "allow_lm_batch": allow_lm_batch,  # Store batch mode setting
        "batch_size": batch_size,  # Store batch size
        "generation_params": generation_params if generation_params else {},  # Store ALL parameters
        "lm_generated_metadata": lm_generated_metadata,  # Store LM metadata for scoring
        "extra_outputs": extra_outputs if extra_outputs else {},  # Store extra outputs for LRC generation
        "timestamp": datetime.datetime.now().isoformat()
    }
    return batch_queue


def update_batch_indicator(current_batch, total_batches):
    """Update batch indicator text"""
    return t("results.batch_indicator", current=current_batch + 1, total=total_batches)


def update_navigation_buttons(current_batch, total_batches):
    """Determine navigation button states"""
    can_go_previous = current_batch > 0
    can_go_next = current_batch < total_batches - 1
    return can_go_previous, can_go_next

def send_audio_to_src_with_metadata(audio_file, lm_metadata):
    """Send generated audio file to src_audio input WITHOUT modifying other fields
    
    This function ONLY sets the src_audio field. All other metadata fields (caption, lyrics, etc.)
    are preserved by returning gr.skip() to avoid overwriting user's existing inputs.
    
    Args:
        audio_file: Audio file path
        lm_metadata: Dictionary containing LM-generated metadata (unused, kept for API compatibility)
        
    Returns:
        Tuple of (audio_file, bpm, caption, lyrics, duration, key_scale, language, time_signature, is_format_caption)
        All values except audio_file are gr.skip() to preserve existing UI values
    """
    if audio_file is None:
        # Return all skip to not modify anything
        return (gr.skip(),) * 9
    
    # Only set the audio file, skip all other fields to preserve existing values
    # This ensures user's caption, lyrics, bpm, etc. are NOT cleared
    return (
        audio_file,      # src_audio - set the audio file
        gr.skip(),       # bpm - preserve existing value
        gr.skip(),       # caption - preserve existing value
        gr.skip(),       # lyrics - preserve existing value
        gr.skip(),       # duration - preserve existing value
        gr.skip(),       # key_scale - preserve existing value
        gr.skip(),       # language - preserve existing value
        gr.skip(),       # time_signature - preserve existing value
        gr.skip(),       # is_format_caption - preserve existing value
    )


def send_audio_to_ref(audio_file):
    """Send generated audio file to reference_audio input

    Args:
        audio_file: Audio file path

    Returns:
        audio_file path or None
    """
    return audio_file


def generate_with_progress(
    dit_handler, llm_handler,
    captions, lyrics, bpm, key_scale, time_signature, vocal_language,
    inference_steps, guidance_scale, random_seed_checkbox, seed,
    reference_audio, audio_duration, batch_size_input, src_audio,
    text2music_audio_code_string, repainting_start, repainting_end,
    instruction_display_gen, audio_cover_strength, task_type,
    use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method, custom_timesteps, audio_format, lm_temperature,
    think_checkbox, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
    use_cot_metas, use_cot_caption, use_cot_language, is_format_caption,
    constrained_decoding_debug,
    allow_lm_batch,
    auto_score,
    auto_lrc,
    score_scale,
    lm_batch_chunk_size,
    custom_track_name=None,
    scratchpad=None,
    progress=gr.Progress(track_tqdm=True),
):
    """Generate audio with progress tracking"""
    
    # ========== GPU Memory Validation ==========
    # Check if duration and batch size are within GPU memory limits
    gpu_config = get_global_gpu_config()
    lm_initialized = llm_handler.llm_initialized if llm_handler else False
    
    # Validate duration
    if audio_duration is not None and audio_duration > 0:
        is_valid, warning_msg = check_duration_limit(audio_duration, gpu_config, lm_initialized)
        if not is_valid:
            gr.Warning(warning_msg)
            # Clamp duration to max allowed
            max_duration = gpu_config.max_duration_with_lm if lm_initialized else gpu_config.max_duration_without_lm
            audio_duration = min(audio_duration, max_duration)
            logger.warning(f"Duration clamped to {audio_duration}s due to GPU memory limits")
    
    # Validate batch size
    if batch_size_input is not None and batch_size_input > 0:
        is_valid, warning_msg = check_batch_size_limit(int(batch_size_input), gpu_config, lm_initialized)
        if not is_valid:
            gr.Warning(warning_msg)
            # Clamp batch size to max allowed
            max_batch_size = gpu_config.max_batch_size_with_lm if lm_initialized else gpu_config.max_batch_size_without_lm
            batch_size_input = min(int(batch_size_input), max_batch_size)
            logger.warning(f"Batch size clamped to {batch_size_input} due to GPU memory limits")
    
    # Skip Phase 1 metas COT if sample is already formatted (from LLM/file/random)
    # This avoids redundant LLM calls since metas (bpm, keyscale, etc.) are already generated
    actual_use_cot_metas = use_cot_metas
    if is_format_caption and use_cot_metas:
        actual_use_cot_metas = False
        logger.info("[generate_with_progress] Skipping Phase 1 metas COT: sample is already formatted (is_format_caption=True)")
        gr.Info(t("messages.skipping_metas_cot"))
    
    # Parse and validate custom timesteps
    parsed_timesteps, has_timesteps_warning, _ = parse_and_validate_timesteps(custom_timesteps, inference_steps)
    
    # Update inference_steps if custom timesteps provided (to match UI display)
    actual_inference_steps = inference_steps
    if parsed_timesteps is not None:
        actual_inference_steps = len(parsed_timesteps) - 1
    
    # step 1: prepare inputs
    # generate_music, GenerationParams, GenerationConfig
    gen_params = GenerationParams(
        task_type=task_type,
        instruction=instruction_display_gen,
        reference_audio=reference_audio,
        src_audio=src_audio,
        audio_codes=text2music_audio_code_string if not think_checkbox else "",
        caption=captions or "",
        lyrics=lyrics or "",
        instrumental=False,
        vocal_language=vocal_language,
        bpm=bpm,
        keyscale=key_scale,
        timesignature=time_signature,
        duration=audio_duration,
        inference_steps=actual_inference_steps,
        guidance_scale=guidance_scale,
        use_adg=use_adg,
        cfg_interval_start=cfg_interval_start,
        cfg_interval_end=cfg_interval_end,
        shift=shift,
        infer_method=infer_method,
        timesteps=parsed_timesteps,
        repainting_start=repainting_start,
        repainting_end=repainting_end,
        audio_cover_strength=audio_cover_strength,
        thinking=think_checkbox,
        lm_temperature=lm_temperature,
        lm_cfg_scale=lm_cfg_scale,
        lm_top_k=lm_top_k,
        lm_top_p=lm_top_p,
        lm_negative_prompt=lm_negative_prompt,
        use_cot_metas=actual_use_cot_metas,
        use_cot_caption=use_cot_caption,
        use_cot_language=use_cot_language,
        use_constrained_decoding=True,
    )
    # seed string to list
    if isinstance(seed, str) and seed.strip():
        if "," in seed:
            seed_list = [int(s.strip()) for s in seed.split(",")]
        else:
            seed_list = [int(seed.strip())]
    else:
        seed_list = None
    gen_config = GenerationConfig(
        batch_size=batch_size_input,
        allow_lm_batch=allow_lm_batch,
        use_random_seed=random_seed_checkbox,
        seeds=seed_list,
        lm_batch_chunk_size=lm_batch_chunk_size,
        constrained_decoding_debug=constrained_decoding_debug,
        audio_format=audio_format,
    )
    result = generate_music(
        dit_handler,
        llm_handler,
        params=gen_params,
        config=gen_config,
        progress=progress,
    )
    
    audio_outputs = [None] * 8
    all_audio_paths = []
    final_codes_list = [""] * 8
    final_scores_list = [""] * 8
    
    # Build generation_info from result data
    status_message = result.status_message
    seed_value_for_ui = result.extra_outputs.get("seed_value", "")
    lm_generated_metadata = result.extra_outputs.get("lm_metadata", {})
    time_costs = result.extra_outputs.get("time_costs", {}).copy()
    
    # Initialize post-processing timing
    audio_conversion_start_time = time_module.time()
    total_auto_score_time = 0.0
    total_auto_lrc_time = 0.0
    
    # Initialize LRC storage for auto_lrc
    final_lrcs_list = [""] * 8
    final_subtitles_list = [None] * 8
    
    updated_audio_codes = text2music_audio_code_string if not think_checkbox else ""
    
    # Build initial generation_info (will be updated with post-processing times at the end)
    generation_info = _build_generation_info(
        lm_metadata=lm_generated_metadata,
        time_costs=time_costs,
        seed_value=seed_value_for_ui,
        inference_steps=inference_steps,
        num_audios=len(result.audios) if result.success else 0,
    )
    
    if not result.success:
        # Structure: 8 audio + batch_files + gen_info + status + seed + 8 scores + 8 codes_display + 8 accordions + 8 lrc_display + lm_meta + is_format + extra_outputs + raw_codes
        yield (
            (None,) * 8 +  # audio outputs
            (None, generation_info, result.status_message, gr.skip()) +  # batch_files, gen_info, status, seed
            (gr.skip(),) * 8 +  # scores
            (gr.skip(),) * 8 +  # codes_display
            (gr.skip(),) * 8 +  # details_accordion
            (gr.skip(),) * 8 +  # lrc_display
            (None, is_format_caption, None, None)  # lm_meta, is_format, extra_outputs, raw_codes
        )
        return
    
    audios = result.audios
    progress(0.99, "Converting audio to mp3...")
    
    # Clear all scores, codes, lrc displays at the start of generation
    # Note: Create independent gr.update objects (not references to the same object)
    # 
    # NEW APPROACH: Don't update audio subtitles directly!
    # Clearing lrc_display will trigger lrc_display.change() which clears subtitles automatically.
    # This decouples audio value updates from subtitle updates, avoiding flickering.
    # 
    # IMPORTANT: Keep visible=True to ensure .change() event is properly triggered by Gradio.
    # These should always remain visible=True so users can expand accordion anytime.
    clear_scores = [gr.update(value="", visible=True) for _ in range(8)]
    clear_codes = [gr.update(value="", visible=True) for _ in range(8)]
    # Clear lrc_display with empty string - this triggers .change() to clear subtitles
    clear_lrcs = [gr.update(value="", visible=True) for _ in range(8)]
    clear_accordions = [gr.skip() for _ in range(8)]  # Don't change accordion visibility
    dump_audio = [gr.update(value=None, subtitles=None) for _ in range(8)]
    yield (
        # Audio outputs - just skip, value will be updated in loop
        # Subtitles will be cleared via lrc_display.change()
        dump_audio[0], dump_audio[1], dump_audio[2], dump_audio[3], dump_audio[4], dump_audio[5], dump_audio[6], dump_audio[7],
        None,  # all_audio_paths (clear batch files)
        generation_info,
        "Clearing previous results...",
        gr.skip(),  # seed
        # Clear scores
        clear_scores[0], clear_scores[1], clear_scores[2], clear_scores[3],
        clear_scores[4], clear_scores[5], clear_scores[6], clear_scores[7],
        # Clear codes display
        clear_codes[0], clear_codes[1], clear_codes[2], clear_codes[3],
        clear_codes[4], clear_codes[5], clear_codes[6], clear_codes[7],
        # Clear accordions
        clear_accordions[0], clear_accordions[1], clear_accordions[2], clear_accordions[3],
        clear_accordions[4], clear_accordions[5], clear_accordions[6], clear_accordions[7],
        # Clear lrc displays
        clear_lrcs[0], clear_lrcs[1], clear_lrcs[2], clear_lrcs[3],
        clear_lrcs[4], clear_lrcs[5], clear_lrcs[6], clear_lrcs[7],
        lm_generated_metadata,
        is_format_caption,
        None,  # extra_outputs placeholder
        None,  # raw_codes placeholder
    )
    time_module.sleep(0.1)
    
    for i in range(8):
        if i < len(audios):
            key = audios[i]["key"]
            audio_tensor = audios[i]["tensor"]
            sample_rate = audios[i]["sample_rate"]
            audio_params = audios[i]["params"]
            # Use local output directory instead of system temp
            timestamp = int(time_module.time())
            temp_dir = os.path.join(DEFAULT_RESULTS_DIR, f"batch_{timestamp}")
            temp_dir = os.path.abspath(temp_dir).replace("\\", "/")
            os.makedirs(temp_dir, exist_ok=True)

            # File naming logic
            if custom_track_name and str(custom_track_name).strip():
                # Sanitize filename
                base_name = str(custom_track_name).strip()
                base_name = re.sub(r'[\\/*?:"<>|]', "", base_name)

                # Append inpainting info if applicable
                if repainting_end != -1:
                    base_name += f"-inpaint_{repainting_start}:{repainting_end}"

                # Append batch index
                filename = f"{base_name}_{i+1}"
            else:
                filename = key

            json_path = os.path.join(temp_dir, f"{filename}.json").replace("\\", "/")
            audio_path = os.path.join(temp_dir, f"{filename}.{audio_format}").replace("\\", "/")

            save_audio(audio_data=audio_tensor, output_path=audio_path, sample_rate=sample_rate, format=audio_format, channels_first=True)

            # Add custom params to metadata
            if custom_track_name:
                audio_params["custom_track_name"] = custom_track_name
            if scratchpad:
                audio_params["scratchpad"] = scratchpad

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(audio_params, f, indent=2, ensure_ascii=False)
            audio_outputs[i] = audio_path
            all_audio_paths.append(audio_path)
            all_audio_paths.append(json_path)
            
            code_str = audio_params.get("audio_codes", "")
            final_codes_list[i] = code_str
            
            scores_ui_updates = [gr.skip() for _ in range(8)]
            score_str = "Done!"
            if auto_score:
                auto_score_start = time_module.time()

                sample_tensor_data = None
                try:
                    full_pred = result.extra_outputs.get("pred_latents")

                    if full_pred is not None and i < full_pred.shape[0]:
                        sample_tensor_data = {
                            "pred_latent": full_pred[i:i + 1],
                            "encoder_hidden_states": result.extra_outputs.get("encoder_hidden_states")[
                                                     i:i + 1] if result.extra_outputs.get(
                                "encoder_hidden_states") is not None else None,
                            "encoder_attention_mask": result.extra_outputs.get("encoder_attention_mask")[
                                                      i:i + 1] if result.extra_outputs.get(
                                "encoder_attention_mask") is not None else None,
                            "context_latents": result.extra_outputs.get("context_latents")[
                                               i:i + 1] if result.extra_outputs.get(
                                "context_latents") is not None else None,
                            "lyric_token_ids": result.extra_outputs.get("lyric_token_idss")[
                                               i:i + 1] if result.extra_outputs.get(
                                "lyric_token_idss") is not None else None,
                        }

                        # 简单校验完整性
                        if any(v is None for v in sample_tensor_data.values()):
                            sample_tensor_data = None

                except Exception as e:
                    print(f"[Auto Score] Failed to prepare tensor data for sample {i}: {e}")
                    sample_tensor_data = None

                score_str = calculate_score_handler(llm_handler, code_str, captions, lyrics, lm_generated_metadata, bpm, key_scale, time_signature, audio_duration, vocal_language, score_scale, dit_handler, sample_tensor_data, inference_steps)
                auto_score_end = time_module.time()
                total_auto_score_time += (auto_score_end - auto_score_start)
            scores_ui_updates[i] = score_str
            final_scores_list[i] = score_str
            
            # Auto LRC generation
            if auto_lrc:
                auto_lrc_start = time_module.time()
                logger.info(f"[auto_lrc] Starting LRC generation for sample {i + 1}")
                try:
                    # Get extra_outputs for this sample
                    pred_latents = result.extra_outputs.get("pred_latents")
                    encoder_hidden_states = result.extra_outputs.get("encoder_hidden_states")
                    encoder_attention_mask = result.extra_outputs.get("encoder_attention_mask")
                    context_latents = result.extra_outputs.get("context_latents")
                    lyric_token_idss = result.extra_outputs.get("lyric_token_idss")
                    
                    logger.info(f"[auto_lrc] pred_latents: {pred_latents is not None}, encoder_hidden_states: {encoder_hidden_states is not None}, encoder_attention_mask: {encoder_attention_mask is not None}, context_latents: {context_latents is not None}, lyric_token_idss: {lyric_token_idss is not None}")
                    
                    if all(x is not None for x in [pred_latents, encoder_hidden_states, encoder_attention_mask, context_latents, lyric_token_idss]):
                        # Extract single sample tensors
                        sample_pred_latent = pred_latents[i:i+1]
                        sample_encoder_hidden_states = encoder_hidden_states[i:i+1]
                        sample_encoder_attention_mask = encoder_attention_mask[i:i+1]
                        sample_context_latents = context_latents[i:i+1]
                        sample_lyric_token_ids = lyric_token_idss[i:i+1]
                        
                        # Calculate actual duration
                        actual_duration = audio_duration
                        if actual_duration is None or actual_duration <= 0:
                            latent_length = pred_latents.shape[1]
                            actual_duration = latent_length / 25.0  # 25 Hz latent rate
                        
                        lrc_result = dit_handler.get_lyric_timestamp(
                            pred_latent=sample_pred_latent,
                            encoder_hidden_states=sample_encoder_hidden_states,
                            encoder_attention_mask=sample_encoder_attention_mask,
                            context_latents=sample_context_latents,
                            lyric_token_ids=sample_lyric_token_ids,
                            total_duration_seconds=float(actual_duration),
                            vocal_language=vocal_language or "en",
                            inference_steps=int(inference_steps),
                            seed=42,
                        )
                        
                        logger.info(f"[auto_lrc] LRC result for sample {i + 1}: success={lrc_result.get('success')}")
                        if lrc_result.get("success"):
                            lrc_text = lrc_result.get("lrc_text", "")
                            final_lrcs_list[i] = lrc_text
                            logger.info(f"[auto_lrc] LRC text length for sample {i + 1}: {len(lrc_text)}")
                            # Convert LRC to VTT file for storage (consistent with new VTT-based approach)
                            vtt_path = lrc_to_vtt_file(lrc_text, total_duration=float(actual_duration))
                            final_subtitles_list[i] = vtt_path
                    else:
                        logger.warning(f"[auto_lrc] Missing required extra_outputs for sample {i + 1}")
                except Exception as e:
                    logger.warning(f"[auto_lrc] Failed to generate LRC for sample {i + 1}: {e}")
                auto_lrc_end = time_module.time()
                total_auto_lrc_time += (auto_lrc_end - auto_lrc_start)
            
            status_message = f"Encoding & Ready: {i+1}/{len(audios)}"
            has_lrc = bool(final_lrcs_list[i])
            has_score = bool(score_str) and score_str != "Done!"
            has_content = bool(code_str) or has_lrc or has_score
            
            # ============== STEP 1: Yield audio + CLEAR LRC ==============
            # First, update audio and clear LRC to avoid race condition
            # (audio needs to load before subtitles are set via .change() event)
            current_audio_updates = [gr.skip() for _ in range(8)]
            current_audio_updates[i] = audio_path
            
            codes_display_updates = [gr.skip() for _ in range(8)]
            codes_display_updates[i] = gr.update(value=code_str, visible=True)  # Keep visible=True
            
            details_accordion_updates = [gr.skip() for _ in range(8)]
            # Don't change accordion visibility - keep it always expandable
            
            # Clear LRC first (this triggers .change() to clear subtitles)
            # Keep visible=True to ensure .change() event is properly triggered
            lrc_clear_updates = [gr.skip() for _ in range(8)]
            lrc_clear_updates[i] = gr.update(value="", visible=True)
            
            yield (
                current_audio_updates[0], current_audio_updates[1], current_audio_updates[2], current_audio_updates[3],
                current_audio_updates[4], current_audio_updates[5], current_audio_updates[6], current_audio_updates[7],
                all_audio_paths,
                generation_info,
                status_message,
                seed_value_for_ui,
                scores_ui_updates[0], scores_ui_updates[1], scores_ui_updates[2], scores_ui_updates[3], scores_ui_updates[4], scores_ui_updates[5], scores_ui_updates[6], scores_ui_updates[7],
                codes_display_updates[0], codes_display_updates[1], codes_display_updates[2], codes_display_updates[3],
                codes_display_updates[4], codes_display_updates[5], codes_display_updates[6], codes_display_updates[7],
                details_accordion_updates[0], details_accordion_updates[1], details_accordion_updates[2], details_accordion_updates[3],
                details_accordion_updates[4], details_accordion_updates[5], details_accordion_updates[6], details_accordion_updates[7],
                # LRC display - CLEAR first
                lrc_clear_updates[0], lrc_clear_updates[1], lrc_clear_updates[2], lrc_clear_updates[3],
                lrc_clear_updates[4], lrc_clear_updates[5], lrc_clear_updates[6], lrc_clear_updates[7],
                lm_generated_metadata,
                is_format_caption,
                None,
                None,
            )
            
            # Wait for audio to load before setting subtitles
            time_module.sleep(0.05)
            
            # ============== STEP 2: Skip audio + SET actual LRC ==============
            # Now set the actual LRC content, which triggers .change() to set subtitles
            # This two-step approach (same as navigate_to_batch) ensures audio is loaded first
            if has_lrc:
                skip_audio = [gr.skip() for _ in range(8)]
                skip_scores = [gr.skip() for _ in range(8)]
                skip_codes = [gr.skip() for _ in range(8)]
                skip_accordions = [gr.skip() for _ in range(8)]
                
                lrc_actual_updates = [gr.skip() for _ in range(8)]
                lrc_actual_updates[i] = gr.update(value=final_lrcs_list[i], visible=True)  # Keep visible=True
                
                yield (
                    skip_audio[0], skip_audio[1], skip_audio[2], skip_audio[3],
                    skip_audio[4], skip_audio[5], skip_audio[6], skip_audio[7],
                    gr.skip(),  # all_audio_paths
                    gr.skip(),  # generation_info
                    gr.skip(),  # status_message
                    gr.skip(),  # seed
                    skip_scores[0], skip_scores[1], skip_scores[2], skip_scores[3],
                    skip_scores[4], skip_scores[5], skip_scores[6], skip_scores[7],
                    skip_codes[0], skip_codes[1], skip_codes[2], skip_codes[3],
                    skip_codes[4], skip_codes[5], skip_codes[6], skip_codes[7],
                    skip_accordions[0], skip_accordions[1], skip_accordions[2], skip_accordions[3],
                    skip_accordions[4], skip_accordions[5], skip_accordions[6], skip_accordions[7],
                    # LRC display - SET actual content (triggers .change() to set subtitles)
                    lrc_actual_updates[0], lrc_actual_updates[1], lrc_actual_updates[2], lrc_actual_updates[3],
                    lrc_actual_updates[4], lrc_actual_updates[5], lrc_actual_updates[6], lrc_actual_updates[7],
                    gr.skip(),  # lm_generated_metadata
                    gr.skip(),  # is_format_caption
                    None,
                    None,
                )
        else:
            # If i exceeds the generated count (e.g., batch=2, i=2..7), do not yield
            pass
        time_module.sleep(0.05)
    
    # Record audio conversion time
    audio_conversion_end_time = time_module.time()
    audio_conversion_time = audio_conversion_end_time - audio_conversion_start_time
    
    # Add post-processing times to time_costs
    if audio_conversion_time > 0:
        time_costs['audio_conversion_time'] = audio_conversion_time
    if total_auto_score_time > 0:
        time_costs['auto_score_time'] = total_auto_score_time
    if total_auto_lrc_time > 0:
        time_costs['auto_lrc_time'] = total_auto_lrc_time
    
    # Update pipeline total time to include post-processing
    if 'pipeline_total_time' in time_costs:
        time_costs['pipeline_total_time'] += audio_conversion_time + total_auto_score_time + total_auto_lrc_time
    
    # Rebuild generation_info with complete timing information
    generation_info = _build_generation_info(
        lm_metadata=lm_generated_metadata,
        time_costs=time_costs,
        seed_value=seed_value_for_ui,
        inference_steps=inference_steps,
        num_audios=len(result.audios),
    )
    
    # Build final codes display, LRC display, accordion visibility updates
    final_codes_display_updates = [gr.skip() for _ in range(8)]
    # final_lrc_display_updates = [gr.skip() for _ in range(8)]
    final_accordion_updates = [gr.skip() for _ in range(8)]

    # On Windows, progressive yields are disabled, so we must return actual audio paths
    # On other platforms, audio was already sent in loop yields, just reset playback position
    # Use gr.update() to force Gradio to update the audio component (Issue #113)
    audio_playback_updates = []
    for idx in range(8):
        path = audio_outputs[idx]
        if path:
            audio_playback_updates.append(gr.update(value=path, label=f"Sample {idx+1} (Ready)", interactive=True))
            logger.info(f"[generate_with_progress] Audio {idx+1} path: {path}")
        else:
            audio_playback_updates.append(gr.update(value=None, label="None", interactive=False))

    yield (
        # Audio outputs - use gr.update() to force component refresh
        audio_playback_updates[0], audio_playback_updates[1], audio_playback_updates[2], audio_playback_updates[3],
        audio_playback_updates[4], audio_playback_updates[5], audio_playback_updates[6], audio_playback_updates[7],
        all_audio_paths,
        generation_info,
        "Generation Complete",
        seed_value_for_ui,
        final_scores_list[0], final_scores_list[1], final_scores_list[2], final_scores_list[3],
        final_scores_list[4], final_scores_list[5], final_scores_list[6], final_scores_list[7],
        # Codes display in results section
        final_codes_display_updates[0], final_codes_display_updates[1], final_codes_display_updates[2], final_codes_display_updates[3],
        final_codes_display_updates[4], final_codes_display_updates[5], final_codes_display_updates[6], final_codes_display_updates[7],
        # Details accordion visibility
        final_accordion_updates[0], final_accordion_updates[1], final_accordion_updates[2], final_accordion_updates[3],
        final_accordion_updates[4], final_accordion_updates[5], final_accordion_updates[6], final_accordion_updates[7],
        # LRC display
        final_lrcs_list[0], final_lrcs_list[1], final_lrcs_list[2], final_lrcs_list[3],
        final_lrcs_list[4], final_lrcs_list[5], final_lrcs_list[6], final_lrcs_list[7],
        lm_generated_metadata,
        is_format_caption,
        {
            **result.extra_outputs,
            "lrcs": final_lrcs_list,
            "subtitles": final_subtitles_list,
        },  # extra_outputs for LRC generation (with auto_lrc results)
        final_codes_list,  # Raw codes list for batch storage (index 47)
    )



def calculate_score_handler(
        llm_handler,
        audio_codes_str,
        caption,
        lyrics,
        lm_metadata,
        bpm,
        key_scale,
        time_signature,
        audio_duration,
        vocal_language,
        score_scale,
        dit_handler,
        extra_tensor_data,
        inference_steps,
):
    """
    Calculate PMI-based quality score for generated audio.
    
    PMI (Pointwise Mutual Information) removes condition bias:
    score = log P(condition|codes) - log P(condition)
    
    For Cover/Repaint modes where audio_codes may not be available,
    falls back to DiT alignment scoring only.
    
    Args:
        llm_handler: LLM handler instance
        audio_codes_str: Generated audio codes string
        caption: Caption text used for generation
        lyrics: Lyrics text used for generation
        lm_metadata: LM-generated metadata dictionary (from CoT generation)
        bpm: BPM value
        key_scale: Key scale value
        time_signature: Time signature value
        audio_duration: Audio duration value
        vocal_language: Vocal language value
        score_scale: Sensitivity scale parameter
        dit_handler: DiT handler instance (for alignment scoring)
        extra_tensor_data: Dictionary containing tensors for the specific sample
        inference_steps: Number of inference steps used
        
    Returns:
        Score display string
    """
    from acestep.test_time_scaling import calculate_pmi_score_per_condition
    
    has_audio_codes = audio_codes_str and audio_codes_str.strip()
    has_dit_alignment_data = dit_handler and extra_tensor_data and lyrics and lyrics.strip()
    
    # Check if we can compute any scores
    if not has_audio_codes and not has_dit_alignment_data:
        # No audio codes and no DiT alignment data - can't compute any score
        return t("messages.no_codes")
    
    try:
        scores_per_condition = {}
        global_score = 0.0
        alignment_report = ""
        
        # PMI-based scoring (requires audio codes and LLM)
        if has_audio_codes:
            if not llm_handler.llm_initialized:
                # Can still try DiT alignment if available
                if not has_dit_alignment_data:
                    return t("messages.lm_not_initialized")
            else:
                # Build metadata dictionary from both LM metadata and user inputs
                metadata = {}
                
                # Priority 1: Use LM-generated metadata if available
                if lm_metadata and isinstance(lm_metadata, dict):
                    metadata.update(lm_metadata)
                
                # Priority 2: Add user-provided metadata (if not already in LM metadata)
                if bpm is not None and 'bpm' not in metadata:
                    try:
                        metadata['bpm'] = int(bpm)
                    except:
                        pass
                
                if caption and 'caption' not in metadata:
                    metadata['caption'] = caption
                
                if audio_duration is not None and audio_duration > 0 and 'duration' not in metadata:
                    try:
                        metadata['duration'] = int(audio_duration)
                    except:
                        pass
                
                if key_scale and key_scale.strip() and 'keyscale' not in metadata:
                    metadata['keyscale'] = key_scale.strip()
                
                if vocal_language and vocal_language.strip() and 'language' not in metadata:
                    metadata['language'] = vocal_language.strip()
                
                if time_signature and time_signature.strip() and 'timesignature' not in metadata:
                    metadata['timesignature'] = time_signature.strip()
                
                # Calculate per-condition scores with appropriate metrics
                # - Metadata fields (bpm, duration, etc.): Top-k recall
                # - Caption and lyrics: PMI (normalized)
                scores_per_condition, global_score, status = calculate_pmi_score_per_condition(
                    llm_handler=llm_handler,
                    audio_codes=audio_codes_str,
                    caption=caption or "",
                    lyrics=lyrics or "",
                    metadata=metadata if metadata else None,
                    temperature=1.0,
                    topk=10,
                    score_scale=score_scale
                )

        # DiT alignment scoring (works even without audio codes - for Cover/Repaint modes)
        if has_dit_alignment_data:
            try:
                align_result = dit_handler.get_lyric_score(
                    pred_latent=extra_tensor_data.get('pred_latent'),
                    encoder_hidden_states=extra_tensor_data.get('encoder_hidden_states'),
                    encoder_attention_mask=extra_tensor_data.get('encoder_attention_mask'),
                    context_latents=extra_tensor_data.get('context_latents'),
                    lyric_token_ids=extra_tensor_data.get('lyric_token_ids'),
                    vocal_language=vocal_language or "en",
                    inference_steps=int(inference_steps),
                    seed=42,
                )

                if align_result.get("success"):
                    lm_align_score = align_result.get("lm_score", 0.0)
                    dit_align_score = align_result.get("dit_score", 0.0)
                    alignment_report = (
                        f"  • llm lyrics alignment score: {lm_align_score:.4f}\n"
                        f"  • dit lyrics alignment score: {dit_align_score:.4f}\n"
                        "\n(Measures how well lyrics timestamps match audio energy using Cross-Attention)"
                    )
                else:
                    align_err = align_result.get("error", "Unknown error")
                    alignment_report = f"\n⚠️ Alignment Score Failed: {align_err}"
            except Exception as e:
                alignment_report = f"\n⚠️ Alignment Score Error: {str(e)}"

        # Format display string
        if has_audio_codes and llm_handler.llm_initialized:
            # Full scoring with PMI + alignment
            if global_score == 0.0 and not scores_per_condition:
                # PMI scoring failed but we might have alignment
                if alignment_report and not alignment_report.startswith("\n⚠️"):
                    final_output = "📊 DiT Alignment Scores (LM codes not available):\n"
                    final_output += alignment_report
                    return final_output
                return t("messages.score_failed", error="PMI scoring returned no results")
            else:
                # Build per-condition scores display
                condition_lines = []
                for condition_name, score_value in sorted(scores_per_condition.items()):
                    condition_lines.append(
                        f"  • {condition_name}: {score_value:.4f}"
                    )
                
                conditions_display = "\n".join(condition_lines) if condition_lines else "  (no conditions)"

                final_output = (
                    f"✅ Global Quality Score: {global_score:.4f} (0-1, higher=better)\n\n"
                    f"📊 Per-Condition Scores (0-1):\n{conditions_display}\n"
                )

                if alignment_report:
                    final_output += alignment_report + "\n"

                final_output += "Note: Metadata uses Top-k Recall, Caption/Lyrics use PMI"
                return final_output
        else:
            # Only DiT alignment available (Cover/Repaint mode fallback)
            if alignment_report and not alignment_report.startswith("\n⚠️"):
                final_output = "📊 DiT Alignment Scores (LM codes not available for Cover/Repaint mode):\n"
                final_output += alignment_report
                return final_output
            elif alignment_report:
                return alignment_report
            else:
                return "⚠️ No scoring data available"
            
    except Exception as e:
        import traceback
        error_msg = t("messages.score_error", error=str(e)) + f"\n{traceback.format_exc()}"
        return error_msg


def calculate_score_handler_with_selection(
        dit_handler,
        llm_handler,
        sample_idx,
        score_scale,
        current_batch_index,
        batch_queue):
    """
    Calculate PMI-based quality score - REFACTORED to read from batch_queue only.
    This ensures scoring uses the actual generation parameters, not current UI values.
    
    Args:
        dit_handler: DiT Handler
        llm_handler: LLM handler instance
        sample_idx: Which sample to score (1-8)
        score_scale: Sensitivity scale parameter (tool setting, can be from UI)
        current_batch_index: Current batch index
        batch_queue: Batch queue containing historical generation data
    """
    if current_batch_index not in batch_queue:
        return gr.skip(), gr.skip(), batch_queue
    
    batch_data = batch_queue[current_batch_index]
    params = batch_data.get("generation_params", {})
    
    # Read ALL parameters from historical batch data
    caption = params.get("captions", "")
    lyrics = params.get("lyrics", "")
    bpm = params.get("bpm")
    key_scale = params.get("key_scale", "")
    time_signature = params.get("time_signature", "")
    audio_duration = params.get("audio_duration", -1)
    vocal_language = params.get("vocal_language", "")
    inference_steps = params.get("inference_steps", 8)
    
    # Get LM metadata from batch_data (if it was saved during generation)
    lm_metadata = batch_data.get("lm_generated_metadata", None)
    
    # Get codes from batch_data
    stored_codes = batch_data.get("codes", "")
    stored_allow_lm_batch = batch_data.get("allow_lm_batch", False)
    
    # Select correct codes for this sample
    audio_codes_str = ""
    if stored_allow_lm_batch and isinstance(stored_codes, list):
        # Batch mode: use specific sample's codes
        if 0 <= sample_idx - 1 < len(stored_codes):
            code_item = stored_codes[sample_idx - 1]
            # Ensure it's a string (handle cases where dict was mistakenly stored)
            audio_codes_str = code_item if isinstance(code_item, str) else ""
    else:
        # Single mode: all samples use same codes
        audio_codes_str = stored_codes if isinstance(stored_codes, str) else ""

    # Extract Tensor Data for Alignment Score (Extra Outputs)
    extra_tensor_data = None
    extra_outputs = batch_data.get("extra_outputs", {})

    # Only proceed if we have tensors and a valid index
    if extra_outputs and dit_handler:
        pred_latents = extra_outputs.get("pred_latents")
        # Ensure we have the critical tensor to check batch size
        if pred_latents is not None:
            sample_idx_0based = sample_idx - 1
            batch_size = pred_latents.shape[0]

            if 0 <= sample_idx_0based < batch_size:
                # Slice tensors for this specific sample (keep dimension [1, ...])
                # We assume all stored tensors are aligned in batch dim 0
                try:
                    extra_tensor_data = {
                        "pred_latent": pred_latents[sample_idx_0based:sample_idx_0based + 1],
                        "encoder_hidden_states": extra_outputs.get("encoder_hidden_states")[
                                                 sample_idx_0based:sample_idx_0based + 1],
                        "encoder_attention_mask": extra_outputs.get("encoder_attention_mask")[
                                                  sample_idx_0based:sample_idx_0based + 1],
                        "context_latents": extra_outputs.get("context_latents")[
                                           sample_idx_0based:sample_idx_0based + 1],
                        "lyric_token_ids": extra_outputs.get("lyric_token_idss")[
                                           sample_idx_0based:sample_idx_0based + 1]
                    }

                    # Verify no None values in the sliced dict
                    if any(v is None for v in extra_tensor_data.values()):
                        extra_tensor_data = None
                except Exception as e:
                    print(f"Error slicing tensor data for score: {e}")
                    extra_tensor_data = None

    # Calculate score using historical parameters
    score_display = calculate_score_handler(
        llm_handler,
        audio_codes_str, caption, lyrics, lm_metadata,
        bpm, key_scale, time_signature, audio_duration, vocal_language,
        score_scale,
        dit_handler,
        extra_tensor_data,
        inference_steps,
    )
    
    # Update batch_queue with the calculated score
    if current_batch_index in batch_queue:
        if "scores" not in batch_queue[current_batch_index]:
            batch_queue[current_batch_index]["scores"] = [""] * 8
        batch_queue[current_batch_index]["scores"][sample_idx - 1] = score_display
    
    # Return: score_display (with visible=True), accordion skip, batch_queue
    return (
        gr.update(value=score_display, visible=True),  # score_display with content, keep visible=True
        gr.skip(),  # details_accordion - don't change visibility
        batch_queue
    )


def generate_lrc_handler(dit_handler, sample_idx, current_batch_index, batch_queue, vocal_language, inference_steps):
    """
    Generate LRC timestamps for a specific audio sample.

    This function retrieves cached generation data from batch_queue and calls
    the handler's get_lyric_timestamp method to generate LRC format lyrics.
    
    NEW APPROACH: Only update lrc_display, NOT audio subtitles directly!
    Audio subtitles will be updated via lrc_display.change() event.
    This decouples audio value updates from subtitle updates, avoiding flickering.

    Args:
        dit_handler: DiT handler instance with get_lyric_timestamp method
        sample_idx: Which sample to generate LRC for (1-8)
        current_batch_index: Current batch index in batch_queue
        batch_queue: Dictionary storing all batch generation data
        vocal_language: Language code for lyrics
        inference_steps: Number of inference steps used in generation

    Returns:
        Tuple of (lrc_display_update, details_accordion_update, batch_queue)
        Note: No audio_update - subtitles updated via lrc_display.change()
    """
    import torch
    
    if current_batch_index not in batch_queue:
        return gr.skip(), gr.skip(), batch_queue

    batch_data = batch_queue[current_batch_index]
    extra_outputs = batch_data.get("extra_outputs", {})

    # Check if required data is available
    # Keep visible=True to ensure .change() event is properly triggered
    if not extra_outputs:
        return gr.update(value=t("messages.lrc_no_extra_outputs"), visible=True), gr.skip(), batch_queue
    
    pred_latents = extra_outputs.get("pred_latents")
    encoder_hidden_states = extra_outputs.get("encoder_hidden_states")
    encoder_attention_mask = extra_outputs.get("encoder_attention_mask")
    context_latents = extra_outputs.get("context_latents")
    lyric_token_idss = extra_outputs.get("lyric_token_idss")
    
    if any(x is None for x in [pred_latents, encoder_hidden_states, encoder_attention_mask, context_latents, lyric_token_idss]):
        return gr.update(value=t("messages.lrc_missing_tensors"), visible=True), gr.skip(), batch_queue
    
    # Adjust sample_idx to 0-based
    sample_idx_0based = sample_idx - 1
    
    # Check if sample exists in batch
    batch_size = pred_latents.shape[0]
    if sample_idx_0based >= batch_size:
        return gr.update(value=t("messages.lrc_sample_not_exist"), visible=True), gr.skip(), batch_queue
    
    # Extract the specific sample's data
    try:
        # Get audio duration from batch data
        params = batch_data.get("generation_params", {})
        audio_duration = params.get("audio_duration", -1)
        
        # Calculate duration from latents if not specified
        if audio_duration is None or audio_duration <= 0:
            # latent_length * frames_per_second_ratio ≈ audio_duration
            # Assuming 25 Hz latent rate: latent_length / 25 = duration
            latent_length = pred_latents.shape[1]
            audio_duration = latent_length / 25.0  # 25 Hz latent rate
        
        # Get the sample's data (keep batch dimension for handler)
        sample_pred_latent = pred_latents[sample_idx_0based:sample_idx_0based+1]
        sample_encoder_hidden_states = encoder_hidden_states[sample_idx_0based:sample_idx_0based+1]
        sample_encoder_attention_mask = encoder_attention_mask[sample_idx_0based:sample_idx_0based+1]
        sample_context_latents = context_latents[sample_idx_0based:sample_idx_0based+1]
        sample_lyric_token_ids = lyric_token_idss[sample_idx_0based:sample_idx_0based+1]
        
        # Call handler to generate timestamps
        result = dit_handler.get_lyric_timestamp(
            pred_latent=sample_pred_latent,
            encoder_hidden_states=sample_encoder_hidden_states,
            encoder_attention_mask=sample_encoder_attention_mask,
            context_latents=sample_context_latents,
            lyric_token_ids=sample_lyric_token_ids,
            total_duration_seconds=float(audio_duration),
            vocal_language=vocal_language or "en",
            inference_steps=int(inference_steps),
            seed=42,  # Use fixed seed for reproducibility
        )
        
        if result.get("success"):
            lrc_text = result.get("lrc_text", "")
            if not lrc_text:
                return gr.update(value=t("messages.lrc_empty_result"), visible=True), gr.skip(), batch_queue
            
            # Store LRC in batch_queue for later retrieval when switching batches
            if "lrcs" not in batch_queue[current_batch_index]:
                batch_queue[current_batch_index]["lrcs"] = [""] * 8
            batch_queue[current_batch_index]["lrcs"][sample_idx_0based] = lrc_text
            
            # Convert LRC to VTT file and store path for batch navigation (consistent with VTT-based approach)
            vtt_path = lrc_to_vtt_file(lrc_text, total_duration=float(audio_duration))
            if "subtitles" not in batch_queue[current_batch_index]:
                batch_queue[current_batch_index]["subtitles"] = [None] * 8
            batch_queue[current_batch_index]["subtitles"][sample_idx_0based] = vtt_path
            
            # Return: lrc_display, details_accordion, batch_queue
            # NEW APPROACH: Only update lrc_display, NOT audio subtitles!
            # Audio subtitles will be updated via lrc_display.change() event.
            # Keep visible=True to ensure .change() event is properly triggered
            return (
                gr.update(value=lrc_text, visible=True),
                gr.skip(),
                batch_queue
            )
        else:
            error_msg = result.get("error", "Unknown error")
            return gr.update(value=f"❌ {error_msg}", visible=True), gr.skip(), batch_queue
            
    except Exception as e:
        logger.exception("[generate_lrc_handler] Error generating LRC")
        return gr.update(value=f"❌ Error: {str(e)}", visible=True), gr.skip(), batch_queue


def update_audio_subtitles_from_lrc(lrc_text: str, audio_duration: float = None):
    """
    Update Audio component's subtitles based on LRC text content.
    
    This function generates a VTT file from LRC text and passes the file path
    to Gradio, which renders it as a native <track src="..."> element.
    This is more stable than JS-based subtitle injection.
    
    Args:
        lrc_text: LRC format lyrics string from lrc_display textbox
        audio_duration: Optional audio duration for calculating last line's end time
        
    Returns:
        gr.update for the Audio component with subtitles file path
    """
    # If LRC text is empty, clear subtitles
    if not lrc_text or not lrc_text.strip():
        return gr.update(subtitles=None)
    
    # Convert LRC to VTT file and get file path
    vtt_path = lrc_to_vtt_file(lrc_text, total_duration=audio_duration)
    
    # Return file path for native <track> rendering
    # If conversion failed, clear subtitles
    return gr.update(subtitles=vtt_path)


def capture_current_params(
    captions, lyrics, bpm, key_scale, time_signature, vocal_language,
    inference_steps, guidance_scale, random_seed_checkbox, seed,
    reference_audio, audio_duration, batch_size_input, src_audio,
    text2music_audio_code_string, repainting_start, repainting_end,
    instruction_display_gen, audio_cover_strength, task_type,
    use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method, custom_timesteps, audio_format, lm_temperature,
    think_checkbox, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
    use_cot_metas, use_cot_caption, use_cot_language,
    constrained_decoding_debug, allow_lm_batch, auto_score, auto_lrc, score_scale, lm_batch_chunk_size,
    track_name, complete_track_classes,
    custom_track_name, scratchpad
):
    """Capture current UI parameters for next batch generation
    
    IMPORTANT: For AutoGen batches, we clear audio codes to ensure:
    - Thinking mode: LM generates NEW codes for each batch
    - Non-thinking mode: DiT generates with different random seeds
    """
    return {
        "captions": captions,
        "lyrics": lyrics,
        "bpm": bpm,
        "key_scale": key_scale,
        "time_signature": time_signature,
        "vocal_language": vocal_language,
        "inference_steps": inference_steps,
        "guidance_scale": guidance_scale,
        "random_seed_checkbox": True,  # Always use random for AutoGen batches
        "seed": seed,
        "reference_audio": reference_audio,
        "audio_duration": audio_duration,
        "batch_size_input": batch_size_input,
        "src_audio": src_audio,
        "text2music_audio_code_string": "",  # CLEAR codes for next batch! Let LM regenerate or DiT use new seeds
        "repainting_start": repainting_start,
        "repainting_end": repainting_end,
        "instruction_display_gen": instruction_display_gen,
        "audio_cover_strength": audio_cover_strength,
        "task_type": task_type,
        "use_adg": use_adg,
        "cfg_interval_start": cfg_interval_start,
        "cfg_interval_end": cfg_interval_end,
        "shift": shift,
        "infer_method": infer_method,
        "custom_timesteps": custom_timesteps,
        "audio_format": audio_format,
        "lm_temperature": lm_temperature,
        "think_checkbox": think_checkbox,
        "lm_cfg_scale": lm_cfg_scale,
        "lm_top_k": lm_top_k,
        "lm_top_p": lm_top_p,
        "lm_negative_prompt": lm_negative_prompt,
        "use_cot_metas": use_cot_metas,
        "use_cot_caption": use_cot_caption,
        "use_cot_language": use_cot_language,
        "constrained_decoding_debug": constrained_decoding_debug,
        "allow_lm_batch": allow_lm_batch,
        "auto_score": auto_score,
        "auto_lrc": auto_lrc,
        "score_scale": score_scale,
        "lm_batch_chunk_size": lm_batch_chunk_size,
        "track_name": track_name,
        "complete_track_classes": complete_track_classes,
        "custom_track_name": custom_track_name,
        "scratchpad": scratchpad,
    }


def generate_with_batch_management(
    dit_handler, llm_handler,
    captions, lyrics, bpm, key_scale, time_signature, vocal_language,
    inference_steps, guidance_scale, random_seed_checkbox, seed,
    reference_audio, audio_duration, batch_size_input, src_audio,
    text2music_audio_code_string, repainting_start, repainting_end,
    instruction_display_gen, audio_cover_strength, task_type,
    use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method, custom_timesteps, audio_format, lm_temperature,
    think_checkbox, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
    use_cot_metas, use_cot_caption, use_cot_language, is_format_caption,
    constrained_decoding_debug,
    allow_lm_batch,
    auto_score,
    auto_lrc,
    score_scale,
    lm_batch_chunk_size,
    track_name,
    complete_track_classes,
    custom_track_name,
    scratchpad,
    autogen_checkbox,
    current_batch_index,
    total_batches,
    batch_queue,
    generation_params_state,
    progress=gr.Progress(track_tqdm=True)
):
    """
    Wrapper for generate_with_progress that adds batch queue management
    """
    # Call the original generation function
    generator = generate_with_progress(
        dit_handler, llm_handler,
        captions, lyrics, bpm, key_scale, time_signature, vocal_language,
        inference_steps, guidance_scale, random_seed_checkbox, seed,
        reference_audio, audio_duration, batch_size_input, src_audio,
        text2music_audio_code_string, repainting_start, repainting_end,
        instruction_display_gen, audio_cover_strength, task_type,
        use_adg, cfg_interval_start, cfg_interval_end, shift, infer_method, custom_timesteps, audio_format, lm_temperature,
        think_checkbox, lm_cfg_scale, lm_top_k, lm_top_p, lm_negative_prompt,
        use_cot_metas, use_cot_caption, use_cot_language, is_format_caption,
        constrained_decoding_debug,
        allow_lm_batch,
        auto_score,
        auto_lrc,
        score_scale,
        lm_batch_chunk_size,
        custom_track_name,
        scratchpad,
        progress
    )
    final_result_from_inner = None
    for partial_result in generator:
        final_result_from_inner = partial_result
        # Progressive yields disabled on Windows to prevent UI freeze
        # On other platforms, yield progress updates normally
        if not IS_WINDOWS:
            # current_batch_index, total_batches, batch_queue, next_params,
            # batch_indicator_text, prev_btn, next_btn, next_status, restore_btn
            # Slice off extra_outputs and raw_codes_list (last 2 items) before re-yielding to UI
            ui_result = partial_result[:-2] if len(partial_result) > 47 else (partial_result[:-1] if len(partial_result) > 46 else partial_result)
            yield ui_result + (
                gr.skip(), gr.skip(), gr.skip(), gr.skip(),
                gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip()
            )
    result = final_result_from_inner
    all_audio_paths = result[8]

    if all_audio_paths is None:
        # Slice off extra_outputs and raw_codes_list before yielding to UI
        ui_result = result[:-2] if len(result) > 47 else (result[:-1] if len(result) > 46 else result)
        yield ui_result + (
            gr.skip(), gr.skip(), gr.skip(), gr.skip(), 
            gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip()
        )
        return

    # Extract results from generation (使用 result 下标访问)
    # New structure after UI refactor (with lrc_display added):
    # 0-7: audio_outputs, 8: all_audio_paths, 9: generation_info, 10: status, 11: seed
    # 12-19: scores, 20-27: codes_display, 28-35: details_accordion, 36-43: lrc_display
    # 44: lm_metadata, 45: is_format_caption, 46: extra_outputs, 47: raw_codes_list
    generation_info = result[9]
    seed_value_for_ui = result[11]
    lm_generated_metadata = result[44]
    
    # Extract raw codes list directly (index 47)
    raw_codes_list = result[47] if len(result) > 47 else [""] * 8
    generated_codes_batch = raw_codes_list if isinstance(raw_codes_list, list) else [""] * 8
    generated_codes_single = generated_codes_batch[0] if generated_codes_batch else ""

    # Determine which codes to store based on mode
    if allow_lm_batch and batch_size_input >= 2:
        codes_to_store = generated_codes_batch[:int(batch_size_input)]
    else:
        codes_to_store = generated_codes_single

    # Save parameters for history
    saved_params = {
        "captions": captions,
        "lyrics": lyrics,
        "bpm": bpm,
        "key_scale": key_scale,
        "time_signature": time_signature,
        "vocal_language": vocal_language,
        "inference_steps": inference_steps,
        "guidance_scale": guidance_scale,
        "random_seed_checkbox": random_seed_checkbox,
        "seed": seed,
        "reference_audio": reference_audio,
        "audio_duration": audio_duration,
        "batch_size_input": batch_size_input,
        "src_audio": src_audio,
        "text2music_audio_code_string": text2music_audio_code_string,
        "repainting_start": repainting_start,
        "repainting_end": repainting_end,
        "instruction_display_gen": instruction_display_gen,
        "audio_cover_strength": audio_cover_strength,
        "task_type": task_type,
        "use_adg": use_adg,
        "cfg_interval_start": cfg_interval_start,
        "cfg_interval_end": cfg_interval_end,
        "shift": shift,
        "infer_method": infer_method,
        "audio_format": audio_format,
        "lm_temperature": lm_temperature,
        "think_checkbox": think_checkbox,
        "lm_cfg_scale": lm_cfg_scale,
        "lm_top_k": lm_top_k,
        "lm_top_p": lm_top_p,
        "lm_negative_prompt": lm_negative_prompt,
        "use_cot_metas": use_cot_metas,
        "use_cot_caption": use_cot_caption,
        "use_cot_language": use_cot_language,
        "constrained_decoding_debug": constrained_decoding_debug,
        "allow_lm_batch": allow_lm_batch,
        "auto_score": auto_score,
        "auto_lrc": auto_lrc,
        "score_scale": score_scale,
        "lm_batch_chunk_size": lm_batch_chunk_size,
        "track_name": track_name,
        "complete_track_classes": complete_track_classes,
        "custom_track_name": custom_track_name,
        "scratchpad": scratchpad,
    }
    
    # Next batch parameters (with cleared codes & random seed)
    # Next batch parameters
    next_params = saved_params.copy()
    next_params["text2music_audio_code_string"] = ""
    next_params["random_seed_checkbox"] = True
    
    # Extract extra_outputs from result tuple (index 46 after adding lrc_display)
    # Note: index 47 is raw_codes_list which we already extracted above
    # Must check both length AND that the value is not None (intermediate yields use None as placeholder)
    extra_outputs_from_result = result[46] if len(result) > 46 and result[46] is not None else {}
    
    # Store current batch in queue
    batch_queue = store_batch_in_queue(
        batch_queue,
        current_batch_index,
        all_audio_paths,
        generation_info,
        seed_value_for_ui,
        codes=codes_to_store,
        allow_lm_batch=allow_lm_batch,
        batch_size=int(batch_size_input),
        generation_params=saved_params,
        lm_generated_metadata=lm_generated_metadata,
        extra_outputs=extra_outputs_from_result,  # Store extra outputs for LRC generation
        status="completed"
    )
    
    # Extract auto_lrc results from extra_outputs (generated in generate_with_progress)
    if auto_lrc and extra_outputs_from_result:
        lrcs_from_extra = extra_outputs_from_result.get("lrcs", [""] * 8)
        subtitles_from_extra = extra_outputs_from_result.get("subtitles", [None] * 8)
        batch_queue[current_batch_index]["lrcs"] = lrcs_from_extra
        batch_queue[current_batch_index]["subtitles"] = subtitles_from_extra
    
    # Update batch counters
    total_batches = max(total_batches, current_batch_index + 1)
    
    # Update batch indicator
    batch_indicator_text = update_batch_indicator(current_batch_index, total_batches)
    
    # Update navigation button states
    can_go_previous, can_go_next = update_navigation_buttons(current_batch_index, total_batches)
    
    # Prepare next batch status message
    next_batch_status_text = ""
    if autogen_checkbox:
        next_batch_status_text = t("messages.autogen_enabled")

    # 4. Yield final result (includes Batch UI updates)
    # Extract core 46 items from result (0-45)
    # Structure: 0-7: audio, 8: all_audio_paths, 9: generation_info, 10: status, 11: seed,
    # 12-19: scores, 20-27: codes_display, 28-35: accordions, 36-43: lrc_display,
    # 44: lm_metadata, 45: is_format_caption
    # (46: extra_outputs, 47: raw_codes_list are NOT included in UI yields)
    ui_core = result[:46]

    logger.info(f"[generate_with_batch_management] Final yield: {len(ui_core)} core + 9 state")

    yield tuple(ui_core) + (
        current_batch_index,
        total_batches,
        batch_queue,
        next_params,
        batch_indicator_text,
        gr.update(interactive=can_go_previous),
        gr.update(interactive=can_go_next),
        next_batch_status_text,
        gr.update(interactive=True),
    )

    # Small delay to ensure Gradio processes final updates (Issue #113)
    time_module.sleep(0.1)


def generate_next_batch_background(
    dit_handler,
    llm_handler,
    autogen_enabled,
    generation_params,
    current_batch_index,
    total_batches,
    batch_queue,
    is_format_caption,
    progress=gr.Progress(track_tqdm=True)
):
    """
    Generate next batch in background if AutoGen is enabled
    """
    # Early return if AutoGen not enabled
    if not autogen_enabled:
        return (
            batch_queue,
            total_batches,
            "",
            gr.update(interactive=False),
        )
    
    # Calculate next batch index
    next_batch_idx = current_batch_index + 1
    
    # Check if next batch already exists
    if next_batch_idx in batch_queue and batch_queue[next_batch_idx].get("status") == "completed":
        return (
            batch_queue,
            total_batches,
            t("messages.batch_ready", n=next_batch_idx + 1),
            gr.update(interactive=True),
        )
    
    # Update total batches count
    total_batches = next_batch_idx + 1
    
    gr.Info(t("messages.batch_generating", n=next_batch_idx + 1))
    
    # Generate next batch using stored parameters
    params = generation_params.copy()
    
    # DEBUG LOGGING: Log all parameters used for background generation
    logger.info(f"========== BACKGROUND GENERATION BATCH {next_batch_idx + 1} ==========")
    logger.info(f"Parameters used for background generation:")
    logger.info(f"  - captions: {params.get('captions', 'N/A')}")
    logger.info(f"  - lyrics: {params.get('lyrics', 'N/A')[:50]}..." if params.get('lyrics') else "  - lyrics: N/A")
    logger.info(f"  - bpm: {params.get('bpm')}")
    logger.info(f"  - batch_size_input: {params.get('batch_size_input')}")
    logger.info(f"  - allow_lm_batch: {params.get('allow_lm_batch')}")
    logger.info(f"  - think_checkbox: {params.get('think_checkbox')}")
    logger.info(f"  - lm_temperature: {params.get('lm_temperature')}")
    logger.info(f"  - track_name: {params.get('track_name')}")
    logger.info(f"  - complete_track_classes: {params.get('complete_track_classes')}")
    logger.info(f"  - text2music_audio_code_string: {'<CLEARED>' if params.get('text2music_audio_code_string') == '' else 'HAS_VALUE'}")
    logger.info(f"=========================================================")
    
    # Add error handling for background generation
    try:
        # Ensure all parameters have default values to prevent None errors
        params.setdefault("captions", "")
        params.setdefault("lyrics", "")
        params.setdefault("bpm", None)
        params.setdefault("key_scale", "")
        params.setdefault("time_signature", "")
        params.setdefault("vocal_language", "unknown")
        params.setdefault("inference_steps", 8)
        params.setdefault("guidance_scale", 7.0)
        params.setdefault("random_seed_checkbox", True)
        params.setdefault("seed", "-1")
        params.setdefault("reference_audio", None)
        params.setdefault("audio_duration", -1)
        params.setdefault("batch_size_input", 2)
        params.setdefault("src_audio", None)
        params.setdefault("text2music_audio_code_string", "")
        params.setdefault("repainting_start", 0.0)
        params.setdefault("repainting_end", -1)
        params.setdefault("instruction_display_gen", "")
        params.setdefault("audio_cover_strength", 1.0)
        params.setdefault("task_type", "text2music")
        params.setdefault("use_adg", False)
        params.setdefault("cfg_interval_start", 0.0)
        params.setdefault("cfg_interval_end", 1.0)
        params.setdefault("shift", 1.0)
        params.setdefault("infer_method", "ode")
        params.setdefault("custom_timesteps", "")
        params.setdefault("audio_format", "mp3")
        params.setdefault("lm_temperature", 0.85)
        params.setdefault("think_checkbox", True)
        params.setdefault("lm_cfg_scale", 2.0)
        params.setdefault("lm_top_k", 0)
        params.setdefault("lm_top_p", 0.9)
        params.setdefault("lm_negative_prompt", "NO USER INPUT")
        params.setdefault("use_cot_metas", True)
        params.setdefault("use_cot_caption", True)
        params.setdefault("use_cot_language", True)
        params.setdefault("constrained_decoding_debug", False)
        params.setdefault("allow_lm_batch", True)
        params.setdefault("auto_score", False)
        params.setdefault("auto_lrc", False)
        params.setdefault("score_scale", 0.5)
        params.setdefault("lm_batch_chunk_size", 8)
        params.setdefault("track_name", None)
        params.setdefault("complete_track_classes", [])
        params.setdefault("custom_track_name", "")
        
        # Call generate_with_progress with the saved parameters
        # Note: generate_with_progress is a generator, need to iterate through it
        # For AutoGen background batches, always skip metas COT since we want to 
        # generate NEW audio codes with new seeds, not regenerate the same metas
        generator = generate_with_progress(
            dit_handler,
            llm_handler,
            captions=params.get("captions"),
            lyrics=params.get("lyrics"),
            bpm=params.get("bpm"),
            key_scale=params.get("key_scale"),
            time_signature=params.get("time_signature"),
            vocal_language=params.get("vocal_language"),
            inference_steps=params.get("inference_steps"),
            guidance_scale=params.get("guidance_scale"),
            random_seed_checkbox=params.get("random_seed_checkbox"),
            seed=params.get("seed"),
            reference_audio=params.get("reference_audio"),
            audio_duration=params.get("audio_duration"),
            batch_size_input=params.get("batch_size_input"),
            src_audio=params.get("src_audio"),
            text2music_audio_code_string=params.get("text2music_audio_code_string"),
            repainting_start=params.get("repainting_start"),
            repainting_end=params.get("repainting_end"),
            instruction_display_gen=params.get("instruction_display_gen"),
            audio_cover_strength=params.get("audio_cover_strength"),
            task_type=params.get("task_type"),
            use_adg=params.get("use_adg"),
            cfg_interval_start=params.get("cfg_interval_start"),
            cfg_interval_end=params.get("cfg_interval_end"),
            shift=params.get("shift"),
            infer_method=params.get("infer_method"),
            custom_timesteps=params.get("custom_timesteps"),
            audio_format=params.get("audio_format"),
            lm_temperature=params.get("lm_temperature"),
            think_checkbox=params.get("think_checkbox"),
            lm_cfg_scale=params.get("lm_cfg_scale"),
            lm_top_k=params.get("lm_top_k"),
            lm_top_p=params.get("lm_top_p"),
            lm_negative_prompt=params.get("lm_negative_prompt"),
            use_cot_metas=params.get("use_cot_metas"),
            use_cot_caption=params.get("use_cot_caption"),
            use_cot_language=params.get("use_cot_language"),
            is_format_caption=is_format_caption,  # Pass through - will skip metas COT if True
            constrained_decoding_debug=params.get("constrained_decoding_debug"),
            allow_lm_batch=params.get("allow_lm_batch"),
            auto_score=params.get("auto_score"),
            auto_lrc=params.get("auto_lrc"),
            score_scale=params.get("score_scale"),
            lm_batch_chunk_size=params.get("lm_batch_chunk_size"),
            custom_track_name=params.get("custom_track_name"),
            scratchpad=params.get("scratchpad"),
            progress=progress
        )
        
        # Consume generator to get final result (similar to generate_with_batch_management)
        final_result = None
        for partial_result in generator:
            final_result = partial_result
        
        # Extract results from final_result
        # New structure after UI refactor (with lrc_display added):
        # 0-7: audio_outputs, 8: all_audio_paths, 9: generation_info, 10: status, 11: seed
        # 12-19: scores, 20-27: codes_display, 28-35: details_accordion, 36-43: lrc_display
        # 44: lm_metadata, 45: is_format_caption, 46: extra_outputs, 47: raw_codes_list
        all_audio_paths = final_result[8]  # generated_audio_batch
        generation_info = final_result[9]
        seed_value_for_ui = final_result[11]
        lm_generated_metadata = final_result[44]
        
        # Extract raw codes list directly (index 47)
        raw_codes_list = final_result[47] if len(final_result) > 47 else [""] * 8
        generated_codes_batch = raw_codes_list if isinstance(raw_codes_list, list) else [""] * 8
        generated_codes_single = generated_codes_batch[0] if generated_codes_batch else ""
        
        # Extract extra_outputs for LRC generation (index 46)
        # Must check both length AND that the value is not None (intermediate yields use None as placeholder)
        extra_outputs_from_bg = final_result[46] if len(final_result) > 46 and final_result[46] is not None else {}
        
        # Extract scores from final_result (indices 12-19)
        # This is critical for auto_score to work when navigating to background-generated batches
        scores_from_bg = []
        for score_idx in range(12, 20):
            if score_idx < len(final_result):
                score_val = final_result[score_idx]
                # Handle gr.update objects - extract value if present, otherwise use empty string
                if hasattr(score_val, 'value'):
                    scores_from_bg.append(score_val.value if score_val.value else "")
                elif isinstance(score_val, str):
                    scores_from_bg.append(score_val)
                else:
                    scores_from_bg.append("")
            else:
                scores_from_bg.append("")
        
        # Determine which codes to store
        batch_size = params.get("batch_size_input", 2)
        allow_lm_batch = params.get("allow_lm_batch", False)
        if allow_lm_batch and batch_size >= 2:
            codes_to_store = generated_codes_batch[:int(batch_size)]
        else:
            codes_to_store = generated_codes_single
        
        # DEBUG LOGGING: Log codes extraction and storage
        logger.info(f"Codes extraction for Batch {next_batch_idx + 1}:")
        logger.info(f"  - allow_lm_batch: {allow_lm_batch}")
        logger.info(f"  - batch_size: {batch_size}")
        logger.info(f"  - generated_codes_single exists: {bool(generated_codes_single)}")
        logger.info(f"  - extra_outputs_from_bg exists: {extra_outputs_from_bg is not None}")
        logger.info(f"  - scores_from_bg: {[bool(s) for s in scores_from_bg]}")
        if isinstance(codes_to_store, list):
            logger.info(f"  - codes_to_store: LIST with {len(codes_to_store)} items")
            for idx, code in enumerate(codes_to_store):
                logger.info(f"    * Sample {idx + 1}: {len(code) if code else 0} chars")
        else:
            logger.info(f"  - codes_to_store: STRING with {len(codes_to_store) if codes_to_store else 0} chars")
        
        # Store next batch in queue with codes, batch settings, scores, and ALL generation params
        batch_queue = store_batch_in_queue(
            batch_queue,
            next_batch_idx,
            all_audio_paths,
            generation_info,
            seed_value_for_ui,
            codes=codes_to_store,
            scores=scores_from_bg,  # FIX: Now passing scores from background generation
            allow_lm_batch=allow_lm_batch,
            batch_size=int(batch_size),
            generation_params=params,
            lm_generated_metadata=lm_generated_metadata,
            extra_outputs=extra_outputs_from_bg,  # Now properly extracted from generation result
            status="completed"
        )
        
        # FIX: Extract auto_lrc results from extra_outputs (same as generate_with_batch_management)
        # This ensures LRC and subtitles are properly stored for batch navigation
        auto_lrc = params.get("auto_lrc", False)
        if auto_lrc and extra_outputs_from_bg:
            lrcs_from_extra = extra_outputs_from_bg.get("lrcs", [""] * 8)
            subtitles_from_extra = extra_outputs_from_bg.get("subtitles", [None] * 8)
            batch_queue[next_batch_idx]["lrcs"] = lrcs_from_extra
            batch_queue[next_batch_idx]["subtitles"] = subtitles_from_extra
            logger.info(f"  - auto_lrc results stored: {[bool(l) for l in lrcs_from_extra]}")
        
        logger.info(f"Batch {next_batch_idx + 1} stored in queue successfully")
        
        # Success message
        next_batch_status = t("messages.batch_ready", n=next_batch_idx + 1)
        
        # Enable next button now that batch is ready
        return (
            batch_queue,
            total_batches,
            next_batch_status,
            gr.update(interactive=True),
        )
    except Exception as e:
        # Handle generation errors
        import traceback
        error_msg = t("messages.batch_failed", error=str(e))
        gr.Warning(error_msg)
        
        # Mark batch as failed in queue
        batch_queue[next_batch_idx] = {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        
        return (
            batch_queue,
            total_batches,
            error_msg,
            gr.update(interactive=False),
        )


def navigate_to_previous_batch(current_batch_index, batch_queue):
    """Navigate to previous batch (Result View Only - Never touches Input UI)
    
    Uses two-step yield to avoid subtitle flickering:
    1. First yield: audio + clear LRC (triggers .change() to clear subtitles)
    2. Sleep 50ms (let audio load)
    3. Second yield: skip audio + set actual LRC (triggers .change() to set subtitles)
    """
    if current_batch_index <= 0:
        gr.Warning(t("messages.at_first_batch"))
        yield tuple([gr.update()] * 48)  # 8 audio + 2 batch files/info + 1 index + 1 indicator + 2 btns + 1 status + 8 scores + 8 codes + 8 lrc + 8 accordions + 1 restore
        return
    
    # Move to previous batch
    new_batch_index = current_batch_index - 1
    
    # Load batch data from queue
    if new_batch_index not in batch_queue:
        gr.Warning(t("messages.batch_not_found", n=new_batch_index + 1))
        yield tuple([gr.update()] * 48)
        return
    
    batch_data = batch_queue[new_batch_index]
    audio_paths = batch_data.get("audio_paths", [])
    generation_info_text = batch_data.get("generation_info", "")

    # Prepare audio outputs (up to 8)
    real_audio_paths = [p for p in audio_paths if not p.lower().endswith('.json')]

    audio_updates = []
    for idx in range(8):
        if idx < len(real_audio_paths):
            audio_path = real_audio_paths[idx].replace("\\", "/")  # Normalize path
            audio_updates.append(gr.update(value=audio_path))
        else:
            audio_updates.append(gr.update(value=None))

    # Update batch indicator
    total_batches = len(batch_queue)
    batch_indicator_text = update_batch_indicator(new_batch_index, total_batches)
    
    # Update button states
    can_go_previous, can_go_next = update_navigation_buttons(new_batch_index, total_batches)
    
    # Restore score displays from batch queue
    stored_scores = batch_data.get("scores", [""] * 8)
    score_displays = stored_scores if stored_scores else [""] * 8
    
    # Restore LRC displays from batch queue (clear if not stored)
    stored_lrcs = batch_data.get("lrcs", [""] * 8)
    lrc_displays = stored_lrcs if stored_lrcs else [""] * 8
    
    # Restore codes display from batch queue
    stored_codes = batch_data.get("codes", "")
    stored_allow_lm_batch = batch_data.get("allow_lm_batch", False)
    batch_size = batch_data.get("batch_size", 2)
    
    codes_display_updates = []
    lrc_display_updates = []
    lrc_clear_updates = []  # For first yield - clear LRC
    details_accordion_updates = []
    for i in range(8):
        if stored_allow_lm_batch and isinstance(stored_codes, list):
            code_str = stored_codes[i] if i < len(stored_codes) else ""
        else:
            code_str = stored_codes if isinstance(stored_codes, str) and i == 0 else ""
        
        lrc_str = lrc_displays[i] if i < len(lrc_displays) else ""
        score_str = score_displays[i] if i < len(score_displays) else ""
        
        # Keep visible=True to ensure .change() event is properly triggered
        codes_display_updates.append(gr.update(value=code_str, visible=True))
        lrc_display_updates.append(gr.update(value=lrc_str, visible=True))
        lrc_clear_updates.append(gr.update(value="", visible=True))  # Clear first
        details_accordion_updates.append(gr.skip())  # Don't change accordion visibility
    
    # ============== STEP 1: Yield audio + CLEAR LRC ==============
    yield (
        audio_updates[0], audio_updates[1], audio_updates[2], audio_updates[3],
        audio_updates[4], audio_updates[5], audio_updates[6], audio_updates[7],
        audio_paths, generation_info_text, new_batch_index, batch_indicator_text,
        gr.update(interactive=can_go_previous), gr.update(interactive=can_go_next),
        t("messages.viewing_batch", n=new_batch_index + 1),
        score_displays[0], score_displays[1], score_displays[2], score_displays[3],
        score_displays[4], score_displays[5], score_displays[6], score_displays[7],
        codes_display_updates[0], codes_display_updates[1], codes_display_updates[2], codes_display_updates[3],
        codes_display_updates[4], codes_display_updates[5], codes_display_updates[6], codes_display_updates[7],
        # LRC display - CLEAR first (triggers .change() to clear subtitles)
        lrc_clear_updates[0], lrc_clear_updates[1], lrc_clear_updates[2], lrc_clear_updates[3],
        lrc_clear_updates[4], lrc_clear_updates[5], lrc_clear_updates[6], lrc_clear_updates[7],
        details_accordion_updates[0], details_accordion_updates[1], details_accordion_updates[2], details_accordion_updates[3],
        details_accordion_updates[4], details_accordion_updates[5], details_accordion_updates[6], details_accordion_updates[7],
        gr.update(interactive=True),
    )
    
    # Wait for audio to load before setting subtitles
    time_module.sleep(0.05)
    
    # ============== STEP 2: Yield skip audio + SET actual LRC ==============
    skip_audio = [gr.skip() for _ in range(8)]
    skip_scores = [gr.skip() for _ in range(8)]
    skip_codes = [gr.skip() for _ in range(8)]
    skip_accordions = [gr.skip() for _ in range(8)]
    
    yield (
        skip_audio[0], skip_audio[1], skip_audio[2], skip_audio[3],
        skip_audio[4], skip_audio[5], skip_audio[6], skip_audio[7],
        gr.skip(), gr.skip(), gr.skip(), gr.skip(),  # audio_paths, generation_info, batch_index, indicator
        gr.skip(), gr.skip(),  # prev/next buttons
        gr.skip(),  # status
        skip_scores[0], skip_scores[1], skip_scores[2], skip_scores[3],
        skip_scores[4], skip_scores[5], skip_scores[6], skip_scores[7],
        skip_codes[0], skip_codes[1], skip_codes[2], skip_codes[3],
        skip_codes[4], skip_codes[5], skip_codes[6], skip_codes[7],
        # LRC display - SET actual content (triggers .change() to set subtitles)
        lrc_display_updates[0], lrc_display_updates[1], lrc_display_updates[2], lrc_display_updates[3],
        lrc_display_updates[4], lrc_display_updates[5], lrc_display_updates[6], lrc_display_updates[7],
        skip_accordions[0], skip_accordions[1], skip_accordions[2], skip_accordions[3],
        skip_accordions[4], skip_accordions[5], skip_accordions[6], skip_accordions[7],
        gr.skip(),  # restore button
    )


def navigate_to_next_batch(autogen_enabled, current_batch_index, total_batches, batch_queue):
    """Navigate to next batch (Result View Only - Never touches Input UI)
    
    Uses two-step yield to avoid subtitle flickering:
    1. First yield: audio + clear LRC (triggers .change() to clear subtitles)
    2. Sleep 50ms (let audio load)
    3. Second yield: skip audio + set actual LRC (triggers .change() to set subtitles)
    """
    if current_batch_index >= total_batches - 1:
        gr.Warning(t("messages.at_last_batch"))
        yield tuple([gr.update()] * 49)  # 8 audio + 2 batch files/info + 1 index + 1 indicator + 2 btns + 1 status + 1 next_status + 8 scores + 8 codes + 8 lrc + 8 accordions + 1 restore
        return
    
    # Move to next batch
    new_batch_index = current_batch_index + 1
    
    # Load batch data from queue
    if new_batch_index not in batch_queue:
        gr.Warning(t("messages.batch_not_found", n=new_batch_index + 1))
        yield tuple([gr.update()] * 49)
        return
    
    batch_data = batch_queue[new_batch_index]
    audio_paths = batch_data.get("audio_paths", [])
    generation_info_text = batch_data.get("generation_info", "")

    # Prepare audio outputs (up to 8)
    real_audio_paths = [p for p in audio_paths if not p.lower().endswith('.json')]

    audio_updates = []
    for idx in range(8):
        if idx < len(real_audio_paths):
            audio_path = real_audio_paths[idx].replace("\\", "/")  # Normalize path
            audio_updates.append(gr.update(value=audio_path))
        else:
            audio_updates.append(gr.update(value=None))

    # Update batch indicator
    batch_indicator_text = update_batch_indicator(new_batch_index, total_batches)
    
    # Update button states
    can_go_previous, can_go_next = update_navigation_buttons(new_batch_index, total_batches)
    
    # Prepare next batch status message
    next_batch_status_text = ""
    is_latest_view = (new_batch_index == total_batches - 1)
    if autogen_enabled and is_latest_view:
        next_batch_status_text = "🔄 AutoGen will generate next batch in background..."
    
    # Restore score displays from batch queue
    stored_scores = batch_data.get("scores", [""] * 8)
    score_displays = stored_scores if stored_scores else [""] * 8
    
    # Restore LRC displays from batch queue (clear if not stored)
    stored_lrcs = batch_data.get("lrcs", [""] * 8)
    lrc_displays = stored_lrcs if stored_lrcs else [""] * 8
    
    # Restore codes display from batch queue
    stored_codes = batch_data.get("codes", "")
    stored_allow_lm_batch = batch_data.get("allow_lm_batch", False)
    batch_size = batch_data.get("batch_size", 2)
    
    codes_display_updates = []
    lrc_display_updates = []
    lrc_clear_updates = []  # For first yield - clear LRC
    details_accordion_updates = []
    for i in range(8):
        if stored_allow_lm_batch and isinstance(stored_codes, list):
            code_str = stored_codes[i] if i < len(stored_codes) else ""
        else:
            code_str = stored_codes if isinstance(stored_codes, str) and i == 0 else ""
        
        lrc_str = lrc_displays[i] if i < len(lrc_displays) else ""
        
        # Keep visible=True to ensure .change() event is properly triggered
        codes_display_updates.append(gr.update(value=code_str, visible=True))
        lrc_display_updates.append(gr.update(value=lrc_str, visible=True))
        lrc_clear_updates.append(gr.update(value="", visible=True))  # Clear first
        details_accordion_updates.append(gr.skip())  # Don't change accordion visibility
    
    # ============== STEP 1: Yield audio + CLEAR LRC ==============
    yield (
        audio_updates[0], audio_updates[1], audio_updates[2], audio_updates[3],
        audio_updates[4], audio_updates[5], audio_updates[6], audio_updates[7],
        audio_paths, generation_info_text, new_batch_index, batch_indicator_text,
        gr.update(interactive=can_go_previous), gr.update(interactive=can_go_next),
        t("messages.viewing_batch", n=new_batch_index + 1), next_batch_status_text,
        score_displays[0], score_displays[1], score_displays[2], score_displays[3],
        score_displays[4], score_displays[5], score_displays[6], score_displays[7],
        codes_display_updates[0], codes_display_updates[1], codes_display_updates[2], codes_display_updates[3],
        codes_display_updates[4], codes_display_updates[5], codes_display_updates[6], codes_display_updates[7],
        # LRC display - CLEAR first (triggers .change() to clear subtitles)
        lrc_clear_updates[0], lrc_clear_updates[1], lrc_clear_updates[2], lrc_clear_updates[3],
        lrc_clear_updates[4], lrc_clear_updates[5], lrc_clear_updates[6], lrc_clear_updates[7],
        details_accordion_updates[0], details_accordion_updates[1], details_accordion_updates[2], details_accordion_updates[3],
        details_accordion_updates[4], details_accordion_updates[5], details_accordion_updates[6], details_accordion_updates[7],
        gr.update(interactive=True),
    )
    
    # Wait for audio to load before setting subtitles
    time_module.sleep(0.05)
    
    # ============== STEP 2: Yield skip audio + SET actual LRC ==============
    skip_audio = [gr.skip() for _ in range(8)]
    skip_scores = [gr.skip() for _ in range(8)]
    skip_codes = [gr.skip() for _ in range(8)]
    skip_accordions = [gr.skip() for _ in range(8)]
    
    yield (
        skip_audio[0], skip_audio[1], skip_audio[2], skip_audio[3],
        skip_audio[4], skip_audio[5], skip_audio[6], skip_audio[7],
        gr.skip(), gr.skip(), gr.skip(), gr.skip(),  # audio_paths, generation_info, batch_index, indicator
        gr.skip(), gr.skip(),  # prev/next buttons
        gr.skip(), gr.skip(),  # status, next_batch_status
        skip_scores[0], skip_scores[1], skip_scores[2], skip_scores[3],
        skip_scores[4], skip_scores[5], skip_scores[6], skip_scores[7],
        skip_codes[0], skip_codes[1], skip_codes[2], skip_codes[3],
        skip_codes[4], skip_codes[5], skip_codes[6], skip_codes[7],
        # LRC display - SET actual content (triggers .change() to set subtitles)
        lrc_display_updates[0], lrc_display_updates[1], lrc_display_updates[2], lrc_display_updates[3],
        lrc_display_updates[4], lrc_display_updates[5], lrc_display_updates[6], lrc_display_updates[7],
        skip_accordions[0], skip_accordions[1], skip_accordions[2], skip_accordions[3],
        skip_accordions[4], skip_accordions[5], skip_accordions[6], skip_accordions[7],
        gr.skip(),  # restore button
    )


def restore_batch_parameters(current_batch_index, batch_queue):
    """
    Restore parameters from currently viewed batch to Input UI.
    This is the bridge allowing users to "reuse" historical settings.
    """
    if current_batch_index not in batch_queue:
        gr.Warning(t("messages.no_batch_data"))
        return [gr.update()] * 22  # Updated count: 1 codes + 21 other params
    
    batch_data = batch_queue[current_batch_index]
    params = batch_data.get("generation_params", {})
    
    # Extract all parameters with defaults
    captions = params.get("captions", "")
    lyrics = params.get("lyrics", "")
    bpm = params.get("bpm", None)
    key_scale = params.get("key_scale", "")
    time_signature = params.get("time_signature", "")
    vocal_language = params.get("vocal_language", "unknown")
    audio_duration = params.get("audio_duration", -1)
    batch_size_input = params.get("batch_size_input", 2)
    inference_steps = params.get("inference_steps", 8)
    lm_temperature = params.get("lm_temperature", 0.85)
    lm_cfg_scale = params.get("lm_cfg_scale", 2.0)
    lm_top_k = params.get("lm_top_k", 0)
    lm_top_p = params.get("lm_top_p", 0.9)
    think_checkbox = params.get("think_checkbox", True)
    use_cot_caption = params.get("use_cot_caption", True)
    use_cot_language = params.get("use_cot_language", True)
    allow_lm_batch = params.get("allow_lm_batch", True)
    track_name = params.get("track_name", None)
    complete_track_classes = params.get("complete_track_classes", [])
    custom_track_name = params.get("custom_track_name", "")
    scratchpad = params.get("scratchpad", "")
    
    # Extract codes - only restore to single input
    stored_codes = batch_data.get("codes", "")
    if stored_codes:
        if isinstance(stored_codes, list):
            # Batch mode: use first codes for single input
            codes_main = stored_codes[0] if stored_codes else ""
        else:
            # Single mode
            codes_main = stored_codes
    else:
        codes_main = ""
    
    gr.Info(t("messages.params_restored", n=current_batch_index + 1))
    
    return (
        codes_main, captions, lyrics, bpm, key_scale, time_signature,
        vocal_language, audio_duration, batch_size_input, inference_steps,
        lm_temperature, lm_cfg_scale, lm_top_k, lm_top_p, think_checkbox,
        use_cot_caption, use_cot_language, allow_lm_batch,
        track_name, complete_track_classes,
        custom_track_name, scratchpad
    )