"""
Gradio UI LoRA & Training Page Module

Contains the LoRA management, dataset builder and training interface components.
"""

import os
import gradio as gr
from acestep.gradio_ui.i18n import t


def create_lora_page(dit_handler, llm_handler, init_params=None) -> dict:
    """Create the LoRA & Training page with management, dataset builder and training controls.
    
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
    
    # Check if LoRA is already loaded
    lora_loaded = dit_handler.lora_loaded if hasattr(dit_handler, 'lora_loaded') else False
    use_lora = dit_handler.use_lora if hasattr(dit_handler, 'use_lora') else False
    lora_scale = dit_handler.lora_scale if hasattr(dit_handler, 'lora_scale') else 1.0

    with gr.Tab("LoRA & Training", visible=not service_mode):
        gr.HTML("""
        <div style="text-align: center; padding: 10px; margin-bottom: 15px;">
            <h2>LoRA & Training</h2>
            <p>Manage, build datasets, and train custom LoRA adapters</p>
        </div>
        """)
        
        with gr.Tabs():
            # ==================== Load & Manage Tab ====================
            with gr.Tab("🔧 Load & Manage"):
                gr.HTML("""
                <div style="padding: 10px; margin-bottom: 10px; border: 1px solid #4a4a6a; border-radius: 8px; background: linear-gradient(135deg, #2a2a4a 0%, #1a1a3a 100%);">
                    <h3 style="margin: 0 0 5px 0;">Load LoRA Adapter</h3>
                    <p style="margin: 0; color: #aaa;">Load a trained LoRA adapter to use for generation.</p>
                </div>
                """)

                with gr.Row():
                    lora_path = gr.Textbox(
                        label="LoRA Path",
                        placeholder="./lora_output/final/adapter",
                        info="Path to trained LoRA adapter directory",
                        scale=3,
                    )
                    load_lora_btn = gr.Button("📥 Load LoRA", variant="secondary", scale=1)
                    unload_lora_btn = gr.Button("🗑️ Unload", variant="secondary", scale=1)

                gr.HTML("<hr><h3>LoRA Settings</h3>")
                with gr.Row():
                    use_lora_checkbox = gr.Checkbox(
                        label="Use LoRA",
                        value=use_lora,
                        info="Enable LoRA adapter for inference",
                        scale=1,
                        interactive=True  # Always interactive, handler logic handles check
                    )
                    lora_scale_slider = gr.Slider(
                        minimum=0.0,
                        maximum=1.0,
                        value=lora_scale,
                        step=0.05,
                        label="LoRA Scale",
                        info="LoRA influence strength (0=disabled, 1=full)",
                        scale=2,
                    )
                    lora_status = gr.Textbox(
                        label="LoRA Status",
                        value="LoRA Loaded" if lora_loaded else "No LoRA loaded",
                        interactive=False,
                        scale=2,
                    )

            # ==================== Dataset Builder Tab ====================
            with gr.Tab("📁 Dataset Builder"):
                # ========== Load Existing OR Scan New ==========
                gr.HTML("""
                <div style="padding: 10px; margin-bottom: 10px; border: 1px solid #4a4a6a; border-radius: 8px; background: linear-gradient(135deg, #2a2a4a 0%, #1a1a3a 100%);">
                    <h3 style="margin: 0 0 5px 0;">🚀 Quick Start</h3>
                    <p style="margin: 0; color: #aaa;">Choose one: <b>Load existing dataset</b> OR <b>Scan new directory</b></p>
                </div>
                """)
                
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.HTML("<h4>📂 Load Existing Dataset</h4>")
                        with gr.Row():
                            load_json_path = gr.Textbox(
                                label="Dataset JSON Path",
                                placeholder="./datasets/my_lora_dataset.json",
                                info="Load a previously saved dataset",
                                scale=3,
                            )
                            load_json_btn = gr.Button("📂 Load", variant="primary", scale=1)
                        load_json_status = gr.Textbox(
                            label="Load Status",
                            interactive=False,
                        )
                    
                    with gr.Column(scale=1):
                        gr.HTML("<h4>🔍 Scan New Directory</h4>")
                        with gr.Row():
                            audio_directory = gr.Textbox(
                                label="Audio Directory Path",
                                placeholder="/path/to/your/audio/folder",
                                info="Scan for audio files (wav, mp3, flac, ogg, opus)",
                                scale=3,
                            )
                            scan_btn = gr.Button("🔍 Scan", variant="secondary", scale=1)
                        scan_status = gr.Textbox(
                            label="Scan Status",
                            interactive=False,
                        )
                
                gr.HTML("<hr>")
                
                with gr.Row():
                    with gr.Column(scale=2):
                        
                        # Audio files table
                        audio_files_table = gr.Dataframe(
                            headers=["#", "Filename", "Duration", "Lyrics", "Labeled", "BPM", "Key", "Caption"],
                            datatype=["number", "str", "str", "str", "str", "str", "str", "str"],
                            label="Found Audio Files",
                            interactive=False,
                            wrap=True,
                        )
                    
                    with gr.Column(scale=1):
                        gr.HTML("<h3>⚙️ Dataset Settings</h3>")
                        
                        dataset_name = gr.Textbox(
                            label="Dataset Name",
                            value="my_lora_dataset",
                            placeholder="Enter dataset name",
                        )
                        
                        all_instrumental = gr.Checkbox(
                            label="All Instrumental",
                            value=True,
                            info="Check if all tracks are instrumental (no vocals)",
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
                            label="Custom Activation Tag",
                            placeholder="e.g., 8bit_retro, my_style",
                            info="Unique tag to activate this LoRA's style",
                        )
                        
                        tag_position = gr.Radio(
                            choices=[
                                ("Prepend (tag, caption)", "prepend"),
                                ("Append (caption, tag)", "append"),
                                ("Replace caption", "replace"),
                            ],
                            value="replace",
                            label="Tag Position",
                            info="Where to place the custom tag in the caption",
                        )

                        genre_ratio = gr.Slider(
                            minimum=0,
                            maximum=100,
                            step=10,
                            value=0,
                            label="Genre Ratio (%)",
                            info="0%=all Caption, 100%=all Genre. Per-sample override takes priority.",
                        )

                gr.HTML("<hr><h3>🤖 Step 2: Auto-Label with AI</h3>")
                
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
                            label="Skip BPM/Key/Time Signature",
                            value=False,
                            info="Skip BPM/Key/Time Signature generation. Caption and Genre are still generated by LLM.",
                        )
                        only_unlabeled = gr.Checkbox(
                            label="Only Unlabeled",
                            value=False,
                            info="Only label samples without caption (useful for resuming failed labeling)",
                        )
                    with gr.Column(scale=1):
                        auto_label_btn = gr.Button(
                            "🏷️ Auto-Label All",
                            variant="primary",
                            size="lg",
                        )
                
                label_progress = gr.Textbox(
                    label="Labeling Progress",
                    interactive=False,
                    lines=2,
                )
                
                gr.HTML("<hr><h3>👀 Step 3: Preview & Edit</h3>")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        sample_selector = gr.Slider(
                            minimum=0,
                            maximum=0,
                            step=1,
                            value=0,
                            label="Select Sample #",
                            info="Choose a sample to preview and edit",
                        )
                        
                        preview_audio = gr.Audio(
                            label="Audio Preview",
                            type="filepath",
                            interactive=False,
                        )
                        
                        preview_filename = gr.Textbox(
                            label="Filename",
                            interactive=False,
                        )

                    with gr.Column(scale=2):
                        with gr.Row():
                            edit_caption = gr.Textbox(
                                label="Caption",
                                lines=3,
                                placeholder="Music description...",
                            )

                        with gr.Row():
                            edit_genre = gr.Textbox(
                                label="Genre",
                                lines=1,
                                placeholder="pop, electronic, dance...",
                            )
                            prompt_override = gr.Dropdown(
                                choices=["Use Global Ratio", "Caption", "Genre"],
                                value="Use Global Ratio",
                                label="Prompt Override (this sample)",
                                info="Override global ratio for this sample",
                            )

                        with gr.Row():
                            edit_lyrics = gr.Textbox(
                                label="Lyrics (editable, used for training)",
                                lines=6,
                                placeholder="[Verse 1]\nLyrics here...\n\n[Chorus]\n...",
                            )
                            raw_lyrics_display = gr.Textbox(
                                label="Raw Lyrics (from .txt file)",
                                lines=6,
                                placeholder="(no .txt lyrics file)",
                                interactive=False,  # Read-only, can copy but not edit
                                visible=False,  # Hidden when no raw lyrics
                            )
                            has_raw_lyrics_state = gr.State(False)  # Track visibility

                        with gr.Row():
                            edit_bpm = gr.Number(
                                label="BPM",
                                precision=0,
                            )
                            edit_keyscale = gr.Textbox(
                                label="Key",
                                placeholder="C Major",
                            )
                            edit_timesig = gr.Dropdown(
                                choices=["", "2", "3", "4", "6", "N/A"],
                                label="Time Signature",
                            )
                            edit_duration = gr.Number(
                                label="Duration (s)",
                                precision=1,
                                interactive=False,
                            )
                        
                        with gr.Row():
                            edit_language = gr.Dropdown(
                                choices=["instrumental", "en", "zh", "ja", "ko", "es", "fr", "de", "pt", "ru", "unknown"],
                                value="instrumental",
                                label="Language",
                            )
                            edit_instrumental = gr.Checkbox(
                                label="Instrumental",
                                value=True,
                            )
                            save_edit_btn = gr.Button("💾 Save Changes", variant="secondary")
                        
                        edit_status = gr.Textbox(
                            label="Edit Status",
                            interactive=False,
                        )
                
                gr.HTML("<hr><h3>💾 Step 4: Save Dataset</h3>")
                
                with gr.Row():
                    with gr.Column(scale=3):
                        save_path = gr.Textbox(
                            label="Save Path",
                            value="./datasets/my_lora_dataset.json",
                            placeholder="./datasets/dataset_name.json",
                            info="Path where the dataset JSON will be saved",
                        )
                    with gr.Column(scale=1):
                        save_dataset_btn = gr.Button(
                            "💾 Save Dataset",
                            variant="primary",
                            size="lg",
                        )
                
                save_status = gr.Textbox(
                    label="Save Status",
                    interactive=False,
                    lines=2,
                )
                
                gr.HTML("<hr><h3>⚡ Step 5: Preprocess to Tensors</h3>")
                
                gr.Markdown("""
                **Preprocessing converts your dataset to pre-computed tensors for fast training.**
                
                You can either:
                - Use the dataset from Steps 1-4 above, **OR**
                - Load an existing dataset JSON file (if you've already saved one)
                """)
                
                with gr.Row():
                    with gr.Column(scale=3):
                        load_existing_dataset_path = gr.Textbox(
                            label="Load Existing Dataset (Optional)",
                            placeholder="./datasets/my_lora_dataset.json",
                            info="Path to a previously saved dataset JSON file",
                        )
                    with gr.Column(scale=1):
                        load_existing_dataset_btn = gr.Button(
                            "📂 Load Dataset",
                            variant="secondary",
                            size="lg",
                        )
                
                load_existing_status = gr.Textbox(
                    label="Load Status",
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
                            label="Tensor Output Directory",
                            value="./datasets/preprocessed_tensors",
                            placeholder="./datasets/preprocessed_tensors",
                            info="Directory to save preprocessed tensor files",
                        )
                    with gr.Column(scale=1):
                        preprocess_btn = gr.Button(
                            "⚡ Preprocess",
                            variant="primary",
                            size="lg",
                        )
                
                preprocess_progress = gr.Textbox(
                    label="Preprocessing Progress",
                    interactive=False,
                    lines=3,
                )
            
            # ==================== Training Tab ====================
            with gr.Tab("🚀 Train LoRA"):
                with gr.Row():
                    with gr.Column(scale=2):
                        gr.HTML("<h3>📊 Preprocessed Dataset Selection</h3>")
                        
                        gr.Markdown("""
                        Select the directory containing preprocessed tensor files (`.pt` files).
                        These are created in the "Dataset Builder" tab using the "Preprocess" button.
                        """)
                        
                        training_tensor_dir = gr.Textbox(
                            label="Preprocessed Tensors Directory",
                            placeholder="./datasets/preprocessed_tensors",
                            value="./datasets/preprocessed_tensors",
                            info="Directory containing preprocessed .pt tensor files",
                        )
                        
                        load_dataset_btn = gr.Button("📂 Load Dataset", variant="secondary")
                        
                        training_dataset_info = gr.Textbox(
                            label="Dataset Info",
                            interactive=False,
                            lines=3,
                        )
                    
                    with gr.Column(scale=1):
                        gr.HTML("<h3>⚙️ LoRA Settings</h3>")
                        
                        lora_rank = gr.Slider(
                            minimum=4,
                            maximum=256,
                            step=4,
                            value=64,
                            label="LoRA Rank (r)",
                            info="Higher = more capacity, more memory",
                        )
                        
                        lora_alpha = gr.Slider(
                            minimum=4,
                            maximum=512,
                            step=4,
                            value=128,
                            label="LoRA Alpha",
                            info="Scaling factor (typically 2x rank)",
                        )
                        
                        lora_dropout = gr.Slider(
                            minimum=0.0,
                            maximum=0.5,
                            step=0.05,
                            value=0.1,
                            label="LoRA Dropout",
                        )
                
                gr.HTML("<hr><h3>🎛️ Training Parameters</h3>")
                
                with gr.Row():
                    learning_rate = gr.Number(
                        label="Learning Rate",
                        value=3e-4,
                        info="Start with 3e-4, adjust if needed",
                    )
                    
                    train_epochs = gr.Slider(
                        minimum=100,
                        maximum=4000,
                        step=100,
                        value=1000,
                        label="Max Epochs",
                    )
                    
                    train_batch_size = gr.Slider(
                        minimum=1,
                        maximum=8,
                        step=1,
                        value=1,
                        label="Batch Size",
                        info="Increase if you have enough VRAM",
                    )
                    
                    gradient_accumulation = gr.Slider(
                        minimum=1,
                        maximum=16,
                        step=1,
                        value=1,
                        label="Gradient Accumulation",
                        info="Effective batch = batch_size × accumulation",
                    )
                
                with gr.Row():
                    save_every_n_epochs = gr.Slider(
                        minimum=50,
                        maximum=1000,
                        step=50,
                        value=200,
                        label="Save Every N Epochs",
                    )
                    
                    training_shift = gr.Slider(
                        minimum=1.0,
                        maximum=5.0,
                        step=0.5,
                        value=3.0,
                        label="Shift",
                        info="Timestep shift for turbo model",
                    )
                    
                    training_seed = gr.Number(
                        label="Seed",
                        value=42,
                        precision=0,
                    )
                
                with gr.Row():
                    lora_output_dir = gr.Textbox(
                        label="Output Directory",
                        value="./lora_output",
                        placeholder="./lora_output",
                        info="Directory to save trained LoRA weights",
                    )
                
                gr.HTML("<hr>")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        start_training_btn = gr.Button(
                            "🚀 Start Training",
                            variant="primary",
                            size="lg",
                        )
                    with gr.Column(scale=1):
                        stop_training_btn = gr.Button(
                            "⏹️ Stop Training",
                            variant="stop",
                            size="lg",
                        )
                
                training_progress = gr.Textbox(
                    label="Training Progress",
                    interactive=False,
                    lines=2,
                )
                
                with gr.Row():
                    training_log = gr.Textbox(
                        label="Training Log",
                        interactive=False,
                        lines=10,
                        max_lines=15,
                        scale=1,
                    )
                    training_loss_plot = gr.LinePlot(
                        x="step",
                        y="loss",
                        title="Training Loss",
                        x_title="Step",
                        y_title="Loss",
                        scale=1,
                    )
                
                gr.HTML("<hr><h3>📦 Export LoRA</h3>")
                
                with gr.Row():
                    export_path = gr.Textbox(
                        label="Export Path",
                        value="./lora_output/final_lora",
                        placeholder="./lora_output/my_lora",
                    )
                    export_lora_btn = gr.Button("📦 Export LoRA", variant="secondary")
                
                export_status = gr.Textbox(
                    label="Export Status",
                    interactive=False,
                )
    
    # Store dataset builder state
    dataset_builder_state = gr.State(None)
    training_state = gr.State({"is_training": False, "should_stop": False})
    
    return {
        # LoRA Manage
        "lora_path": lora_path,
        "load_lora_btn": load_lora_btn,
        "unload_lora_btn": unload_lora_btn,
        "use_lora_checkbox": use_lora_checkbox,
        "lora_scale_slider": lora_scale_slider,
        "lora_status": lora_status,
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
