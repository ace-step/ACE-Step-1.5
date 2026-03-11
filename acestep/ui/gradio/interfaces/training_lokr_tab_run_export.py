"""LoKr tab run and export controls."""

from __future__ import annotations

import gradio as gr

from acestep.ui.gradio.i18n import t


def build_lokr_run_and_export_controls() -> dict[str, object]:
    """Render LoKr training-run and export controls for the training tab."""

    gr.HTML(f"<hr><h3>🎛️ {t('training.train_section_params')}</h3>")

    with gr.Row():
        lokr_learning_rate = gr.Number(
            label=t("training.learning_rate"),
            value=1e-3,
            info=t("training.lokr_learning_rate_info"),
            elem_classes=["has-info-container"],
        )

        lokr_train_epochs = gr.Slider(
            minimum=1,
            maximum=4000,
            step=1,
            value=500,
            label=t("training.max_epochs"),
        )

        lokr_train_batch_size = gr.Slider(
            minimum=1,
            maximum=8,
            step=1,
            value=1,
            label=t("training.batch_size"),
        )

        lokr_gradient_accumulation = gr.Slider(
            minimum=1,
            maximum=16,
            step=1,
            value=4,
            label=t("training.gradient_accumulation"),
        )

    with gr.Row():
        lokr_save_every_n_epochs = gr.Slider(
            minimum=1,
            maximum=1000,
            step=1,
            value=10,
            label=t("training.save_every_n_epochs"),
        )

        lokr_training_shift = gr.Slider(
            minimum=1.0,
            maximum=5.0,
            step=0.5,
            value=3.0,
            label=t("training.shift"),
            info=t("training.shift_info"),
            elem_classes=["has-info-container"],
        )

        lokr_training_seed = gr.Number(
            label=t("training.seed"),
            value=42,
            precision=0,
        )

    with gr.Row():
        lokr_output_dir = gr.Textbox(
            label=t("training.output_dir"),
            value="./lokr_output",
            placeholder="./lokr_output",
            info=t("training.lokr_output_dir_info"),
            elem_classes=["has-info-container"],
        )

    gr.HTML("<hr>")

    with gr.Row():
        with gr.Column(scale=1):
            start_lokr_training_btn = gr.Button(
                t("training.start_lokr_training_btn"),
                variant="primary",
                size="lg",
            )
        with gr.Column(scale=1):
            stop_lokr_training_btn = gr.Button(
                t("training.stop_training_btn"),
                variant="stop",
                size="lg",
            )

    lokr_training_progress = gr.Textbox(
        label=t("training.training_progress"),
        interactive=False,
        lines=2,
    )

    with gr.Row():
        lokr_training_log = gr.Textbox(
            label=t("training.training_log"),
            interactive=False,
            lines=10,
            max_lines=15,
            scale=1,
        )
        lokr_training_loss_plot = gr.Plot(
            label=t("training.lokr_training_loss_title"),
            scale=1,
        )

    gr.HTML(f"<hr><h3>📦 {t('training.lokr_export_header')}</h3>")

    with gr.Row():
        lokr_export_path = gr.Textbox(
            label=t("training.export_path"),
            value="./lokr_output/final_lokr",
            placeholder="./lokr_output/my_lokr",
        )
        export_lokr_btn = gr.Button(t("training.export_lokr_btn"), variant="secondary")

    with gr.Row():
        lokr_export_epoch = gr.Dropdown(
            choices=[t("training.latest_auto")],
            value=t("training.latest_auto"),
            label=t("training.lokr_checkpoint_epoch"),
            info=t("training.lokr_checkpoint_epoch_info"),
            elem_classes=["has-info-container"],
        )
        refresh_lokr_export_epochs_btn = gr.Button(
            t("training.refresh_epochs_btn"), variant="secondary"
        )

    lokr_export_status = gr.Textbox(
        label=t("training.export_status"),
        interactive=False,
    )

    return {
        "lokr_learning_rate": lokr_learning_rate,
        "lokr_train_epochs": lokr_train_epochs,
        "lokr_train_batch_size": lokr_train_batch_size,
        "lokr_gradient_accumulation": lokr_gradient_accumulation,
        "lokr_save_every_n_epochs": lokr_save_every_n_epochs,
        "lokr_training_shift": lokr_training_shift,
        "lokr_training_seed": lokr_training_seed,
        "lokr_output_dir": lokr_output_dir,
        "start_lokr_training_btn": start_lokr_training_btn,
        "stop_lokr_training_btn": stop_lokr_training_btn,
        "lokr_training_progress": lokr_training_progress,
        "lokr_training_log": lokr_training_log,
        "lokr_training_loss_plot": lokr_training_loss_plot,
        "lokr_export_path": lokr_export_path,
        "lokr_export_epoch": lokr_export_epoch,
        "refresh_lokr_export_epochs_btn": refresh_lokr_export_epochs_btn,
        "export_lokr_btn": export_lokr_btn,
        "lokr_export_status": lokr_export_status,
    }
