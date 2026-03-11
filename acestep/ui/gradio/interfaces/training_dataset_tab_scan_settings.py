"""Dataset scan/load and settings controls for the training dataset tab."""

from __future__ import annotations

import gradio as gr

from acestep.ui.gradio.i18n import t


def build_dataset_scan_and_settings_controls() -> dict[str, object]:
    """Render scan/load controls and dataset settings for the dataset-builder tab."""

    gr.HTML(
        f"""
            <div style="padding: 10px; margin-bottom: 10px; border: 1px solid #4a4a6a; border-radius: 8px; background: linear-gradient(135deg, #2a2a4a 0%, #1a1a3a 100%);">
                <h3 style="margin: 0 0 5px 0;">{t("training.quick_start_title")}</h3>
                <p style="margin: 0; color: #aaa;">Choose one: <b>Load existing dataset</b> OR <b>Scan new directory</b></p>
            </div>
            """
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.HTML("<h4>📂 Load Existing Dataset</h4>")
            with gr.Row():
                load_json_path = gr.Textbox(
                    label=t("training.load_dataset_label"),
                    placeholder="./datasets/my_lora_dataset.json",
                    info=t("training.load_dataset_info"),
                    elem_classes=["has-info-container"],
                    scale=3,
                )
                load_json_btn = gr.Button(t("training.load_btn"), variant="primary", scale=1)
            load_json_status = gr.Textbox(
                label=t("training.load_status"),
                interactive=False,
            )

        with gr.Column(scale=1):
            gr.HTML("<h4>🔍 Scan New Directory</h4>")
            with gr.Row():
                audio_directory = gr.Textbox(
                    label=t("training.scan_label"),
                    placeholder="/path/to/your/audio/folder",
                    info=t("training.scan_info"),
                    elem_classes=["has-info-container"],
                    scale=3,
                )
                scan_btn = gr.Button(t("training.scan_btn"), variant="secondary", scale=1)
            scan_status = gr.Textbox(
                label=t("training.scan_status"),
                interactive=False,
            )

    gr.HTML("<hr>")

    with gr.Row():
        with gr.Column(scale=2):
            audio_files_table = gr.Dataframe(
                headers=["#", "Filename", "Duration", "Lyrics", "Labeled", "BPM", "Key", "Caption"],
                datatype=["number", "str", "str", "str", "str", "str", "str", "str"],
                label=t("training.found_audio_files"),
                interactive=False,
                wrap=True,
            )

        with gr.Column(scale=1):
            gr.HTML(f"<h3>⚙️ {t('training.dataset_settings_header')}</h3>")

            dataset_name = gr.Textbox(
                label=t("training.dataset_name"),
                value="my_lora_dataset",
                placeholder=t("training.dataset_name_placeholder"),
            )

            all_instrumental = gr.Checkbox(
                label=t("training.all_instrumental"),
                value=True,
                info=t("training.all_instrumental_info"),
                elem_classes=["has-info-container"],
            )

            format_lyrics = gr.Checkbox(
                label="Format Lyrics (LM)",
                value=False,
                info="Use LM to format/structure user-provided lyrics from .txt files (coming soon)",
                elem_classes=["has-info-container"],
                interactive=False,
            )

            transcribe_lyrics = gr.Checkbox(
                label="Transcribe Lyrics (LM)",
                value=False,
                info="Use LM to transcribe lyrics from audio (coming soon)",
                elem_classes=["has-info-container"],
                interactive=False,
            )

            custom_tag = gr.Textbox(
                label=t("training.custom_tag"),
                placeholder="e.g., 8bit_retro, my_style",
                info=t("training.custom_tag_info"),
                elem_classes=["has-info-container"],
            )

            tag_position = gr.Radio(
                choices=[
                    (t("training.tag_prepend"), "prepend"),
                    (t("training.tag_append"), "append"),
                    (t("training.tag_replace"), "replace"),
                ],
                value="replace",
                label=t("training.tag_position"),
                info=t("training.tag_position_info"),
                elem_classes=["has-info-container"],
            )

            genre_ratio = gr.Slider(
                minimum=0,
                maximum=100,
                step=10,
                value=0,
                label=t("training.genre_ratio"),
                info=t("training.genre_ratio_info"),
                elem_classes=["has-info-container"],
            )

    return {
        "load_json_path": load_json_path,
        "load_json_btn": load_json_btn,
        "load_json_status": load_json_status,
        "audio_directory": audio_directory,
        "scan_btn": scan_btn,
        "scan_status": scan_status,
        "audio_files_table": audio_files_table,
        "dataset_name": dataset_name,
        "all_instrumental": all_instrumental,
        "format_lyrics": format_lyrics,
        "transcribe_lyrics": transcribe_lyrics,
        "custom_tag": custom_tag,
        "tag_position": tag_position,
        "genre_ratio": genre_ratio,
    }
