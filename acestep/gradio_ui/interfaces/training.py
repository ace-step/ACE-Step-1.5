"""
Gradio UI Training Tab Module

Contains the dataset builder and LoRA training interface components.
"""

import os
import gradio as gr
from acestep.gradio_ui.i18n import t


def create_training_section(dit_handler, llm_handler, init_params=None) -> dict:
    """Create the training tab section with dataset builder and training controls.
    
    Args:
        dit_handler: DiT handler instance
        llm_handler: LLM handler instance
        init_params: Dictionary containing initialization parameters and state.
                    If None, service will not be pre-initialized.
        
    Returns:
        Dictionary of Gradio components for event handling
    """
    # Check if running in service mode (hide training tab)
    service_mode = init_params is not None and init_params.get('service_mode', False)
    
    with gr.Tab(t("training.tab_title"), visible=not service_mode):
        gr.HTML("""
        <div style="text-align: center; padding: 10px; margin-bottom: 15px;">
            <h2>🎵 LoRA Training for ACE-Step</h2>
            <p>Build datasets from your audio files and train custom LoRA adapters</p>
        </div>
        """)
        
        with gr.Tabs():
            # ==================== Dataset Builder Tab ====================
            with gr.Tab(t("training.tab_dataset_builder")):
                # ========== Load Existing OR Scan New ==========
                gr.HTML(f"""
                <div style="padding: 10px; margin-bottom: 10px; border: 1px solid #4a4a6a; border-radius: 8px; background: linear-gradient(135deg, #2a2a4a 0%, #1a1a3a 100%);">
                    <h3 style="margin: 0 0 5px 0;">{t("training.quick_start_title")}</h3>
                    <p style="margin: 0; color: #aaa;">Choose one: <b>Load existing dataset</b> OR <b>Scan new directory</b></p>
                </div>
                """)
                
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.HTML("<h4>📂 Load Existing Dataset</h4>")
                        with gr.Row():
                            load_json_path = gr.Textbox(
                                label=t("training.load_dataset_label"),
                                placeholder="./datasets/my_lora_dataset.json",
                                info=t("training.load_dataset_info"),
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
                        
                        # Audio files table
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
                        )

                        format_lyrics = gr.Checkbox(
                            label="Format Lyrics (LM)",
                            value=False,
                            info="Use LM to format/structure user-provided lyrics from .txt files (coming soon)",
                            interactive=False,  # Disabled for now - model update needed
                        )

                        transcribe_lyrics = gr.Checkbox(
                            label="Transcribe Lyrics (LM)",
                            value=False,
                            info="Use LM to transcribe lyrics from audio (coming soon)",
                            interactive=False,  # Disabled for now - model update needed
                        )
                        
                        custom_tag = gr.Textbox(
                            label=t("training.custom_tag"),
                            placeholder="e.g., 8bit_retro, my_style",
                            info=t("training.custom_tag_info"),
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
                        )

                        genre_ratio = gr.Slider(
                            minimum=0,
                            maximum=100,
                            step=10,
                            value=0,
                            label=t("training.genre_ratio"),
                            info=t("training.genre_ratio_info"),
                        )

                gr.HTML(f"<hr><h3>🤖 {t('training.step2_title')}</h3>")
                
                with gr.Row():
                    with gr.Column(scale=3):
                        gr.Markdown("""
                        Click the button below to automatically generate metadata for all audio files using AI:
                        - **Caption**: Music style, genre, mood description
                        - **BPM**: Beats per minute
                        - **Key**: Musical key (e.g., C Major, Am)
                        - **Time Signature**: 4/4, 3/4, etc.
                        """)
                        skip_metas = gr.Checkbox(
                            label=t("training.skip_metas"),
                            value=False,
                            info=t("training.skip_metas_info"),
                        )
                        only_unlabeled = gr.Checkbox(
                            label=t("training.only_unlabeled"),
                            value=False,
                            info=t("training.only_unlabeled_info"),
                        )
                    with gr.Column(scale=1):
                        auto_label_btn = gr.Button(
                            t("training.auto_label_btn"),
                            variant="primary",
                            size="lg",
                        )
                
                label_progress = gr.Textbox(
                    label=t("training.label_progress"),
                    interactive=False,
                    lines=2,
                )
                
                gr.HTML(f"<hr><h3>👀 {t('training.step3_title')}</h3>")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        sample_selector = gr.Slider(
                            minimum=0,
                            maximum=0,
                            step=1,
                            value=0,
                            label=t("training.select_sample"),
                            info=t("training.select_sample_info"),
                        )
                        
                        preview_audio = gr.Audio(
                            label=t("training.audio_preview"),
                            type="filepath",
                            interactive=False,
                        )
                        
                        preview_filename = gr.Textbox(
                            label=t("training.filename"),
                            interactive=False,
                        )

                    with gr.Column(scale=2):
                        with gr.Row():
                            edit_caption = gr.Textbox(
                                label=t("training.caption"),
                                lines=3,
                                placeholder="Music description...",
                            )

                        with gr.Row():
                            edit_genre = gr.Textbox(
                                label=t("training.genre"),
                                lines=1,
                                placeholder="pop, electronic, dance...",
                            )
                            prompt_override = gr.Dropdown(
                                choices=["Use Global Ratio", "Caption", "Genre"],
                                value="Use Global Ratio",
                                label=t("training.prompt_override_label"),
                                info=t("training.prompt_override_info"),
                            )

                        with gr.Row():
                            edit_lyrics = gr.Textbox(
                                label=t("training.lyrics_editable_label"),
                                lines=6,
                                placeholder="[Verse 1]\nLyrics here...\n\n[Chorus]\n...",
                            )
                            raw_lyrics_display = gr.Textbox(
                                label=t("training.raw_lyrics_label"),
                                lines=6,
                                placeholder=t("training.no_lyrics_placeholder"),
                                interactive=False,  # Read-only, can copy but not edit
                                visible=False,  # Hidden when no raw lyrics
                            )
                            has_raw_lyrics_state = gr.State(False)  # Track visibility

                        with gr.Row():
                            edit_bpm = gr.Number(
                                label=t("training.bpm"),
                                precision=0,
                            )
                            edit_keyscale = gr.Textbox(
                                label=t("training.key_label"),
                                placeholder=t("training.key_placeholder"),
                            )
                            edit_timesig = gr.Dropdown(
                                choices=["", "2", "3", "4", "6", "N/A"],
                                label=t("training.time_sig"),
                            )
                            edit_duration = gr.Number(
                                label=t("training.duration_s"),
                                precision=1,
                                interactive=False,
                            )
                        
                        with gr.Row():
                            edit_language = gr.Dropdown(
                                choices=["instrumental", "en", "zh", "ja", "ko", "es", "fr", "de", "pt", "ru", "unknown"],
                                value="instrumental",
                                label=t("training.language"),
                            )
                            edit_instrumental = gr.Checkbox(
                                label=t("training.instrumental"),
                                value=True,
                            )
                            save_edit_btn = gr.Button(t("training.save_changes_btn"), variant="secondary")
                        
                        edit_status = gr.Textbox(
                            label=t("training.edit_status"),
                            interactive=False,
                        )
                
                gr.HTML(f"<hr><h3>💾 {t('training.step4_title')}</h3>")
                
                with gr.Row():
                    with gr.Column(scale=3):
                        save_path = gr.Textbox(
                            label=t("training.save_path"),
                            value="./datasets/my_lora_dataset.json",
                            placeholder="./datasets/dataset_name.json",
                            info=t("training.save_path_info"),
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
                
                gr.Markdown("""
                **Preprocessing converts your dataset to pre-computed tensors for fast training.**
                
                You can either:
                - Use the dataset from Steps 1-4 above, **OR**
                - Load an existing dataset JSON file (if you've already saved one)
                """)
                
                with gr.Row():
                    with gr.Column(scale=3):
                        load_existing_dataset_path = gr.Textbox(
                            label=t("training.load_existing_label"),
                            placeholder="./datasets/my_lora_dataset.json",
                            info=t("training.load_existing_info"),
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
                
                gr.Markdown("""
                This step:
                - Encodes audio to VAE latents
                - Encodes captions and lyrics to text embeddings  
                - Runs the condition encoder
                - Saves all tensors to `.pt` files
                
                ⚠️ **This requires the model to be loaded and may take a few minutes.**
                """)
                
                with gr.Row():
                    with gr.Column(scale=3):
                        preprocess_output_dir = gr.Textbox(
                            label=t("training.tensor_output_dir"),
                            value="./datasets/preprocessed_tensors",
                            placeholder="./datasets/preprocessed_tensors",
                            info=t("training.tensor_output_info"),
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
            
            # ==================== Training Tab ====================
            with gr.Tab(t("training.tab_train_lora")):
                with gr.Row():
                    with gr.Column(scale=2):
                        gr.HTML(f"<h3>📊 {t('training.train_section_tensors')}</h3>")
                        
                        gr.Markdown("""
                        Select the directory containing preprocessed tensor files (`.pt` files).
                        These are created in the "Dataset Builder" tab using the "Preprocess" button.
                        """)
                        
                        training_tensor_dir = gr.Textbox(
                            label=t("training.preprocessed_tensors_dir"),
                            placeholder="./datasets/preprocessed_tensors",
                            value="./datasets/preprocessed_tensors",
                            info=t("training.preprocessed_tensors_info"),
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
                        )
                        
                        lora_alpha = gr.Slider(
                            minimum=4,
                            maximum=512,
                            step=4,
                            value=128,
                            label=t("training.lora_alpha"),
                            info=t("training.lora_alpha_info"),
                        )
                        
                        lora_dropout = gr.Slider(
                            minimum=0.0,
                            maximum=0.5,
                            step=0.05,
                            value=0.1,
                            label=t("training.lora_dropout"),
                        )
                
                gr.HTML(f"<hr><h3>🎛️ {t('training.train_section_params')}</h3>")
                
                with gr.Row():
                    learning_rate = gr.Number(
                        label=t("training.learning_rate"),
                        value=3e-4,
                        info=t("training.learning_rate_info"),
                    )
                    
                    train_epochs = gr.Slider(
                        minimum=100,
                        maximum=4000,
                        step=100,
                        value=1000,
                        label=t("training.max_epochs"),
                    )
                    
                    train_batch_size = gr.Slider(
                        minimum=1,
                        maximum=8,
                        step=1,
                        value=1,
                        label=t("training.batch_size"),
                        info=t("training.batch_size_info"),
                    )
                    
                    gradient_accumulation = gr.Slider(
                        minimum=1,
                        maximum=16,
                        step=1,
                        value=1,
                        label=t("training.gradient_accumulation"),
                        info=t("training.gradient_accumulation_info"),
                    )
                
                with gr.Row():
                    save_every_n_epochs = gr.Slider(
                        minimum=50,
                        maximum=1000,
                        step=50,
                        value=200,
                        label=t("training.save_every_n_epochs"),
                    )
                    
                    training_shift = gr.Slider(
                        minimum=1.0,
                        maximum=5.0,
                        step=0.5,
                        value=3.0,
                        label=t("training.shift"),
                        info=t("training.shift_info"),
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
                    training_loss_plot = gr.LinePlot(
                        x="step",
                        y="loss",
                        title=t("training.training_loss_title"),
                        x_title=t("training.step"),
                        y_title=t("training.loss"),
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
    
    # Store dataset builder state
    dataset_builder_state = gr.State(None)
    training_state = gr.State({"is_training": False, "should_stop": False})
    
    return {
        # Dataset Builder - Load or Scan
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
        "skip_metas": skip_metas,
        "only_unlabeled": only_unlabeled,
        "auto_label_btn": auto_label_btn,
        "label_progress": label_progress,
        "sample_selector": sample_selector,
        "preview_audio": preview_audio,
        "preview_filename": preview_filename,
        "edit_caption": edit_caption,
        "edit_genre": edit_genre,
        "prompt_override": prompt_override,
        "genre_ratio": genre_ratio,
        "edit_lyrics": edit_lyrics,
        "raw_lyrics_display": raw_lyrics_display,
        "has_raw_lyrics_state": has_raw_lyrics_state,
        "edit_bpm": edit_bpm,
        "edit_keyscale": edit_keyscale,
        "edit_timesig": edit_timesig,
        "edit_duration": edit_duration,
        "edit_language": edit_language,
        "edit_instrumental": edit_instrumental,
        "save_edit_btn": save_edit_btn,
        "edit_status": edit_status,
        "save_path": save_path,
        "save_dataset_btn": save_dataset_btn,
        "save_status": save_status,
        # Preprocessing
        "load_existing_dataset_path": load_existing_dataset_path,
        "load_existing_dataset_btn": load_existing_dataset_btn,
        "load_existing_status": load_existing_status,
        "preprocess_output_dir": preprocess_output_dir,
        "preprocess_btn": preprocess_btn,
        "preprocess_progress": preprocess_progress,
        "dataset_builder_state": dataset_builder_state,
        # Training
        "training_tensor_dir": training_tensor_dir,
        "load_dataset_btn": load_dataset_btn,
        "training_dataset_info": training_dataset_info,
        "lora_rank": lora_rank,
        "lora_alpha": lora_alpha,
        "lora_dropout": lora_dropout,
        "learning_rate": learning_rate,
        "train_epochs": train_epochs,
        "train_batch_size": train_batch_size,
        "gradient_accumulation": gradient_accumulation,
        "save_every_n_epochs": save_every_n_epochs,
        "training_shift": training_shift,
        "training_seed": training_seed,
        "lora_output_dir": lora_output_dir,
        "start_training_btn": start_training_btn,
        "stop_training_btn": stop_training_btn,
        "training_progress": training_progress,
        "training_log": training_log,
        "training_loss_plot": training_loss_plot,
        "export_path": export_path,
        "export_lora_btn": export_lora_btn,
        "export_status": export_status,
        "training_state": training_state,
    }
