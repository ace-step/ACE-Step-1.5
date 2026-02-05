"""
History Event Handlers Module
"""
import os
import json
import glob
import datetime
import gradio as gr
from acestep.gradio_ui.events.results_handlers import DEFAULT_RESULTS_DIR
from acestep.gradio_ui.events.generation_handlers import load_metadata

def scan_history():
    """
    Scan the output directory for generated files and return data for the history table.

    Returns:
        List of lists for the dataframe: [ID, Filename, Date, Caption, Duration]
    """
    history_data = []

    # Walk through the output directory
    # Structure is usually: gradio_outputs/batch_TIMESTAMP/UUID.json
    # Or just flat in gradio_outputs?
    # generate_with_progress saves to: DEFAULT_RESULTS_DIR/batch_{timestamp}/{key}.json

    # We look for all .json files in subdirectories of DEFAULT_RESULTS_DIR
    json_pattern = os.path.join(DEFAULT_RESULTS_DIR, "**", "*.json")
    json_files = glob.glob(json_pattern, recursive=True)

    # Sort by modification time (newest first)
    json_files.sort(key=os.path.getmtime, reverse=True)

    for json_path in json_files:
        try:
            # Check if there is a corresponding audio file
            # Audio format could be mp3, flac, wav
            base_path = os.path.splitext(json_path)[0]
            audio_path = None
            for ext in [".mp3", ".flac", ".wav"]:
                if os.path.exists(base_path + ext):
                    audio_path = base_path + ext
                    break

            if not audio_path:
                continue

            # Read JSON metadata
            with open(json_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            # Extract info
            filename = os.path.basename(audio_path)
            timestamp = os.path.getmtime(json_path)
            date_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

            caption = meta.get('caption', '')
            if len(caption) > 50:
                caption = caption[:47] + "..."

            duration = meta.get('duration', 'N/A')
            if isinstance(duration, (int, float)):
                duration = f"{duration}s"

            # Use json_path as ID (hidden in dataframe logic usually, but here we show it or use index)
            # We'll use the full json path as the ID column
            history_data.append([json_path, filename, date_str, caption, duration])

        except Exception as e:
            print(f"Error reading history file {json_path}: {e}")
            continue

    return history_data

def select_history_item(evt: gr.SelectData, history_data):
    """
    Handle selection in the history table.

    Args:
        evt: Gradio SelectData
        history_data: The dataframe data

    Returns:
        audio_path, metadata_json, json_path, load_btn_interactive, send_src_btn_interactive, send_ref_btn_interactive
    """
    if evt.index is None:
        return None, None, None, gr.update(interactive=False), gr.update(interactive=False), gr.update(interactive=False)

    row_index = evt.index[0]

    if row_index >= len(history_data):
        return None, None, None, gr.update(interactive=False), gr.update(interactive=False), gr.update(interactive=False)

    # Get JSON path from the first column (ID)
    json_path = history_data[row_index][0]

    try:
        # Find audio path again
        base_path = os.path.splitext(json_path)[0]
        audio_path = None
        for ext in [".mp3", ".flac", ".wav"]:
            if os.path.exists(base_path + ext):
                audio_path = base_path + ext
                break

        with open(json_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        return audio_path, metadata, json_path, gr.update(interactive=True), gr.update(interactive=True), gr.update(interactive=True)

    except Exception as e:
        print(f"Error loading history item {json_path}: {e}")
        return None, {"error": str(e)}, None, gr.update(interactive=False), gr.update(interactive=False), gr.update(interactive=False)

def load_params_from_history(json_path, llm_handler):
    """
    Load parameters from the selected history item into the Generation tab.
    Wrapper around gen_h.load_metadata.
    """
    if not json_path:
        return [gr.skip()] * 37  # load_metadata returns 37 items

    return load_metadata(json_path, llm_handler)

def delete_history_item(json_path):
    """
    Delete the selected history item (JSON and associated audio).

    Args:
        json_path: Path to the JSON metadata file.

    Returns:
        Status message string.
    """
    if not json_path or not os.path.exists(json_path):
        return "File not found or no item selected"

    try:
        # Delete JSON
        os.remove(json_path)

        # Find audio path
        base_path = os.path.splitext(json_path)[0]
        audio_path = None
        for ext in [".mp3", ".flac", ".wav"]:
            if os.path.exists(base_path + ext):
                audio_path = base_path + ext
                break

        # Delete Audio
        if audio_path:
            os.remove(audio_path)

        return f"Deleted {os.path.basename(json_path)} and associated audio"
    except Exception as e:
        return f"Error deleting file: {str(e)}"
