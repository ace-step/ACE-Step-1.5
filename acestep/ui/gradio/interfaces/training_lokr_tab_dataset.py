"""LoKr tab dataset and adapter-setting controls."""

from __future__ import annotations

import gradio as gr

from acestep.ui.gradio.i18n import t


def build_lokr_dataset_and_adapter_controls() -> dict[str, object]:
    """Render LoKr dataset selector and adapter-parameter controls."""

    with gr.Row():
        with gr.Column(scale=2):
            gr.HTML(f"<h3>📊 {t('training.lokr_section_tensors')}</h3>")
            gr.Markdown(t("training.lokr_tensor_selection_desc"))

            lokr_training_tensor_dir = gr.Textbox(
                label=t("training.preprocessed_tensors_dir"),
                placeholder="./datasets/preprocessed_tensors",
                value="./datasets/preprocessed_tensors",
                info=t("training.preprocessed_tensors_info"),
                elem_classes=["has-info-container"],
            )

            lokr_load_dataset_btn = gr.Button(t("training.load_dataset_btn"), variant="secondary")

            lokr_training_dataset_info = gr.Textbox(
                label=t("training.dataset_info"),
                interactive=False,
                lines=3,
            )

        with gr.Column(scale=1):
            gr.HTML(f"<h3>⚙️ {t('training.lokr_section_settings')}</h3>")

            lokr_linear_dim = gr.Slider(
                minimum=4,
                maximum=256,
                step=4,
                value=64,
                label=t("training.lokr_linear_dim"),
                info=t("training.lokr_linear_dim_info"),
                elem_classes=["has-info-container"],
            )
            lokr_linear_alpha = gr.Slider(
                minimum=4,
                maximum=512,
                step=4,
                value=128,
                label=t("training.lokr_linear_alpha"),
                info=t("training.lokr_linear_alpha_info"),
                elem_classes=["has-info-container"],
            )
            lokr_factor = gr.Number(
                label=t("training.lokr_factor"),
                value=-1,
                precision=0,
                info=t("training.lokr_factor_info"),
                elem_classes=["has-info-container"],
            )
            lokr_decompose_both = gr.Checkbox(
                label=t("training.lokr_decompose_both"),
                value=False,
                info=t("training.lokr_decompose_both_info"),
                elem_classes=["has-info-container"],
            )
            lokr_use_tucker = gr.Checkbox(
                label=t("training.lokr_use_tucker"),
                value=False,
                info=t("training.lokr_use_tucker_info"),
                elem_classes=["has-info-container"],
            )
            lokr_use_scalar = gr.Checkbox(
                label=t("training.lokr_use_scalar"),
                value=False,
                info=t("training.lokr_use_scalar_info"),
                elem_classes=["has-info-container"],
            )
            lokr_weight_decompose = gr.Checkbox(
                label=t("training.lokr_weight_decompose"),
                value=True,
                info=t("training.lokr_weight_decompose_info"),
                elem_classes=["has-info-container"],
            )

    return {
        "lokr_training_tensor_dir": lokr_training_tensor_dir,
        "lokr_load_dataset_btn": lokr_load_dataset_btn,
        "lokr_training_dataset_info": lokr_training_dataset_info,
        "lokr_linear_dim": lokr_linear_dim,
        "lokr_linear_alpha": lokr_linear_alpha,
        "lokr_factor": lokr_factor,
        "lokr_decompose_both": lokr_decompose_both,
        "lokr_use_tucker": lokr_use_tucker,
        "lokr_use_scalar": lokr_use_scalar,
        "lokr_weight_decompose": lokr_weight_decompose,
    }
