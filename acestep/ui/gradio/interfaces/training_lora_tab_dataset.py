"""LoRA tab dataset and adapter-setting controls."""

from __future__ import annotations

import gradio as gr

from acestep.ui.gradio.i18n import t


def build_lora_dataset_and_adapter_controls() -> dict[str, object]:
    """Render LoRA dataset selector and adapter-parameter controls."""

    with gr.Row():
        with gr.Column(scale=2):
            gr.HTML(f"<h3>📊 {t('training.train_section_tensors')}</h3>")
            gr.Markdown(t("training.train_tensor_selection_desc"))

            training_tensor_dir = gr.Textbox(
                label=t("training.preprocessed_tensors_dir"),
                placeholder="./datasets/preprocessed_tensors",
                value="./datasets/preprocessed_tensors",
                info=t("training.preprocessed_tensors_info"),
                elem_classes=["has-info-container"],
            )

            load_dataset_btn = gr.Button(t("training.load_dataset_btn"), variant="secondary")

            training_dataset_info = gr.Textbox(
                label=t("training.dataset_info"),
                interactive=False,
                lines=3,
            )

        with gr.Column(scale=1):
            gr.HTML(f"<h3>⚙️ {t('training.train_section_lora')}</h3>")

            lora_rank = gr.Slider(
                minimum=4,
                maximum=256,
                step=4,
                value=64,
                label=t("training.lora_rank"),
                info=t("training.lora_rank_info"),
                elem_classes=["has-info-container"],
            )

            lora_alpha = gr.Slider(
                minimum=4,
                maximum=512,
                step=4,
                value=128,
                label=t("training.lora_alpha"),
                info=t("training.lora_alpha_info"),
                elem_classes=["has-info-container"],
            )

            lora_dropout = gr.Slider(
                minimum=0.0,
                maximum=0.5,
                step=0.05,
                value=0.1,
                label=t("training.lora_dropout"),
            )

    return {
        "training_tensor_dir": training_tensor_dir,
        "load_dataset_btn": load_dataset_btn,
        "training_dataset_info": training_dataset_info,
        "lora_rank": lora_rank,
        "lora_alpha": lora_alpha,
        "lora_dropout": lora_dropout,
    }
