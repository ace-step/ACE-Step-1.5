"""
Dashboard component - shows recent projects and quick start options
"""
import streamlit as st
from datetime import datetime
from utils import ProjectManager
from config import PROJECTS_DIR, GENERATION_MODES


def show_dashboard():
    """Display dashboard with recent projects and quick start options"""
    st.markdown("# 🎹 ACE Studio")
    st.markdown("*Music Generation & Editing Made Easy*")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🎵 Generate New", key="quick_gen", use_container_width=True, type="primary"):
            st.session_state.tab = "generate"
            st.rerun()
    
    with col2:
        if st.button("🎤 Create Cover", key="quick_cover", use_container_width=True):
            st.session_state.tab = "editor"
            st.session_state.editor_mode = "cover"
            st.rerun()
    
    with col3:
        if st.button("🎨 Edit Song", key="quick_edit", use_container_width=True):
            st.session_state.tab = "editor"
            st.session_state.editor_mode = "repaint"
            st.rerun()
    
    with col4:
        if st.button("📦 Batch", key="quick_batch", use_container_width=True):
            st.session_state.tab = "batch"
            st.rerun()
    
    st.divider()
    
    # Recent Projects Section
    st.markdown("## 📚 Recent Projects")
    
    pm = ProjectManager(PROJECTS_DIR)
    projects = pm.list_projects()
    
    if projects:
        # Display as grid
        cols = st.columns(3)
        for idx, project in enumerate(projects[:6]):  # Show first 6
            with cols[idx % 3]:
                with st.container():
                    st.markdown(f"### {project['name']}")
                    
                    # Metadata
                    if project.get('genre'):
                        st.caption(f"🎼 {project['genre']}")
                    if project.get('mood'):
                        st.caption(f"💭 {project['mood']}")
                    if project.get('duration'):
                        st.caption(f"⏱️ {project['duration']}s @ {project.get('bpm', '?')} BPM")
                    
                    # Modified time
                    modified = datetime.fromisoformat(project['modified_at'])
                    st.caption(f"📅 {modified.strftime('%b %d, %H:%M')}")
                    
                    # Action buttons
                    col_play, col_edit, col_del = st.columns(3)
                    with col_play:
                        if st.button("▶️", key=f"play_{project['name']}", help="Play"):
                            st.session_state.selected_project = project['name']
                            st.session_state.tab = "editor"
                            st.rerun()
                    
                    with col_edit:
                        if st.button("✏️", key=f"edit_{project['name']}", help="Edit"):
                            st.session_state.selected_project = project['name']
                            st.session_state.tab = "editor"
                            st.rerun()
                    
                    with col_del:
                        if st.button("🗑️", key=f"del_{project['name']}", help="Delete"):
                            if pm.delete_project(project['name']):
                                st.success(f"Deleted: {project['name']}")
                                st.rerun()
    else:
        st.info("✨ No projects yet. Generate your first song!")
    
    st.divider()
    
    # Statistics
    st.markdown("## 📊 Stats")
    metrics_cols = st.columns(4)
    with metrics_cols[0]:
        st.metric("Total Projects", len(projects))
    with metrics_cols[1]:
        total_duration = sum(p.get('duration', 0) for p in projects)
        st.metric("Total Duration", f"{total_duration // 60}m" if total_duration else "0m")
    with metrics_cols[2]:
        st.metric("Favorite Mood", "Coming Soon", help="Based on generated songs")
    with metrics_cols[3]:
        st.metric("Favorite Genre", "Coming Soon", help="Based on generated songs")
