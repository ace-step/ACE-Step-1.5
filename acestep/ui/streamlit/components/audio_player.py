"""
Audio player widget - play and control audio playback
"""
import streamlit as st
from pathlib import Path
from typing import Optional


def audio_player_widget(audio_path: str, label: str = "Audio", show_download: bool = True):
    """Display audio player with controls
    
    Args:
        audio_path: Path to audio file
        label: Label for the audio player
        show_download: Show download button
    """
    audio_file = Path(audio_path)
    
    if not audio_file.exists():
        st.error(f"❌ Audio file not found: {audio_path}")
        return
    
    # Read audio file
    with open(audio_file, "rb") as f:
        audio_bytes = f.read()
    
    # Display audio player
    st.audio(audio_bytes, format="audio/wav")
    
    # File info
    col1, col2, col3 = st.columns(3)
    
    with col1:
        file_size_mb = audio_file.stat().st_size / 1e6
        st.metric("File Size", f"{file_size_mb:.2f} MB")
    
    with col2:
        # Try to get duration
        try:
            import librosa
            duration = librosa.get_duration(filename=audio_path)
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            st.metric("Duration", f"{minutes}m {seconds}s")
        except:
            st.metric("Duration", "Unknown")
    
    with col3:
        st.metric("Format", audio_file.suffix.upper())
    
    # Download button
    if show_download:
        st.download_button(
            label="📥 Download Audio",
            data=audio_bytes,
            file_name=audio_file.name,
            mime="audio/wav",
            use_container_width=True
        )


def simple_audio_player(audio_path: str, label: str = "▶️ Play"):
    """Simple inline audio player"""
    audio_file = Path(audio_path)
    
    if not audio_file.exists():
        return
    
    with open(audio_file, "rb") as f:
        audio_bytes = f.read()
    
    st.audio(audio_bytes, format="audio/wav")
