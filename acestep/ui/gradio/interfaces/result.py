"""
Gradio UI Results Section Module
Contains results display section component definitions
"""
import gradio as gr
from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.help_content import create_help_button


def _create_audio_column(n, visible=True):
    """Create a single audio sample column with all its sub-components.
    
    Layout:
        Audio player
        Row: [Send To Cover] [Send To Repaint] [Save]
        Accordion (Score & LRC & LM Codes):
            codes_display
            Row: score_display + score_btn
            Row: lrc_display + lrc_btn
    """
    with gr.Column(visible=visible) as audio_col:
        generated_audio = gr.Audio(
            label=t("results.generated_music", n=n),
            type="filepath",
            interactive=False,
            buttons=[]
        )
        with gr.Row(equal_height=True):
            send_to_remix_btn = gr.Button(
                t("results.send_to_remix_btn"),
                variant="secondary", size="sm", scale=1
            )
            send_to_repaint_btn = gr.Button(
                t("results.send_to_repaint_btn"),
                variant="secondary", size="sm", scale=1
            )
            save_btn = gr.Button(
                t("results.save_btn"),
                variant="primary", size="sm", scale=1
            )
        with gr.Accordion(t("results.details_accordion"), open=False, visible=True) as details_accordion:
            codes_display = gr.Textbox(
                label=t("results.codes_label", n=n),
                interactive=False, buttons=["copy"],
                lines=4, max_lines=4, visible=True
            )
            convert_to_codes_btn = gr.Button(
                t("results.convert_to_codes_btn"),
                variant="secondary", size="sm"
            )
            score_display = gr.Textbox(
                label=t("results.quality_score_label", n=n),
                interactive=False, buttons=["copy"],
                lines=6, max_lines=6, visible=True
            )
            score_btn = gr.Button(
                t("results.score_btn"),
                variant="secondary", size="sm"
            )
            lrc_display = gr.Textbox(
                label=t("results.lrc_label", n=n),
                interactive=True, buttons=["copy"],
                lines=8, max_lines=8, visible=True
            )
            with gr.Row(equal_height=True):
                lrc_btn = gr.Button(
                    t("results.lrc_btn"),
                    variant="secondary", size="sm"
                )
                save_lrc_btn = gr.Button(
                    t("results.save_lrc_btn"),
                    variant="secondary", size="sm"
                )
            lrc_download_file = gr.File(
                label="LRC Download",
                visible=False,
                interactive=False,
            )
    return {
        "audio_col": audio_col,
        "generated_audio": generated_audio,
        "send_to_remix_btn": send_to_remix_btn,
        "send_to_repaint_btn": send_to_repaint_btn,
        "save_btn": save_btn,
        "details_accordion": details_accordion,
        "codes_display": codes_display,
        "convert_to_codes_btn": convert_to_codes_btn,
        "score_display": score_display,
        "score_btn": score_btn,
        "lrc_display": lrc_display,
        "lrc_btn": lrc_btn,
        "save_lrc_btn": save_lrc_btn,
        "lrc_download_file": lrc_download_file,
    }


def create_results_section(dit_handler) -> dict:
    """Create results display section"""
    with gr.Accordion(t("results.title"), open=True):
        create_help_button("results")
        # Hidden state to store LM-generated metadata
        lm_metadata_state = gr.State(value=None)
        
        # Hidden state to track if caption/metadata is from formatted source (LM/transcription)
        is_format_caption_state = gr.State(value=False)
        
        # Batch management states
        current_batch_index = gr.State(value=0)
        total_batches = gr.State(value=1)
        batch_queue = gr.State(value={})
        generation_params_state = gr.State(value={})
        is_generating_background = gr.State(value=False)

        # Row 1: samples 1-4
        with gr.Row():
            cols_1_4 = []
            for i in range(1, 5):
                cols_1_4.append(_create_audio_column(i, visible=(i <= 2)))
        
        # Row 2: samples 5-8 (initially hidden)
        with gr.Row(visible=False) as audio_row_5_8:
            cols_5_8 = []
            for i in range(5, 9):
                cols_5_8.append(_create_audio_column(i, visible=True))
        
        all_cols = cols_1_4 + cols_5_8
        
        status_output = gr.Textbox(label=t("results.generation_status"), interactive=False)
        
        # Batch navigation controls
        with gr.Row(equal_height=True):
            prev_batch_btn = gr.Button(
                t("results.prev_btn"),
                variant="secondary", interactive=False, scale=1, size="sm"
            )
            batch_indicator = gr.Textbox(
                label=t("results.current_batch"),
                value=t("results.batch_indicator", current=1, total=1),
                interactive=False, scale=3
            )
            next_batch_status = gr.Textbox(
                label=t("results.next_batch_status"),
                value="", interactive=False, scale=3
            )
            next_batch_btn = gr.Button(
                t("results.next_btn"),
                variant="primary", interactive=False, scale=1, size="sm"
            )
        
        # One-click restore parameters button
        restore_params_btn = gr.Button(
            t("results.restore_params_btn"),
            variant="secondary", interactive=False, size="sm"
        )
        
        with gr.Accordion(t("results.batch_results_title"), open=True):
            generated_audio_batch = gr.File(
                label=t("results.all_files_label"),
                file_count="multiple", interactive=False
            )
            generation_info = gr.Markdown(label=t("results.generation_details"))
    
    # Build return dict from all_cols
    result = {
        "lm_metadata_state": lm_metadata_state,
        "is_format_caption_state": is_format_caption_state,
        "current_batch_index": current_batch_index,
        "total_batches": total_batches,
        "batch_queue": batch_queue,
        "generation_params_state": generation_params_state,
        "is_generating_background": is_generating_background,
        "status_output": status_output,
        "prev_batch_btn": prev_batch_btn,
        "batch_indicator": batch_indicator,
        "next_batch_btn": next_batch_btn,
        "next_batch_status": next_batch_status,
        "restore_params_btn": restore_params_btn,
        "audio_row_5_8": audio_row_5_8,
        "generated_audio_batch": generated_audio_batch,
        "generation_info": generation_info,
    }
    
    for idx, col_data in enumerate(all_cols, start=1):
        result[f"generated_audio_{idx}"] = col_data["generated_audio"]
        result[f"audio_col_{idx}"] = col_data["audio_col"]
        result[f"send_to_remix_btn_{idx}"] = col_data["send_to_remix_btn"]
        result[f"send_to_repaint_btn_{idx}"] = col_data["send_to_repaint_btn"]
        result[f"save_btn_{idx}"] = col_data["save_btn"]
        result[f"score_btn_{idx}"] = col_data["score_btn"]
        result[f"score_display_{idx}"] = col_data["score_display"]
        result[f"codes_display_{idx}"] = col_data["codes_display"]
        result[f"convert_to_codes_btn_{idx}"] = col_data["convert_to_codes_btn"]
        result[f"lrc_btn_{idx}"] = col_data["lrc_btn"]
        result[f"lrc_display_{idx}"] = col_data["lrc_display"]
        result[f"save_lrc_btn_{idx}"] = col_data["save_lrc_btn"]
        result[f"lrc_download_file_{idx}"] = col_data["lrc_download_file"]
        result[f"details_accordion_{idx}"] = col_data["details_accordion"]
    
    return result
