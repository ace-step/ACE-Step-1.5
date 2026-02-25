"""
Help content module for Gradio UI.

Provides a reusable inline help button + modal component that displays
i18n-sourced Markdown documentation within the Gradio interface.

The button is rendered as a pure-HTML ``<span>`` so it takes zero layout
space and can be placed inside any existing row or header without
creating extra blank rows.
"""
from pathlib import Path
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
        elem_classes=["help-inline-container", "no-grow"],
    )

    return html


# ---------------------------------------------------------------------------
# CSS to be injected into the main Blocks CSS string.
# ---------------------------------------------------------------------------
css_file = Path(__file__).parent / "interfaces" / "css" / "help_modal.css"
HELP_MODAL_CSS = css_file.read_text()
