"""
Gradio UI Event Handlers Module
Main entry point for setting up all event handlers
"""
import gradio as gr
from typing import Optional
from loguru import logger

# Import handler modules
from . import generation_handlers as gen_h
from . import results_handlers as res_h
from . import training_handlers as train_h
from .wiring import (
    GenerationWiringContext,
    TrainingWiringContext,
    build_mode_ui_outputs,
    register_generation_metadata_handlers,
    register_generation_mode_handlers,
    register_results_aux_handlers,
    register_generation_service_handlers,
)
from acestep.ui.gradio.i18n import t


def setup_event_handlers(demo, dit_handler, llm_handler, dataset_handler, dataset_section, generation_section, results_section):
    """Setup event handlers connecting UI components and business logic"""
    wiring_context = GenerationWiringContext(
        demo=demo,
        dit_handler=dit_handler,
        llm_handler=llm_handler,
        dataset_handler=dataset_handler,
        dataset_section=dataset_section,
        generation_section=generation_section,
        results_section=results_section,
    )
    
    auto_checkbox_inputs, auto_checkbox_outputs = register_generation_service_handlers(
        wiring_context
    )
    mode_ui_outputs = build_mode_ui_outputs(wiring_context)
    register_generation_metadata_handlers(
        wiring_context,
        auto_checkbox_inputs=auto_checkbox_inputs,
        auto_checkbox_outputs=auto_checkbox_outputs,
    )

    register_generation_mode_handlers(
        wiring_context,
        mode_ui_outputs=mode_ui_outputs,
        auto_checkbox_inputs=auto_checkbox_inputs,
        auto_checkbox_outputs=auto_checkbox_outputs,
    )

    # ========== Load/Save Metadata ==========
    generation_section["load_file"].upload(
        fn=lambda file_obj: gen_h.load_metadata(file_obj, llm_handler),
        inputs=[generation_section["load_file"]],
        outputs=[
            generation_section["task_type"],
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["vocal_language"],
            generation_section["bpm"],
            generation_section["key_scale"],
            generation_section["time_signature"],
            generation_section["audio_duration"],
            generation_section["batch_size_input"],
            generation_section["inference_steps"],
            generation_section["guidance_scale"],
            generation_section["seed"],
            generation_section["random_seed_checkbox"],
            generation_section["use_adg"],
            generation_section["cfg_interval_start"],
            generation_section["cfg_interval_end"],
            generation_section["shift"],
            generation_section["infer_method"],
            generation_section["custom_timesteps"],
            generation_section["audio_format"],
            generation_section["lm_temperature"],
            generation_section["lm_cfg_scale"],
            generation_section["lm_top_k"],
            generation_section["lm_top_p"],
            generation_section["lm_negative_prompt"],
            generation_section["use_cot_metas"],  # Added: use_cot_metas
            generation_section["use_cot_caption"],
            generation_section["use_cot_language"],
            generation_section["audio_cover_strength"],
            generation_section["cover_noise_strength"],
            generation_section["think_checkbox"],
            generation_section["text2music_audio_code_string"],
            generation_section["repainting_start"],
            generation_section["repainting_end"],
            generation_section["track_name"],
            generation_section["complete_track_classes"],
            generation_section["instrumental_checkbox"],  # Added: instrumental_checkbox
            results_section["is_format_caption_state"]
        ]
    ).then(
        fn=gen_h.uncheck_auto_for_populated_fields,
        inputs=auto_checkbox_inputs,
        outputs=auto_checkbox_outputs,
    )
    
    # Save buttons for all 8 audio outputs
    download_existing_js = """(current_audio, batch_files) => {
    // Debug: print what the input actually is
    console.log("👉 [Debug] Current Audio Input:", current_audio);
    
    // 1. Safety check
    if (!current_audio) {
        console.warn("⚠️ No audio selected or audio is empty.");
        return;
    }
    if (!batch_files || !Array.isArray(batch_files)) {
        console.warn("⚠️ Batch file list is empty/not ready.");
        return;
    }

    // 2. Smartly extract path string
    let pathString = "";
    
    if (typeof current_audio === "string") {
        // Case A: direct path string received
        pathString = current_audio;
    } else if (typeof current_audio === "object") {
        // Case B: an object is received, try common properties
        // Gradio file objects usually have path, url, or name
        pathString = current_audio.path || current_audio.name || current_audio.url || "";
    }

    if (!pathString) {
        console.error("❌ Error: Could not extract a valid path string from input.", current_audio);
        return;
    }

    // 3. Extract Key (UUID)
    // Path could be /tmp/.../uuid.mp3 or url like /file=.../uuid.mp3
    let filename = pathString.split(/[\\\\/]/).pop(); // get the filename
    let key = filename.split('.')[0]; // get UUID without extension

    console.log(`🔑 Key extracted: ${key}`);

    // 4. Find matching file(s) in the list
    let targets = batch_files.filter(f => {
        // Also extract names from batch_files objects
        // f usually contains name (backend path) and orig_name (download name)
        const fPath = f.name || f.path || ""; 
        return fPath.includes(key);
    });

    if (targets.length === 0) {
        console.warn("❌ No matching files found in batch list for key:", key);
        alert("Batch list does not contain this file yet. Please wait for generation to finish.");
        return;
    }

    // 5. Trigger download(s)
    console.log(`🎯 Found ${targets.length} files to download.`);
    targets.forEach((f, index) => {
        setTimeout(() => {
            const a = document.createElement('a');
            // Prefer url (frontend-accessible link), otherwise try data
            a.href = f.url || f.data; 
            a.download = f.orig_name || "download";
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }, index * 1000); // 300ms interval to avoid browser blocking
    });
}
"""
    for btn_idx in range(1, 9):
        results_section[f"save_btn_{btn_idx}"].click(
            fn=None,
            inputs=[
                results_section[f"generated_audio_{btn_idx}"],
                results_section["generated_audio_batch"],
            ],
        js=download_existing_js  # Run the above JS
    )
    register_results_aux_handlers(
        wiring_context,
        mode_ui_outputs=mode_ui_outputs,
    )

    def generation_wrapper(*args):
        """Proxy batched generation to the results handler stream."""
        yield from res_h.generate_with_batch_management(dit_handler, llm_handler, *args)
    # ========== Generation Handler ==========
    generation_section["generate_btn"].click(
        fn=res_h.clear_audio_outputs_for_new_generation,
        outputs=[
            results_section["generated_audio_1"],
            results_section["generated_audio_2"],
            results_section["generated_audio_3"],
            results_section["generated_audio_4"],
            results_section["generated_audio_5"],
            results_section["generated_audio_6"],
            results_section["generated_audio_7"],
            results_section["generated_audio_8"],
            results_section["generated_audio_batch"],
        ],
    ).then(
        fn=generation_wrapper,
        inputs=[
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["bpm"],
            generation_section["key_scale"],
            generation_section["time_signature"],
            generation_section["vocal_language"],
            generation_section["inference_steps"],
            generation_section["guidance_scale"],
            generation_section["random_seed_checkbox"],
            generation_section["seed"],
            generation_section["reference_audio"],
            generation_section["audio_duration"],
            generation_section["batch_size_input"],
            generation_section["src_audio"],
            generation_section["text2music_audio_code_string"],
            generation_section["repainting_start"],
            generation_section["repainting_end"],
            generation_section["instruction_display_gen"],
            generation_section["audio_cover_strength"],
            generation_section["cover_noise_strength"],
            generation_section["task_type"],
            generation_section["use_adg"],
            generation_section["cfg_interval_start"],
            generation_section["cfg_interval_end"],
            generation_section["shift"],
            generation_section["infer_method"],
            generation_section["custom_timesteps"],
            generation_section["audio_format"],
            generation_section["lm_temperature"],
            generation_section["think_checkbox"],
            generation_section["lm_cfg_scale"],
            generation_section["lm_top_k"],
            generation_section["lm_top_p"],
            generation_section["lm_negative_prompt"],
            generation_section["use_cot_metas"],
            generation_section["use_cot_caption"],
            generation_section["use_cot_language"],
            results_section["is_format_caption_state"],
            generation_section["constrained_decoding_debug"],
            generation_section["allow_lm_batch"],
            generation_section["auto_score"],
            generation_section["auto_lrc"],
            generation_section["score_scale"],
            generation_section["lm_batch_chunk_size"],
            generation_section["track_name"],
            generation_section["complete_track_classes"],
            generation_section["enable_normalization"],
            generation_section["normalization_db"],
            generation_section["latent_shift"],
            generation_section["latent_rescale"],
            generation_section["autogen_checkbox"],
            results_section["current_batch_index"],
            results_section["total_batches"],
            results_section["batch_queue"],
            results_section["generation_params_state"],
        ],
        outputs=[
            results_section["generated_audio_1"],
            results_section["generated_audio_2"],
            results_section["generated_audio_3"],
            results_section["generated_audio_4"],
            results_section["generated_audio_5"],
            results_section["generated_audio_6"],
            results_section["generated_audio_7"],
            results_section["generated_audio_8"],
            results_section["generated_audio_batch"],
            results_section["generation_info"],
            results_section["status_output"],
            generation_section["seed"],
            results_section["score_display_1"],
            results_section["score_display_2"],
            results_section["score_display_3"],
            results_section["score_display_4"],
            results_section["score_display_5"],
            results_section["score_display_6"],
            results_section["score_display_7"],
            results_section["score_display_8"],
            results_section["codes_display_1"],
            results_section["codes_display_2"],
            results_section["codes_display_3"],
            results_section["codes_display_4"],
            results_section["codes_display_5"],
            results_section["codes_display_6"],
            results_section["codes_display_7"],
            results_section["codes_display_8"],
            results_section["details_accordion_1"],
            results_section["details_accordion_2"],
            results_section["details_accordion_3"],
            results_section["details_accordion_4"],
            results_section["details_accordion_5"],
            results_section["details_accordion_6"],
            results_section["details_accordion_7"],
            results_section["details_accordion_8"],
            results_section["lrc_display_1"],
            results_section["lrc_display_2"],
            results_section["lrc_display_3"],
            results_section["lrc_display_4"],
            results_section["lrc_display_5"],
            results_section["lrc_display_6"],
            results_section["lrc_display_7"],
            results_section["lrc_display_8"],
            results_section["lm_metadata_state"],
            results_section["is_format_caption_state"],
            results_section["current_batch_index"],
            results_section["total_batches"],
            results_section["batch_queue"],
            results_section["generation_params_state"],
            results_section["batch_indicator"],
            results_section["prev_batch_btn"],
            results_section["next_batch_btn"],
            results_section["next_batch_status"],
            results_section["restore_params_btn"],
        ],
    ).then(
        fn=lambda *args: res_h.generate_next_batch_background(dit_handler, llm_handler, *args),
        inputs=[
            generation_section["autogen_checkbox"],
            results_section["generation_params_state"],
            results_section["current_batch_index"],
            results_section["total_batches"],
            results_section["batch_queue"],
            results_section["is_format_caption_state"],
        ],
        outputs=[
            results_section["batch_queue"],
            results_section["total_batches"],
            results_section["next_batch_status"],
            results_section["next_batch_btn"],
        ]
    )
    
    # ========== Batch Navigation Handlers ==========
    results_section["prev_batch_btn"].click(
        fn=res_h.navigate_to_previous_batch,
        inputs=[
            results_section["current_batch_index"],
            results_section["batch_queue"],
        ],
        outputs=[
            results_section["generated_audio_1"],
            results_section["generated_audio_2"],
            results_section["generated_audio_3"],
            results_section["generated_audio_4"],
            results_section["generated_audio_5"],
            results_section["generated_audio_6"],
            results_section["generated_audio_7"],
            results_section["generated_audio_8"],
            results_section["generated_audio_batch"],
            results_section["generation_info"],
            results_section["current_batch_index"],
            results_section["batch_indicator"],
            results_section["prev_batch_btn"],
            results_section["next_batch_btn"],
            results_section["status_output"],
            results_section["score_display_1"],
            results_section["score_display_2"],
            results_section["score_display_3"],
            results_section["score_display_4"],
            results_section["score_display_5"],
            results_section["score_display_6"],
            results_section["score_display_7"],
            results_section["score_display_8"],
            results_section["codes_display_1"],
            results_section["codes_display_2"],
            results_section["codes_display_3"],
            results_section["codes_display_4"],
            results_section["codes_display_5"],
            results_section["codes_display_6"],
            results_section["codes_display_7"],
            results_section["codes_display_8"],
            results_section["lrc_display_1"],
            results_section["lrc_display_2"],
            results_section["lrc_display_3"],
            results_section["lrc_display_4"],
            results_section["lrc_display_5"],
            results_section["lrc_display_6"],
            results_section["lrc_display_7"],
            results_section["lrc_display_8"],
            results_section["details_accordion_1"],
            results_section["details_accordion_2"],
            results_section["details_accordion_3"],
            results_section["details_accordion_4"],
            results_section["details_accordion_5"],
            results_section["details_accordion_6"],
            results_section["details_accordion_7"],
            results_section["details_accordion_8"],
            results_section["restore_params_btn"],
        ]
    )
    
    results_section["next_batch_btn"].click(
        fn=res_h.capture_current_params,
        inputs=[
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["bpm"],
            generation_section["key_scale"],
            generation_section["time_signature"],
            generation_section["vocal_language"],
            generation_section["inference_steps"],
            generation_section["guidance_scale"],
            generation_section["random_seed_checkbox"],
            generation_section["seed"],
            generation_section["reference_audio"],
            generation_section["audio_duration"],
            generation_section["batch_size_input"],
            generation_section["src_audio"],
            generation_section["text2music_audio_code_string"],
            generation_section["repainting_start"],
            generation_section["repainting_end"],
            generation_section["instruction_display_gen"],
            generation_section["audio_cover_strength"],
            generation_section["cover_noise_strength"],
            generation_section["task_type"],
            generation_section["use_adg"],
            generation_section["cfg_interval_start"],
            generation_section["cfg_interval_end"],
            generation_section["shift"],
            generation_section["infer_method"],
            generation_section["custom_timesteps"],
            generation_section["audio_format"],
            generation_section["lm_temperature"],
            generation_section["think_checkbox"],
            generation_section["lm_cfg_scale"],
            generation_section["lm_top_k"],
            generation_section["lm_top_p"],
            generation_section["lm_negative_prompt"],
            generation_section["use_cot_metas"],
            generation_section["use_cot_caption"],
            generation_section["use_cot_language"],
            generation_section["constrained_decoding_debug"],
            generation_section["allow_lm_batch"],
            generation_section["auto_score"],
            generation_section["auto_lrc"],
            generation_section["score_scale"],
            generation_section["lm_batch_chunk_size"],
            generation_section["track_name"],
            generation_section["complete_track_classes"],
            generation_section["enable_normalization"],
            generation_section["normalization_db"],
            generation_section["latent_shift"],
            generation_section["latent_rescale"],
        ],
        outputs=[results_section["generation_params_state"]]
    ).then(
        fn=res_h.navigate_to_next_batch,
        inputs=[
            generation_section["autogen_checkbox"],
            results_section["current_batch_index"],
            results_section["total_batches"],
            results_section["batch_queue"],
        ],
        outputs=[
            results_section["generated_audio_1"],
            results_section["generated_audio_2"],
            results_section["generated_audio_3"],
            results_section["generated_audio_4"],
            results_section["generated_audio_5"],
            results_section["generated_audio_6"],
            results_section["generated_audio_7"],
            results_section["generated_audio_8"],
            results_section["generated_audio_batch"],
            results_section["generation_info"],
            results_section["current_batch_index"],
            results_section["batch_indicator"],
            results_section["prev_batch_btn"],
            results_section["next_batch_btn"],
            results_section["status_output"],
            results_section["next_batch_status"],
            results_section["score_display_1"],
            results_section["score_display_2"],
            results_section["score_display_3"],
            results_section["score_display_4"],
            results_section["score_display_5"],
            results_section["score_display_6"],
            results_section["score_display_7"],
            results_section["score_display_8"],
            results_section["codes_display_1"],
            results_section["codes_display_2"],
            results_section["codes_display_3"],
            results_section["codes_display_4"],
            results_section["codes_display_5"],
            results_section["codes_display_6"],
            results_section["codes_display_7"],
            results_section["codes_display_8"],
            results_section["lrc_display_1"],
            results_section["lrc_display_2"],
            results_section["lrc_display_3"],
            results_section["lrc_display_4"],
            results_section["lrc_display_5"],
            results_section["lrc_display_6"],
            results_section["lrc_display_7"],
            results_section["lrc_display_8"],
            results_section["details_accordion_1"],
            results_section["details_accordion_2"],
            results_section["details_accordion_3"],
            results_section["details_accordion_4"],
            results_section["details_accordion_5"],
            results_section["details_accordion_6"],
            results_section["details_accordion_7"],
            results_section["details_accordion_8"],
            results_section["restore_params_btn"],
        ]
    ).then(
        fn=lambda *args: res_h.generate_next_batch_background(dit_handler, llm_handler, *args),
        inputs=[
            generation_section["autogen_checkbox"],
            results_section["generation_params_state"],
            results_section["current_batch_index"],
            results_section["total_batches"],
            results_section["batch_queue"],
            results_section["is_format_caption_state"],
        ],
        outputs=[
            results_section["batch_queue"],
            results_section["total_batches"],
            results_section["next_batch_status"],
            results_section["next_batch_btn"],
        ]
    )
    
    # ========== Restore Parameters Handler ==========
    results_section["restore_params_btn"].click(
        fn=res_h.restore_batch_parameters,
        inputs=[
            results_section["current_batch_index"],
            results_section["batch_queue"]
        ],
        outputs=[
            generation_section["text2music_audio_code_string"],
            generation_section["captions"],
            generation_section["lyrics"],
            generation_section["bpm"],
            generation_section["key_scale"],
            generation_section["time_signature"],
            generation_section["vocal_language"],
            generation_section["audio_duration"],
            generation_section["batch_size_input"],
            generation_section["inference_steps"],
            generation_section["lm_temperature"],
            generation_section["lm_cfg_scale"],
            generation_section["lm_top_k"],
            generation_section["lm_top_p"],
            generation_section["think_checkbox"],
            generation_section["use_cot_caption"],
            generation_section["use_cot_language"],
            generation_section["allow_lm_batch"],
            generation_section["track_name"],
            generation_section["complete_track_classes"],
            generation_section["enable_normalization"],
            generation_section["normalization_db"],
            generation_section["latent_shift"],
            generation_section["latent_rescale"],
        ]
    )
    
    # ========== LRC Display Change Handlers ==========
    # NEW APPROACH: Use lrc_display.change() to update audio subtitles
    # This decouples audio value updates from subtitle updates, avoiding flickering.
    #
    # When lrc_display text changes (from generate, LRC button, or manual edit):
    # 1. lrc_display.change() is triggered
    # 2. update_audio_subtitles_from_lrc() parses LRC and updates audio subtitles
    # 3. Audio value is NEVER updated here - only subtitles
    for lrc_idx in range(1, 9):
        results_section[f"lrc_display_{lrc_idx}"].change(
            fn=res_h.update_audio_subtitles_from_lrc,
            inputs=[
                results_section[f"lrc_display_{lrc_idx}"],
                # audio_duration not needed - parse_lrc_to_subtitles calculates end time from timestamps
            ],
            outputs=[
                results_section[f"generated_audio_{lrc_idx}"],  # Only updates subtitles, not value
            ]
        )


