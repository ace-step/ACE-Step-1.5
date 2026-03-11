"""Dataset save and preprocess controls for the training dataset tab."""

from __future__ import annotations

import gradio as gr

from acestep.ui.gradio.i18n import t


def build_dataset_save_and_preprocess_controls() -> dict[str, object]:
    """Render dataset save/load-preprocess controls and return component handles."""

    gr.HTML(f"<hr><h3>💾 {t('training.step4_title')}</h3>")

    with gr.Row():
        with gr.Column(scale=3):
            save_path = gr.Textbox(
                label=t("training.save_path"),
                value="./datasets/my_lora_dataset.json",
                placeholder="./datasets/dataset_name.json",
                info=t("training.save_path_info"),
                elem_classes=["has-info-container"],
            )
        with gr.Column(scale=1):
            save_dataset_btn = gr.Button(
                t("training.save_dataset_btn"),
                variant="primary",
                size="lg",
            )

    save_status = gr.Textbox(
        label=t("training.save_status"),
        interactive=False,
        lines=2,
    )

    gr.HTML(f"<hr><h3>⚡ {t('training.step5_title')}</h3>")

    gr.Markdown(t("training.step5_intro"))

    with gr.Row():
        with gr.Column(scale=3):
            load_existing_dataset_path = gr.Textbox(
                label=t("training.load_existing_label"),
                placeholder="./datasets/my_lora_dataset.json",
                info=t("training.load_existing_info"),
                elem_classes=["has-info-container"],
            )
        with gr.Column(scale=1):
            load_existing_dataset_btn = gr.Button(
                t("training.load_dataset_btn"),
                variant="secondary",
                size="lg",
            )

    load_existing_status = gr.Textbox(
        label=t("training.load_status"),
        interactive=False,
    )

    gr.Markdown(t("training.step5_details"))

    with gr.Row():
        preprocess_mode = gr.Dropdown(
            label="Preprocess For",
            choices=["LoRA", "LoKr"],
            value="LoRA",
            info="LoRA keeps compatibility mode; LoKr uses per-sample source-style context.",
            elem_classes=["has-info-container"],
        )

    with gr.Row():
        with gr.Column(scale=3):
            preprocess_output_dir = gr.Textbox(
                label=t("training.tensor_output_dir"),
                value="./datasets/preprocessed_tensors",
                placeholder="./datasets/preprocessed_tensors",
                info=t("training.tensor_output_info"),
                elem_classes=["has-info-container"],
            )
        with gr.Column(scale=1):
            preprocess_btn = gr.Button(
                t("training.preprocess_btn"),
                variant="primary",
                size="lg",
            )

    preprocess_progress = gr.Textbox(
        label=t("training.preprocess_progress"),
        interactive=False,
        lines=3,
    )

    return {
        "save_path": save_path,
        "save_dataset_btn": save_dataset_btn,
        "save_status": save_status,
        "load_existing_dataset_path": load_existing_dataset_path,
        "load_existing_dataset_btn": load_existing_dataset_btn,
        "load_existing_status": load_existing_status,
        "preprocess_mode": preprocess_mode,
        "preprocess_output_dir": preprocess_output_dir,
        "preprocess_btn": preprocess_btn,
        "preprocess_progress": preprocess_progress,
    }
