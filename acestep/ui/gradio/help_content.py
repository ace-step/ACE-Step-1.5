"""
Help content module for Gradio UI.

Provides a reusable inline help button + modal component that displays
i18n-sourced Markdown documentation within the Gradio interface.

The button is rendered as a pure-HTML ``<span>`` so it takes zero layout
space and can be placed inside any existing row or header without
creating extra blank rows.
"""
import gradio as gr
from acestep.ui.gradio.i18n import t

# Unique counter to avoid DOM id collisions across multiple help buttons.
_help_counter = 0


def _next_id() -> str:
    """Return a unique DOM id suffix for each help modal instance."""
    global _help_counter
    _help_counter += 1
    return str(_help_counter)


def _md_to_html(md_text: str) -> str:
    """Convert Markdown to HTML with basic formatting.

    Handles headings, bold, italic, code blocks, lists, blockquotes,
    and paragraphs.  Intentionally lightweight so we avoid adding an
    external ``markdown`` dependency.

    Args:
        md_text: Markdown-formatted string.

    Returns:
        HTML string.
    """
    import re

    lines = md_text.split("\n")
    html_parts: list[str] = []
    in_code = False
    in_list = False

    for line in lines:
        # Fenced code blocks
        if line.strip().startswith("```"):
            if in_code:
                html_parts.append("</code></pre>")
                in_code = False
            else:
                html_parts.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            html_parts.append(line)
            continue

        stripped = line.strip()

        # Close list if line is not a list item
        if in_list and not stripped.startswith("- ") and not re.match(r"^\d+\.", stripped):
            html_parts.append("</ul>")
            in_list = False

        # Headings
        if stripped.startswith("### "):
            heading = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2" target="_blank" style="color:var(--color-accent,#4a9eff);">\1</a>',
                stripped[4:],
            )
            html_parts.append(f"<h4>{heading}</h4>")
            continue
        if stripped.startswith("## "):
            heading = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2" target="_blank" style="color:var(--color-accent,#4a9eff);">\1</a>',
                stripped[3:],
            )
            html_parts.append(f"<h3>{heading}</h3>")
            continue

        # Blockquotes
        if stripped.startswith("> "):
            content = stripped[2:]
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
            content = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2" target="_blank" style="color:var(--color-accent,#4a9eff);">\1</a>',
                content,
            )
            html_parts.append(
                f'<blockquote style="border-left:3px solid #888;'
                f'padding-left:10px;color:#aaa;">{content}</blockquote>'
            )
            continue

        # List items
        if stripped.startswith("- ") or re.match(r"^\d+\.\s", stripped):
            if not in_list:
                html_parts.append("<ul style='padding-left:20px;'>")
                in_list = True
            content = re.sub(r"^-\s|^\d+\.\s", "", stripped)
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
            content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)
            content = re.sub(r"`([^`]+)`", r"<code>\1</code>", content)
            content = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2" target="_blank" style="color:var(--color-accent,#4a9eff);">\1</a>',
                content,
            )
            html_parts.append(f"<li>{content}</li>")
            continue

        # Empty line
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("<br/>")
            continue

        # Regular paragraph
        p = stripped
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"\*(.+?)\*", r"<em>\1</em>", p)
        p = re.sub(r"`([^`]+)`", r"<code>\1</code>", p)
        p = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2" target="_blank" style="color:var(--color-accent,#4a9eff);">\1</a>',
            p,
        )
        html_parts.append(f"<p style='margin:4px 0;'>{p}</p>")

    if in_list:
        html_parts.append("</ul>")
    if in_code:
        html_parts.append("</code></pre>")

    return "\n".join(html_parts)


def create_help_button(section_key: str) -> gr.HTML:
    """Create an inline (?) help button that opens a modal with documentation.

    The entire widget (button + hidden modal) is a single ``gr.HTML``
    component so it takes minimal layout space and can be placed inside
    any existing ``gr.Row`` without creating extra blank areas.

    Args:
        section_key: The i18n sub-key under ``help.`` (e.g. ``"generation_simple"``).

    Returns:
        The ``gr.HTML`` instance.
    """
    uid = _next_id()
    modal_id = f"help-modal-{uid}"
    btn_id = f"help-btn-{uid}"
    md_content = t(f"help.{section_key}")
    html_content = _md_to_html(md_content)
    close_label = t("help.close_label")

    html = gr.HTML(
        value=f"""
        <span class="help-inline-wrapper">
          <button id="{btn_id}" class="help-inline-btn"
                  onclick="document.getElementById('{modal_id}').style.display='flex'"
                  title="Help">?</button>
        </span>
        <div id="{modal_id}" class="help-modal-overlay" style="display:none;"
             onclick="if(event.target===this)this.style.display='none'">
          <div class="help-modal-content">
            <button class="help-modal-close"
                    onclick="document.getElementById('{modal_id}').style.display='none'">
              {close_label}
            </button>
            <div class="help-modal-body">
              {html_content}
            </div>
          </div>
        </div>
        """,
        elem_classes=["help-inline-container"],
    )

    return html


# ---------------------------------------------------------------------------
# CSS to be injected into the main Blocks CSS string.
# ---------------------------------------------------------------------------
HELP_MODAL_CSS = """
/* ---- Inline help button container ---- */
.help-inline-container {
    min-height: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    display: inline-flex !important;
    align-items: center !important;
    flex-shrink: 0 !important;
    max-width: 32px !important;
    min-width: 32px !important;
    overflow: visible !important;
}

.help-inline-wrapper {
    display: inline-flex;
    align-items: center;
    line-height: 1;
}

/* ---- Inline help button ---- */
.help-inline-btn {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 1.5px solid var(--border-color-primary, #555);
    background: transparent;
    color: var(--body-text-color-subdued, #888);
    font-size: 12px;
    font-weight: 600;
    line-height: 20px;
    text-align: center;
    cursor: pointer;
    padding: 0;
    transition: all 0.15s ease;
    flex-shrink: 0;
}
.help-inline-btn:hover {
    background: var(--color-accent, #4a9eff);
    color: #fff;
    border-color: var(--color-accent, #4a9eff);
    transform: scale(1.1);
}

/* ---- Modal overlay ---- */
.help-modal-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.5);
    z-index: 100000;
    display: flex;
    justify-content: center;
    align-items: center;
}

.help-modal-content {
    background: var(--background-fill-primary, #fff);
    color: var(--body-text-color, #222);
    border-radius: 12px;
    max-width: 640px;
    width: 90%;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    position: relative;
}

.help-modal-close {
    position: absolute;
    top: 12px; right: 16px;
    background: none;
    border: none;
    font-size: 20px;
    cursor: pointer;
    color: var(--body-text-color, #222);
    z-index: 1;
    opacity: 0.6;
}
.help-modal-close:hover { opacity: 1; }

.help-modal-body {
    padding: 28px 32px;
    overflow-y: auto;
    line-height: 1.7;
    font-size: 0.92rem;
}
.help-modal-body h3 { margin: 16px 0 8px; font-size: 1.15rem; }
.help-modal-body h4 { margin: 12px 0 6px; font-size: 1.0rem; }
.help-modal-body pre {
    background: var(--background-fill-secondary, #f5f5f5);
    padding: 10px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 0.85rem;
}
.help-modal-body code {
    background: var(--background-fill-secondary, #f5f5f5);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 0.88em;
}
.help-modal-body ul { margin: 6px 0; }
.help-modal-body li { margin: 3px 0; }
"""