def setup_training_event_handlers(demo, dit_handler, llm_handler, training_section):
    """Setup event handlers for the training tab (dataset builder and LoRA training)"""
    training_context = TrainingWiringContext(
        demo=demo,
        dit_handler=dit_handler,
        llm_handler=llm_handler,
        training_section=training_section,
    )
    training_section = training_context.training_section
    
    # ========== Load Existing Dataset (Top Section) ==========

    # Load existing dataset JSON at the top of Dataset Builder
    training_section["load_json_btn"].click(
        fn=train_h.load_existing_dataset_for_preprocess,
        inputs=[
            training_section["load_json_path"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["load_json_status"],
            training_section["audio_files_table"],
            training_section["sample_selector"],
            training_section["dataset_builder_state"],
            # Also update preview fields with first sample
            training_section["preview_audio"],
            training_section["preview_filename"],
            training_section["edit_caption"],
            training_section["edit_genre"],
            training_section["prompt_override"],
            training_section["edit_lyrics"],
            training_section["edit_bpm"],
            training_section["edit_keyscale"],
            training_section["edit_timesig"],
            training_section["edit_duration"],
            training_section["edit_language"],
            training_section["edit_instrumental"],
            training_section["raw_lyrics_display"],
            training_section["has_raw_lyrics_state"],
            # Update dataset-level settings
            training_section["dataset_name"],
            training_section["custom_tag"],
            training_section["tag_position"],
            training_section["all_instrumental"],
            training_section["genre_ratio"],
        ]
    ).then(
        fn=lambda has_raw: gr.update(visible=has_raw),
        inputs=[training_section["has_raw_lyrics_state"]],
        outputs=[training_section["raw_lyrics_display"]],
    )
    
    # ========== Dataset Builder Handlers ==========
    
    # Scan directory for audio files
    training_section["scan_btn"].click(
        fn=lambda dir, name, tag, pos, instr, state: train_h.scan_directory(
            dir, name, tag, pos, instr, state
        ),
        inputs=[
            training_section["audio_directory"],
            training_section["dataset_name"],
            training_section["custom_tag"],
            training_section["tag_position"],
            training_section["all_instrumental"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["audio_files_table"],
            training_section["scan_status"],
            training_section["sample_selector"],
            training_section["dataset_builder_state"],
        ]
    )
    
    # Auto-label all samples
    training_section["auto_label_btn"].click(
        fn=lambda state, skip, fmt_lyrics, trans_lyrics, only_unlab: train_h.auto_label_all(
            dit_handler, llm_handler, state, skip, fmt_lyrics, trans_lyrics, only_unlab
        ),
        inputs=[
            training_section["dataset_builder_state"],
            training_section["skip_metas"],
            training_section["format_lyrics"],
            training_section["transcribe_lyrics"],
            training_section["only_unlabeled"],
        ],
        outputs=[
            training_section["audio_files_table"],
            training_section["label_progress"],
            training_section["dataset_builder_state"],
        ]
    ).then(
        # Refresh preview/edit fields after labeling completes
        fn=train_h.get_sample_preview,
        inputs=[
            training_section["sample_selector"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["preview_audio"],
            training_section["preview_filename"],
            training_section["edit_caption"],
            training_section["edit_genre"],
            training_section["prompt_override"],
            training_section["edit_lyrics"],
            training_section["edit_bpm"],
            training_section["edit_keyscale"],
            training_section["edit_timesig"],
            training_section["edit_duration"],
            training_section["edit_language"],
            training_section["edit_instrumental"],
            training_section["raw_lyrics_display"],
            training_section["has_raw_lyrics_state"],
        ]
    ).then(
        fn=lambda status: f"{status or '✅ Auto-label complete.'}\n✅ Preview refreshed.",
        inputs=[training_section["label_progress"]],
        outputs=[training_section["label_progress"]],
    ).then(
        fn=lambda has_raw: gr.update(visible=bool(has_raw)),
        inputs=[training_section["has_raw_lyrics_state"]],
        outputs=[training_section["raw_lyrics_display"]],
    )

    # Mutual exclusion: format_lyrics and transcribe_lyrics cannot both be True
    training_section["format_lyrics"].change(
        fn=lambda fmt: gr.update(value=False) if fmt else gr.update(),
        inputs=[training_section["format_lyrics"]],
        outputs=[training_section["transcribe_lyrics"]]
    )

    training_section["transcribe_lyrics"].change(
        fn=lambda trans: gr.update(value=False) if trans else gr.update(),
        inputs=[training_section["transcribe_lyrics"]],
        outputs=[training_section["format_lyrics"]]
    )

    # Sample selector change - update preview
    training_section["sample_selector"].change(
        fn=train_h.get_sample_preview,
        inputs=[
            training_section["sample_selector"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["preview_audio"],
            training_section["preview_filename"],
            training_section["edit_caption"],
            training_section["edit_genre"],
            training_section["prompt_override"],
            training_section["edit_lyrics"],
            training_section["edit_bpm"],
            training_section["edit_keyscale"],
            training_section["edit_timesig"],
            training_section["edit_duration"],
            training_section["edit_language"],
            training_section["edit_instrumental"],
            training_section["raw_lyrics_display"],
            training_section["has_raw_lyrics_state"],
        ]
    ).then(
        # Show/hide raw lyrics panel based on whether raw lyrics exist
        fn=lambda has_raw: gr.update(visible=has_raw),
        inputs=[training_section["has_raw_lyrics_state"]],
        outputs=[training_section["raw_lyrics_display"]],
    )
    
    # Save sample edit
    training_section["save_edit_btn"].click(
        fn=train_h.save_sample_edit,
        inputs=[
            training_section["sample_selector"],
            training_section["edit_caption"],
            training_section["edit_genre"],
            training_section["prompt_override"],
            training_section["edit_lyrics"],
            training_section["edit_bpm"],
            training_section["edit_keyscale"],
            training_section["edit_timesig"],
            training_section["edit_language"],
            training_section["edit_instrumental"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["audio_files_table"],
            training_section["edit_status"],
            training_section["dataset_builder_state"],
        ]
    )

    # Update settings when changed (including genre_ratio)
    for trigger in [training_section["custom_tag"], training_section["tag_position"], training_section["all_instrumental"], training_section["genre_ratio"]]:
        trigger.change(
            fn=train_h.update_settings,
            inputs=[
                training_section["custom_tag"],
                training_section["tag_position"],
                training_section["all_instrumental"],
                training_section["genre_ratio"],
                training_section["dataset_builder_state"],
            ],
            outputs=[training_section["dataset_builder_state"]]
        )

    # Save dataset
    training_section["save_dataset_btn"].click(
        fn=train_h.save_dataset,
        inputs=[
            training_section["save_path"],
            training_section["dataset_name"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["save_status"],
            training_section["save_path"],
        ]
    )
    
    # ========== Preprocess Handlers ==========
    
    # Load existing dataset JSON for preprocessing
    # This also updates the preview section so users can view/edit samples
    training_section["load_existing_dataset_btn"].click(
        fn=train_h.load_existing_dataset_for_preprocess,
        inputs=[
            training_section["load_existing_dataset_path"],
            training_section["dataset_builder_state"],
        ],
        outputs=[
            training_section["load_existing_status"],
            training_section["audio_files_table"],
            training_section["sample_selector"],
            training_section["dataset_builder_state"],
            # Also update preview fields with first sample
            training_section["preview_audio"],
            training_section["preview_filename"],
            training_section["edit_caption"],
            training_section["edit_genre"],
            training_section["prompt_override"],
            training_section["edit_lyrics"],
            training_section["edit_bpm"],
            training_section["edit_keyscale"],
            training_section["edit_timesig"],
            training_section["edit_duration"],
            training_section["edit_language"],
            training_section["edit_instrumental"],
            training_section["raw_lyrics_display"],
            training_section["has_raw_lyrics_state"],
            # Update dataset-level settings
            training_section["dataset_name"],
            training_section["custom_tag"],
            training_section["tag_position"],
            training_section["all_instrumental"],
            training_section["genre_ratio"],
        ]
    ).then(
        fn=lambda has_raw: gr.update(visible=has_raw),
        inputs=[training_section["has_raw_lyrics_state"]],
        outputs=[training_section["raw_lyrics_display"]],
    )
    
    # Preprocess dataset to tensor files
    training_section["preprocess_btn"].click(
        fn=lambda output_dir, mode, state: train_h.preprocess_dataset(
            output_dir, mode, dit_handler, state
        ),
        inputs=[
            training_section["preprocess_output_dir"],
            training_section["preprocess_mode"],
            training_section["dataset_builder_state"],
        ],
        outputs=[training_section["preprocess_progress"]]
    )
    
    # ========== Training Tab Handlers ==========
    
    # Load preprocessed tensor dataset
    training_section["load_dataset_btn"].click(
        fn=train_h.load_training_dataset,
        inputs=[training_section["training_tensor_dir"]],
        outputs=[training_section["training_dataset_info"]]
    )
    
    # Start training from preprocessed tensors
    def training_wrapper(tensor_dir, r, a, d, lr, ep, bs, ga, se, sh, sd, od, rc, ts):
        """Stream LoRA training progress and normalize failure outputs for the UI."""
        from loguru import logger
        if not isinstance(ts, dict):
            ts = {"is_training": False, "should_stop": False}
        try:
            for progress, log_msg, plot, state in train_h.start_training(
                tensor_dir, dit_handler, r, a, d, lr, ep, bs, ga, se, sh, sd, od, rc, ts
            ):
                yield progress, log_msg, plot, state
        except Exception as e:
            logger.exception("Training wrapper error")
            yield f"❌ Error: {str(e)}", str(e), None, ts
    
    training_section["start_training_btn"].click(
        fn=training_wrapper,
        inputs=[
            training_section["training_tensor_dir"],
            training_section["lora_rank"],
            training_section["lora_alpha"],
            training_section["lora_dropout"],
            training_section["learning_rate"],
            training_section["train_epochs"],
            training_section["train_batch_size"],
            training_section["gradient_accumulation"],
            training_section["save_every_n_epochs"],
            training_section["training_shift"],
            training_section["training_seed"],
            training_section["lora_output_dir"],
            training_section["resume_checkpoint_dir"],
            training_section["training_state"],
        ],
        outputs=[
            training_section["training_progress"],
            training_section["training_log"],
            training_section["training_loss_plot"],
            training_section["training_state"],
        ]
    )
    
    # Stop training
    training_section["stop_training_btn"].click(
        fn=train_h.stop_training,
        inputs=[training_section["training_state"]],
        outputs=[
            training_section["training_progress"],
            training_section["training_state"],
        ]
    )
    
    # Export LoRA
    training_section["export_lora_btn"].click(
        fn=train_h.export_lora,
        inputs=[
            training_section["export_path"],
            training_section["lora_output_dir"],
        ],
        outputs=[training_section["export_status"]]
    )
    
    # ========== LoKr Training Tab Handlers ==========
    
    # Load preprocessed tensor dataset for LoKr
    training_section["lokr_load_dataset_btn"].click(
        fn=train_h.load_training_dataset,
        inputs=[training_section["lokr_training_tensor_dir"]],
        outputs=[training_section["lokr_training_dataset_info"]]
    )
    
    # Start LoKr training from preprocessed tensors
    def lokr_training_wrapper(
        tensor_dir, ldim, lalpha, factor, decompose_both, use_tucker,
        use_scalar, weight_decompose, lr, ep, bs, ga, se, sh, sd, od, ts,
    ):
        """Stream LoKr training progress and normalize failure outputs for the UI."""
        from loguru import logger
        if not isinstance(ts, dict):
            ts = {"is_training": False, "should_stop": False}
        try:
            for progress, log_msg, plot, state in train_h.start_lokr_training(
                tensor_dir, dit_handler,
                ldim, lalpha, factor, decompose_both, use_tucker,
                use_scalar, weight_decompose,
                lr, ep, bs, ga, se, sh, sd, od, ts,
            ):
                yield progress, log_msg, plot, state
        except Exception as e:
            logger.exception("LoKr training wrapper error")
            yield f"❌ Error: {str(e)}", str(e), None, ts
    
    training_section["start_lokr_training_btn"].click(
        fn=lokr_training_wrapper,
        inputs=[
            training_section["lokr_training_tensor_dir"],
            training_section["lokr_linear_dim"],
            training_section["lokr_linear_alpha"],
            training_section["lokr_factor"],
            training_section["lokr_decompose_both"],
            training_section["lokr_use_tucker"],
            training_section["lokr_use_scalar"],
            training_section["lokr_weight_decompose"],
            training_section["lokr_learning_rate"],
            training_section["lokr_train_epochs"],
            training_section["lokr_train_batch_size"],
            training_section["lokr_gradient_accumulation"],
            training_section["lokr_save_every_n_epochs"],
            training_section["lokr_training_shift"],
            training_section["lokr_training_seed"],
            training_section["lokr_output_dir"],
            training_section["training_state"],
        ],
        outputs=[
            training_section["lokr_training_progress"],
            training_section["lokr_training_log"],
            training_section["lokr_training_loss_plot"],
            training_section["training_state"],
        ]
    )
    
    # Stop LoKr training (reuses same stop mechanism)
    training_section["stop_lokr_training_btn"].click(
        fn=train_h.stop_training,
        inputs=[training_section["training_state"]],
        outputs=[
            training_section["lokr_training_progress"],
            training_section["training_state"],
        ]
    )
    
    # Refresh LoKr export epochs
    training_section["refresh_lokr_export_epochs_btn"].click(
        fn=train_h.list_lokr_export_epochs,
        inputs=[training_section["lokr_output_dir"]],
        outputs=[
            training_section["lokr_export_epoch"],
            training_section["lokr_export_status"],
        ]
    )
    
    # Export LoKr
    training_section["export_lokr_btn"].click(
        fn=train_h.export_lokr,
        inputs=[
            training_section["lokr_export_path"],
            training_section["lokr_output_dir"],
            training_section["lokr_export_epoch"],
        ],
        outputs=[training_section["lokr_export_status"]]
    )
