"""LoRA tab run and export controls."""

from __future__ import annotations

import gradio as gr

from acestep.ui.gradio.i18n import t


def build_lora_run_and_export_controls(
    *,
    epoch_min: int,
    epoch_step: int,
    epoch_default: int,
) -> dict[str, object]:
    """Render LoRA training-run and export controls for the training tab."""

    gr.HTML(f"<hr><h3>🎛️ {t('training.train_section_params')}</h3>")

    with gr.Row():
        learning_rate = gr.Number(
            label=t("training.learning_rate"),
            value=3e-4,
            info=t("training.learning_rate_info"),
            elem_classes=["has-info-container"],
        )

        train_epochs = gr.Slider(
            minimum=epoch_min,
            maximum=4000,
            step=epoch_step,
            value=epoch_default,
            label=t("training.max_epochs"),
        )

        train_batch_size = gr.Slider(
            minimum=1,
            maximum=8,
            step=1,
            value=1,
            label=t("training.batch_size"),
            info=t("training.batch_size_info"),
            elem_classes=["has-info-container"],
        )

        gradient_accumulation = gr.Slider(
            minimum=1,
            maximum=16,
            step=1,
            value=1,
            label=t("training.gradient_accumulation"),
            info=t("training.gradient_accumulation_info"),
            elem_classes=["has-info-container"],
        )

    with gr.Row():
        save_every_n_epochs = gr.Slider(
            minimum=1,
            maximum=1000,
            step=1,
            value=10,
            label=t("training.save_every_n_epochs"),
        )

        training_shift = gr.Slider(
            minimum=1.0,
            maximum=5.0,
            step=0.5,
            value=3.0,
            label=t("training.shift"),
            info=t("training.shift_info"),
            elem_classes=["has-info-container"],
        )

        training_seed = gr.Number(
            label=t("training.seed"),
            value=42,
            precision=0,
        )

    with gr.Row():
        lora_output_dir = gr.Textbox(
            label=t("training.output_dir"),
            value="./lora_output",
            placeholder="./lora_output",
            info=t("training.output_dir_info"),
            elem_classes=["has-info-container"],
        )

    with gr.Row():
        resume_checkpoint_dir = gr.Textbox(
            label="Resume Checkpoint",
            placeholder="./lora_output/checkpoints/epoch_200",
            info="Directory of a saved LoRA checkpoint to resume from",
            elem_classes=["has-info-container"],
        )

    gr.HTML("<hr>")

    with gr.Row():
        with gr.Column(scale=1):
            start_training_btn = gr.Button(
                t("training.start_training_btn"),
                variant="primary",
                size="lg",
            )
        with gr.Column(scale=1):
            stop_training_btn = gr.Button(
                t("training.stop_training_btn"),
                variant="stop",
                size="lg",
            )

    training_progress = gr.Textbox(
        label=t("training.training_progress"),
        interactive=False,
        lines=2,
    )

    with gr.Row():
        training_log = gr.Textbox(
            label=t("training.training_log"),
            interactive=False,
            lines=10,
            max_lines=15,
            scale=1,
        )
        training_loss_plot = gr.Plot(
            label=t("training.training_loss_title"),
            scale=1,
        )

    gr.HTML(f"<hr><h3>📦 {t('training.export_header')}</h3>")

    with gr.Row():
        export_path = gr.Textbox(
            label=t("training.export_path"),
            value="./lora_output/final_lora",
            placeholder="./lora_output/my_lora",
        )
        export_lora_btn = gr.Button(t("training.export_lora_btn"), variant="secondary")

    export_status = gr.Textbox(
        label=t("training.export_status"),
        interactive=False,
    )

    return {
        "learning_rate": learning_rate,
        "train_epochs": train_epochs,
        "train_batch_size": train_batch_size,
        "gradient_accumulation": gradient_accumulation,
        "save_every_n_epochs": save_every_n_epochs,
        "training_shift": training_shift,
        "training_seed": training_seed,
        "lora_output_dir": lora_output_dir,
        "resume_checkpoint_dir": resume_checkpoint_dir,
        "start_training_btn": start_training_btn,
        "stop_training_btn": stop_training_btn,
        "training_progress": training_progress,
        "training_log": training_log,
        "training_loss_plot": training_loss_plot,
        "export_path": export_path,
        "export_lora_btn": export_lora_btn,
        "export_status": export_status,
    }
