## 2025-02-18 - Gradio Icon-Only Buttons
**Learning:** This Gradio app frequently uses icon-only buttons (like 🎲) without text labels or tooltips, making them inaccessible and unclear.
**Action:** Always verify if `gr.Button` has a descriptive label or if `info` params are available on associated components to provide context.
