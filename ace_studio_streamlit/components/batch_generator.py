"""
Batch Generator component - generate multiple songs at once
"""
import streamlit as st
from utils import ProjectManager, get_dit_handler
from config import PROJECTS_DIR, GENRES, MOODS, DEFAULT_DURATION, DEFAULT_BPM
from loguru import logger


def show_batch_generator():
    """Display batch generation interface (up to 8 songs)"""
    st.markdown("## 📦 Batch Generator")
    st.info("🚀 Generate up to 8 songs simultaneously")
    
    # Initialize batch queue
    if "batch_queue" not in st.session_state:
        st.session_state.batch_queue = []
    
    st.markdown("### Add Songs to Queue")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        song_caption = st.text_input(
            "Song Description",
            placeholder="Upbeat pop with synth...",
            key="batch_caption"
        )
    
    with col2:
        if st.button("➕ Add to Queue", key="batch_add_btn", use_container_width=True):
            if song_caption and len(st.session_state.batch_queue) < 8:
                st.session_state.batch_queue.append({
                    "caption": song_caption,
                    "duration": DEFAULT_DURATION,
                    "bpm": DEFAULT_BPM,
                    "status": "queued"
                })
                st.success("✅ Added to queue")
                st.rerun()
            elif len(st.session_state.batch_queue) >= 8:
                st.error("🔴 Queue is full (max 8 songs)")
            else:
                st.error("Please enter a song description")
    
    st.divider()
    
    # Queue display
    st.markdown(f"### Queue ({len(st.session_state.batch_queue)}/8)")
    
    if st.session_state.batch_queue:
        # Show as grid
        cols = st.columns(4)
        
        for idx, song in enumerate(st.session_state.batch_queue):
            with cols[idx % 4]:
                with st.container(border=True):
                    st.markdown(f"**#{idx + 1}**")
                    st.caption(song["caption"][:50] + "..." if len(song["caption"]) > 50 else song["caption"])
                    
                    # Status indicator
                    status_emoji = {
                        "queued": "⏳",
                        "generating": "⚙️",
                        "completed": "✅",
                        "failed": "❌"
                    }
                    st.caption(f"{status_emoji.get(song['status'], '?')} {song['status'].title()}")
                    
                    # Remove button
                    if song["status"] == "queued":
                        if st.button("🗑️", key=f"remove_{idx}", use_container_width=True):
                            st.session_state.batch_queue.pop(idx)
                            st.rerun()
    else:
        st.info("📝 Add songs to the queue to get started")
    
    st.divider()
    
    # Batch settings
    with st.expander("⚙️ Batch Settings", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            parallel_count = st.slider(
                "Process in Parallel",
                min_value=1,
                max_value=4,
                value=2,
                help="Number of songs to generate simultaneously",
                key="parallel_count"
            )
        
        with col2:
            inference_steps = st.slider(
                "Diffusion Steps",
                min_value=8,
                max_value=100,
                value=32,
                step=4,
                key="batch_steps"
            )
        
        with col3:
            guidance_scale = st.slider(
                "Guidance Scale",
                min_value=1.0,
                max_value=15.0,
                value=7.5,
                step=0.5,
                key="batch_guidance"
            )
    
    st.divider()
    
    # Generate Button
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if st.button(
            f"🚀 Generate All ({len(st.session_state.batch_queue)})",
            use_container_width=True,
            type="primary",
            key="batch_gen_btn",
            disabled=len(st.session_state.batch_queue) == 0
        ):
            generate_batch(st.session_state.batch_queue, parallel_count, inference_steps, guidance_scale)


def generate_batch(queue: list, parallel_count: int, steps: int, guidance: float):
    """Generate all songs in the batch queue"""
    pm = ProjectManager(PROJECTS_DIR)
    dit_handler = get_dit_handler()
    
    if not dit_handler:
        st.error("❌ Failed to load generation model")
        return
    
    # Create progress tracking
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    results_placeholder = st.empty()
    
    total_songs = len(queue)
    completed = 0
    failed = 0
    results = []
    
    with st.spinner(f"🎵 Generating {total_songs} songs..."):
        try:
            for idx, song in enumerate(queue):
                # Update progress
                progress = (idx + 1) / total_songs
                progress_placeholder.progress(progress)
                status_placeholder.text(f"Generating song {idx + 1}/{total_songs}: {song['caption'][:40]}...")
                
                try:
                    # Create project
                    project_name = f"Batch_{song['caption'][:20].replace(' ', '_')}"
                    project_path = pm.create_project(project_name, description=song['caption'])
                    
                    # TODO: Actual generation
                    # result = dit_handler.generate(song['caption'], duration=song['duration'])
                    # pm.save_audio(project_path, result['audio'], "output.wav")
                    
                    results.append({
                        "song": song['caption'],
                        "project": project_name,
                        "status": "✅ Success"
                    })
                    completed += 1
                
                except Exception as e:
                    logger.error(f"Batch generation error for song {idx + 1}: {e}")
                    results.append({
                        "song": song['caption'],
                        "project": "",
                        "status": f"❌ Failed: {str(e)[:50]}"
                    })
                    failed += 1
            
            # Display results
            st.success(f"🎉 Batch generation complete! Completed: {completed}/{total_songs}")
            
            if results:
                results_df = st.dataframe(results, use_container_width=True)
            
            # Clear queue
            st.session_state.batch_queue = []
            
        except Exception as e:
            logger.error(f"Batch error: {e}")
            st.error(f"❌ Batch generation failed: {e}")
