"""
ACE Studio - Modern Streamlit UI for Music Generation
Main application entry point
"""
import streamlit as st
import sys
from pathlib import Path

# Configure Streamlit page
st.set_page_config(
    page_title="ACE Studio",
    page_icon="🎹",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": (
            "https://github.com/ace-step/ACE-Step-1.5"
        ),
        "Report a bug": (
            "https://github.com/ace-step/ACE-Step-1.5/issues"
        ),
        "About": (
            "ACE Studio v0.1.0 - Streamlit UI for "
            "ACE-Step Music Generation"
        ),
    },
)

# Custom CSS
st.markdown(
    """
<style>
    .main { padding: 1rem; }
    [data-testid="stMetricValue"] { font-size: 1.5rem; }
    .stButton > button { border-radius: 8px; }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize session state
if "tab" not in st.session_state:
    st.session_state.tab = "dashboard"
if "editor_mode" not in st.session_state:
    st.session_state.editor_mode = "repaint"
if "selected_project" not in st.session_state:
    st.session_state.selected_project = None

# Import components
from components import (
    show_dashboard,
    show_generation_wizard,
    show_editor,
    show_batch_generator,
    show_settings_panel,
)
from utils import is_dit_ready, initialize_dit, initialize_llm

# ------------------------------------------------------------------
# Auto-initialise models on first load (runs once per session)
# ------------------------------------------------------------------
if "_models_auto_init_done" not in st.session_state:
    st.session_state._models_auto_init_done = True
    if not is_dit_ready():
        with st.spinner(
            "Loading DiT model (first launch, may take a minute)..."
        ):
            _status, _ok = initialize_dit(
                config_path="acestep-v15-turbo",
                device="auto",
                offload_to_cpu=(sys.platform != "darwin"),
            )
            if _ok:
                st.toast("DiT model loaded successfully", icon="✅")
            else:
                st.toast(
                    f"DiT auto-init failed: {_status}",
                    icon="⚠️",
                )
        # Also try LLM (non-blocking; optional)
        _backend = "mlx" if sys.platform == "darwin" else "vllm"
        with st.spinner("Loading LLM (optional, for CoT)..."):
            _lm_status, _lm_ok = initialize_llm(
                backend=_backend, device="auto",
            )
            if _lm_ok:
                st.toast("LLM loaded successfully", icon="✅")
            else:
                st.toast(
                    "LLM not loaded (optional)", icon="ℹ️",
                )

# ------------------------------------------------------------------
# Sidebar navigation
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🎹 ACE Studio")

    nav_selection = st.radio(
        "Select Tab",
        options=[
            "📊 Dashboard",
            "🎵 Generate",
            "🎛️ Edit",
            "📦 Batch",
            "⚙️ Settings",
        ],
        label_visibility="collapsed",
        index=[
            "dashboard",
            "generate",
            "editor",
            "batch",
            "settings",
        ].index(st.session_state.tab),
    )

    tab_map = {
        "📊 Dashboard": "dashboard",
        "🎵 Generate": "generate",
        "🎛️ Edit": "editor",
        "📦 Batch": "batch",
        "⚙️ Settings": "settings",
    }
    st.session_state.tab = tab_map[nav_selection]

    st.divider()

    # Quick project count
    try:
        from utils import ProjectManager
        from config import PROJECTS_DIR

        pm = ProjectManager(PROJECTS_DIR)
        projects = pm.list_projects()
        st.metric("💾 Projects", len(projects))
    except Exception:
        pass

    st.divider()

    # ------------------------------------------------------------------
    # Model status (lightweight - never loads weights here)
    # ------------------------------------------------------------------
    st.markdown("### 🤖 Model Status")

    from utils import is_llm_ready

    col1, col2 = st.columns(2)
    with col1:
        if is_dit_ready():
            st.success("✅ DiT")
        else:
            st.warning("⏳ DiT")
    with col2:
        if is_llm_ready():
            st.success("✅ LLM")
        else:
            st.info("⏸️ LLM")

    if not is_dit_ready():
        st.caption(
            "Go to **⚙️ Settings → Models** to initialise."
        )

    st.divider()

    # Quick help
    with st.expander("❓ Quick Help"):
        st.markdown(
            """
**Getting Started:**
1. Go to **Settings → Models** to load the AI model
2. Use **Generate** to create new songs
3. Use **Edit** to modify generated audio
4. Use **Batch** to generate multiple songs

**Tips:**
- Be descriptive in song captions
- Use editing to refine generated songs
"""
        )

# ------------------------------------------------------------------
# Main content area – route to selected tab
# ------------------------------------------------------------------
if st.session_state.tab == "dashboard":
    show_dashboard()
elif st.session_state.tab == "generate":
    show_generation_wizard()
elif st.session_state.tab == "editor":
    show_editor()
elif st.session_state.tab == "batch":
    show_batch_generator()
elif st.session_state.tab == "settings":
    show_settings_panel()
else:
    st.error(f"Unknown tab: {st.session_state.tab}")
    show_dashboard()

# Footer
st.divider()
st.markdown(
    """
<div style="text-align: center; color: #888; font-size: 0.85rem;">
    <p>
        🎵 <strong>ACE Studio</strong> v0.1.0 |
        Powered by
        <a href="https://github.com/ace-step/ACE-Step-1.5">
        ACE-Step</a> |
        <a href="https://discord.gg/PeWDxrkdj7">Discord</a>
    </p>
</div>
""",
    unsafe_allow_html=True,
)
