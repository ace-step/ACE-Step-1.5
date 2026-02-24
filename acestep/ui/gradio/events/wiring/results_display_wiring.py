"""Results display/restore/LRC event wiring helpers."""

from .context import GenerationWiringContext
from .. import results_handlers as res_h


_DOWNLOAD_EXISTING_JS = """(current_audio, batch_files) => {
    // Debug: print what the input actually is
    console.log("[Debug] Current Audio Input:", current_audio);

    // 1. Safety check
    if (!current_audio) {
        console.warn("Warning: No audio selected or audio is empty.");
        return;
    }
    if (!batch_files || !Array.isArray(batch_files)) {
        console.warn("Warning: Batch file list is empty/not ready.");
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
        console.error("Error: Could not extract a valid path string from input.", current_audio);
        return;
    }

    // 3. Extract Key (UUID)
    // Path could be /tmp/.../uuid.mp3 or url like /file=.../uuid.mp3
    let filename = pathString.split(/[\\/]/).pop(); // get the filename
    let key = filename.split('.')[0]; // get UUID without extension

    console.log(`Key extracted: ${key}`);

    // 4. Find matching file(s) in the list
    let targets = batch_files.filter(f => {
        // Also extract names from batch_files objects
        // f usually contains name (backend path) and orig_name (download name)
        const fPath = f.name || f.path || "";
        return fPath.includes(key);
    });

    if (targets.length === 0) {
        console.warn("Warning: No matching files found in batch list for key:", key);
        alert("Batch list does not contain this file yet. Please wait for generation to finish.");
        return;
    }

    // 5. Trigger download(s)
    console.log(`Found ${targets.length} files to download.`);
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
        }, index * 1000); // 1000ms interval per index to avoid browser blocking
    });
}
"""


def register_results_save_button_handlers(context: GenerationWiringContext) -> None:
    """Register save/download button JS handlers for the 8 result slots."""

    results_section = context.results_section
    for btn_idx in range(1, 9):
        results_section[f"save_btn_{btn_idx}"].click(
            fn=None,
            inputs=[
                results_section[f"generated_audio_{btn_idx}"],
                results_section["generated_audio_batch"],
            ],
            js=_DOWNLOAD_EXISTING_JS,
        )


def register_results_restore_and_lrc_handlers(context: GenerationWiringContext) -> None:
    """Register restore-parameters and LRC subtitle-sync handlers."""

    generation_section = context.generation_section
    results_section = context.results_section

    results_section["restore_params_btn"].click(
        fn=res_h.restore_batch_parameters,
        inputs=[
            results_section["current_batch_index"],
            results_section["batch_queue"],
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
        ],
    )

    for lrc_idx in range(1, 9):
        results_section[f"lrc_display_{lrc_idx}"].change(
            fn=res_h.update_audio_subtitles_from_lrc,
            inputs=[results_section[f"lrc_display_{lrc_idx}"]],
            outputs=[results_section[f"generated_audio_{lrc_idx}"]],
        )
