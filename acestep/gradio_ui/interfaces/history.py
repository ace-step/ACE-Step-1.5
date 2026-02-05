"""
Gradio UI History Tab Module
Contains the history library component definitions
"""
import gradio as gr
from acestep.gradio_ui.i18n import t

def create_history_section() -> dict:
    """Create the history tab section.

    Returns:
        Dictionary of Gradio components for event handling
    """
    with gr.Tab("📚 History"):
        gr.HTML("""
        <div style="text-align: center; padding: 10px; margin-bottom: 15px;">
            <h2>Generation History</h2>
            <p>View past generations and reload their settings</p>
        </div>
        """)

        with gr.Row():
            with gr.Column(scale=3):
                refresh_history_btn = gr.Button("🔄 Refresh", variant="secondary")
                # Dataframe to list files
                # Columns: ID (timestamp), Filename, Date, Caption, Duration, Status
                history_table = gr.Dataframe(
                    headers=["ID", "Filename", "Date", "Caption", "Duration"],
                    datatype=["str", "str", "str", "str", "str"],
                    label="Generated Files",
                    interactive=False,
                    wrap=True,
                    type="array",
                )

            with gr.Column(scale=2):
                gr.HTML("<h3>Details</h3>")

                selected_audio = gr.Audio(label="Audio Preview", type="filepath", interactive=False)

                with gr.Accordion("Metadata", open=True):
                    selected_metadata = gr.JSON(label="Full Metadata")

                with gr.Row():
                    send_to_src_btn = gr.Button("🎵 Send to Source Audio", interactive=False)
                    send_to_ref_btn = gr.Button("🎹 Send to Reference Audio", interactive=False)

                load_params_btn = gr.Button("📋 Load Parameters to Generation Tab", variant="primary", interactive=False)

                # Hidden state to store the full path of the selected item
                selected_item_path = gr.State(None)

    return {
        "refresh_history_btn": refresh_history_btn,
        "history_table": history_table,
        "selected_audio": selected_audio,
        "selected_metadata": selected_metadata,
        "send_to_src_btn": send_to_src_btn,
        "send_to_ref_btn": send_to_ref_btn,
        "load_params_btn": load_params_btn,
        "selected_item_path": selected_item_path,
    }
