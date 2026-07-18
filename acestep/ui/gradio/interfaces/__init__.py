"""
Gradio UI Components Module
Contains all Gradio interface component definitions and layouts

Layout:
  ┌──────────────────────────────────────┐
  │  Header                              │
  ├──────────────────────────────────────┤
  │  Dataset Explorer (hidden accordion) │
  ├──────────────────────────────────────┤
  │  Settings (accordion, collapsed)     │
  │   ├─ Service Configuration           │
  │   ├─ DiT Parameters                  │
  │   ├─ LM Parameters                   │
  │   └─ Output / Automation             │
  ├──────────────────────────────────────┤
  │  ┌─ Generation ─┬─ Training ──────┐  │
  │  │  Mode Radio   │  Dataset/LoRA  │  │
  │  │  Inputs       │                │  │
  │  │  Results      │                │  │
  │  └───────────────┴────────────────┘  │
  └──────────────────────────────────────┘
"""
import gradio as gr
from acestep.ui.gradio.i18n import get_i18n, t
from acestep.ui.gradio.interfaces.dataset import create_dataset_section
from acestep.ui.gradio.interfaces.generation import (
    create_advanced_settings_section,
    create_generation_tab_section,
)
from acestep.ui.gradio.interfaces.simple_ui import build_simple_ui
from acestep.ui.gradio.interfaces.audio_player_preferences import (
    get_audio_player_preferences_head,
)
from acestep.ui.gradio.interfaces.user_preferences import (
    get_user_preferences_head,
    wire_preference_restore,
)
from acestep.ui.gradio.interfaces.result import create_results_section
from acestep.ui.gradio.interfaces.training import create_training_section
from acestep.ui.gradio.events import (
    setup_event_handlers,
    setup_simple_ui_handlers,
    setup_training_event_handlers,
)
from acestep.ui.gradio.help_content import create_help_button, HELP_MODAL_CSS


def create_gradio_interface(dit_handler, llm_handler, dataset_handler, init_params=None, language='en') -> gr.Blocks:
    """
    Create Gradio interface
    
    Args:
        dit_handler: DiT handler instance
        llm_handler: LM handler instance
        dataset_handler: Dataset handler instance
        init_params: Dictionary containing initialization parameters and state.
                    If None, service will not be pre-initialized.
        language: UI language code ('en', 'zh', 'ja', default: 'en')
        
    Returns:
        Gradio Blocks instance
    """
    # Update i18n with selected language
    i18n = get_i18n(language)
    
    # Check if running in service mode (hide training tab)
    service_mode = init_params is not None and init_params.get('service_mode', False)
    
    with gr.Blocks(
        title=t("app.title"),
        theme=gr.themes.Soft(),
        head=get_audio_player_preferences_head() + ("" if service_mode else get_user_preferences_head()) + """
        <script>
        /* Flip tooltips upward when they would overflow the viewport bottom.
           Handles both .has-info-container and .checkbox-container elements. */
        document.addEventListener('mouseover', function(e) {
            var el = e.target.closest('.has-info-container, .checkbox-container');
            if (!el) return;
            var rect = el.getBoundingClientRect();
            if (rect.bottom > window.innerHeight * 0.65) {
                el.classList.add('tooltip-flip');
            } else {
                el.classList.remove('tooltip-flip');
            }
        });
        </script>
        """,
        css="""
        .main-header {
            text-align: center;
            margin-bottom: 2rem;
        }
        .section-header {
            background: linear-gradient(90deg, #4CAF50, #45a049);
            color: white;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .lm-hints-row {
            align-items: stretch;
        }
        .lm-hints-col {
            display: flex;
        }
        .lm-hints-col > div {
            flex: 1;
            display: flex;
        }
        .lm-hints-btn button {
            height: 100%;
            width: 100%;
        }
        /* Position Audio time labels lower to avoid scrollbar overlap */
        .component-wrapper > .timestamps {
            transform: translateY(15px);
        }
        /* Equal-height row for instrumental checkbox + enhance lyrics button */
        .instrumental-row {
            align-items: stretch !important;
        }
        .instrumental-row > div {
            display: flex !important;
            align-items: stretch !important;
        }
        .instrumental-row > div > div {
            flex: 1;
            display: flex;
            align-items: center;
        }
        .instrumental-row button {
            height: 100% !important;
            min-height: 42px;
        }
        /* Ensure buttons in instrumental-row fill height */
        .instrumental-row > div > button {
            height: 100% !important;
            min-height: 42px;
        }
        /* Two-line icon buttons: emoji on top, text below */
        .icon-btn-wrap button, .icon-btn-wrap > button {
            word-spacing: 100vw;
            text-align: center;
            line-height: 1.4;
        }

        /* --- On-hover Tooltips --- */
        /* Safely ensure parents don't clip the tooltips using the container class */
        .has-info-container {
            overflow: visible !important;
            contain: none !important;
        }

        /* Ensure immediate flex parents (like rows, accordions) also allow overflow if they contain an info container */
        .row:has(.has-info-container),
        .column:has(.has-info-container),
        .form:has(.has-info-container),
        .accordion:has(.has-info-container),
        .tabs:has(.has-info-container),
        .gr-block:has(.has-info-container),
        .gr-box:has(.has-info-container) {
            overflow: visible !important;
            contain: none !important;
        }

        /* Hide info text by default and format as tooltip.
           In Gradio 6, info is often a div following the span[data-testid="block-info"].
           Uses visibility/opacity (not display:none) so the tooltip remains interactive
           and doesn't collapse when the user moves their mouse onto it to scroll. */
        .has-info-container span[data-testid="block-info"] + div,
        .has-info-container span[data-testid="block-info"] + span,
        .checkbox-container + div {
            visibility: hidden;
            opacity: 0;
            transition: opacity 0.1s ease, visibility 0.1s ease;
            transition-delay: 0.08s;
            position: absolute;
            background: rgba(25, 25, 25, 0.98);
            color: #ffffff;
            padding: 12px 16px;
            border-radius: 10px;
            font-size: 0.85rem;
            z-index: 999999;
            max-width: 320px;
            min-width: 180px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.5);
            pointer-events: none;
            line-height: 1.5;
            margin-top: 6px;
            border: 1px solid rgba(255,255,255,0.15);
            backdrop-filter: blur(10px);
            left: 0;
            font-weight: 400;
            text-transform: none;
        }

        /* Prevent tooltip CSS from hiding content inside .no-tooltip components */
        .no-tooltip span[data-testid="block-info"] + div,
        .no-tooltip span[data-testid="block-info"] + span {
            display: block !important;
            position: static !important;
            background: none !important;
            padding: 0 !important;
            border: none !important;
            box-shadow: none !important;
            backdrop-filter: none !important;
            max-width: none !important;
            min-width: 0 !important;
            z-index: auto !important;
            pointer-events: auto !important;
            margin-top: 0 !important;
            color: inherit !important;
            font-size: inherit !important;
            line-height: inherit !important;
            font-weight: inherit !important;
            text-transform: inherit !important;
            border-radius: 0 !important;
        }
        .no-tooltip span[data-testid="block-info"]::after {
            display: none !important;
        }

        /* Show tooltips on hover of the label/icon, OR when hovering the tooltip itself.
           The sibling :hover rule keeps the tooltip visible while the user scrolls it. */
        .has-info-container span[data-testid="block-info"]:hover + div,
        .has-info-container span[data-testid="block-info"]:hover + span,
        .has-info-container span[data-testid="block-info"] + div:hover,
        .has-info-container span[data-testid="block-info"] + span:hover,
        .checkbox-container:hover + div,
        .checkbox-container + div:hover {
            visibility: visible !important;
            opacity: 1 !important;
            transition-delay: 0s;
        }

        /* ═══════════════════════════════════════════
           ✦ Simple UI — 5-Step Creative Studio ✦
           ═══════════════════════════════════════════ */

        /* ── Container ── */
        #simple-ui-column {
            max-width: 680px;
            margin: 0 auto;
            padding: 0 1rem 2rem;
            background: #faf8f6;
            min-height: 0;
            height: auto;
            overflow: hidden;
        }
        #simple-ui-column > div:empty {
            display: none !important;
        }
        #simple-ui-column .gr-form {
            min-height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
        }

        /* ── Header ── */
        .simple-header {
            position: relative;
            padding: 1.25rem 1.5rem 1rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 0 0 24px 24px;
            margin: 0 -1rem 1.25rem;
        }
        .simple-header-content {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            justify-content: center;
        }
        .simple-header-icon {
            flex-shrink: 0;
            display: flex;
        }
        .simple-header-icon svg {
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.15));
        }
        .simple-header-text {
            text-align: left;
        }
        .simple-header-text h2 {
            font-size: 1.25rem;
            font-weight: 700;
            margin: 0;
            color: #ffffff;
            letter-spacing: -0.01em;
            line-height: 1.3;
        }
        .simple-header-text p {
            font-size: 0.8rem;
            color: rgba(255,255,255,0.7);
            margin: 0.1rem 0 0;
            line-height: 1.3;
        }

        /* ── Hamburger button ── */
        .simple-hamburger-btn {
            position: absolute !important;
            top: 0.75rem !important;
            right: 0.75rem !important;
            z-index: 10 !important;
            background: rgba(255,255,255,0.15) !important;
            border: none !important;
            border-radius: 8px !important;
            color: white !important;
            font-size: 0 !important;
            padding: 0.25rem 0.5rem !important;
            line-height: 1 !important;
            min-width: 0 !important;
            width: auto !important;
            cursor: pointer !important;
            transition: background 0.15s ease !important;
        }
        .simple-hamburger-btn::before {
            content: "";
            display: block;
            width: 22px;
            height: 22px;
            background: currentColor;
            -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M4 6h16M4 12h16M4 18h16' fill='none' stroke='black' stroke-width='2.5' stroke-linecap='round'/%3E%3C/svg%3E") center/contain no-repeat;
            mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M4 6h16M4 12h16M4 18h16' fill='none' stroke='black' stroke-width='2.5' stroke-linecap='round'/%3E%3C/svg%3E") center/contain no-repeat;
        }
        .simple-hamburger-btn:hover {
            background: rgba(255,255,255,0.25) !important;
        }

        /* ── Hamburger dropdown menu ── */
        .simple-hamburger-menu {
            position: absolute !important;
            top: 3rem !important;
            right: 0.75rem !important;
            z-index: 20 !important;
            background: #ffffff !important;
            border: 1px solid #e2dff0 !important;
            border-radius: 12px !important;
            box-shadow: 0 8px 24px rgba(0,0,0,0.12) !important;
            padding: 0.35rem !important;
            min-width: 180px !important;
            overflow: visible !important;
        }
        .simple-hamburger-menu > div,
        .simple-hamburger-menu > div > div {
            background: #ffffff !important;
            border-color: transparent !important;
        }
        .simple-menu-item {
            width: 100% !important;
            justify-content: flex-start !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 0.5rem 0.85rem !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            color: #1a1a2e !important;
            background: transparent !important;
            transition: background 0.1s ease !important;
            text-align: left !important;
            gap: 0.65rem !important;
        }
        .simple-menu-item::before {
            content: "";
            display: inline-block;
            flex: 0 0 18px;
            width: 18px;
            height: 18px;
            background-color: #667eea;
            -webkit-mask-position: center;
            -webkit-mask-repeat: no-repeat;
            -webkit-mask-size: contain;
            mask-position: center;
            mask-repeat: no-repeat;
            mask-size: contain;
        }
        .simple-menu-about::before {
            -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='12' r='9' fill='none' stroke='black' stroke-width='2'/%3E%3Cpath d='M12 11v6M12 7h.01' fill='none' stroke='black' stroke-width='2.5' stroke-linecap='round'/%3E%3C/svg%3E");
            mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='12' r='9' fill='none' stroke='black' stroke-width='2'/%3E%3Cpath d='M12 11v6M12 7h.01' fill='none' stroke='black' stroke-width='2.5' stroke-linecap='round'/%3E%3C/svg%3E");
        }
        .simple-menu-help::before {
            -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='12' r='9' fill='none' stroke='black' stroke-width='2'/%3E%3Cpath d='M9.8 9a2.4 2.4 0 1 1 3.4 2.2c-.8.4-1.2.9-1.2 1.8M12 17h.01' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");
            mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='12' r='9' fill='none' stroke='black' stroke-width='2'/%3E%3Cpath d='M9.8 9a2.4 2.4 0 1 1 3.4 2.2c-.8.4-1.2.9-1.2 1.8M12 17h.01' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");
        }
        .simple-menu-advanced::before {
            -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M7 14v6' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");
            mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M7 14v6' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");
        }
        .simple-menu-item:hover {
            background: #f4f2ff !important;
        }

        /* ── About Overlay ── */
        .simple-about-backdrop {
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            z-index: 9999 !important;
            background: rgba(0,0,0,0.45) !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            backdrop-filter: blur(4px) !important;
        }
        .simple-about-modal {
            background: #ffffff !important;
            border-radius: 20px !important;
            padding: 2.5rem 2rem !important;
            max-width: 440px !important;
            width: 90% !important;
            text-align: center !important;
            box-shadow: 0 20px 60px rgba(0,0,0,0.2) !important;
            position: relative !important;
        }
        .simple-about-close {
            position: absolute !important;
            top: 0.75rem !important;
            right: 1rem !important;
            background: none !important;
            border: none !important;
            font-size: 1.5rem !important;
            color: #999 !important;
            cursor: pointer !important;
            padding: 0.25rem !important;
            line-height: 1 !important;
        }
        .simple-about-close:hover {
            color: #333 !important;
        }
        .simple-about-icon {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
        .simple-about-modal h2 {
            font-size: 1.2rem;
            font-weight: 700;
            color: #1a1a2e;
            margin: 0 0 0.3rem;
        }
        .simple-about-subtitle {
            font-size: 0.85rem;
            color: #667eea;
            font-weight: 600;
            margin: 0 0 0.75rem;
        }
        .simple-about-desc {
            font-size: 0.85rem;
            color: #666;
            line-height: 1.5;
            margin: 0;
        }

        /* ── Hidden help button container ── */
        .simple-help-container {
            position: fixed !important;
            top: -9999px !important;
            left: -9999px !important;
            opacity: 0 !important;
            pointer-events: none !important;
            height: 0 !important;
            overflow: hidden !important;
        }

        /* ── Step Indicator ── */
        .simple-step-indicator {
            margin: 0 0 1.5rem;
            overflow: visible !important;
            contain: none !important;
        }

        /* ── Step Columns ── */
        .simple-step {
            /* Gradio 6 can hide a Column's children while leaving its layout shell
               mounted. A transparent layout wrapper prevents that shell from
               rendering as an empty bordered row. Inline display:none still wins
               when Gradio hides the Column itself. */
            display: contents;
        }
        /* Gradio can place its hidden marker on either the component or its host.
           Collapse the single step boundary without overriding child display rules. */
        .simple-step.hide,
        .simple-step.hidden,
        .simple-step[hidden],
        .simple-step[style*="display: none"],
        .hide:has(> .simple-step),
        .hidden:has(> .simple-step),
        [hidden]:has(> .simple-step) {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            gap: 0 !important;
        }

        /* Collapse any Gradio wrapper that contains ONLY hidden content */
        #simple-ui-column > div:empty {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        @keyframes simpleFadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        /* ── Text Inputs ── */
        .simple-input label {
            font-size: 0.95rem !important;
            font-weight: 600 !important;
            color: #1a1a2e !important;
            margin-bottom: 0.3rem !important;
        }
        .simple-input textarea {
            border-radius: 12px !important;
            border: 2px solid #e2dff0 !important;
            padding: 12px 16px !important;
            font-size: 0.95rem !important;
            line-height: 1.5 !important;
            transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
            background: #ffffff !important;
            color: #1a1a2e !important;
            resize: vertical !important;
        }
        .simple-input textarea:focus {
            border-color: #667eea !important;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15) !important;
            outline: none !important;
        }
        .simple-input textarea::placeholder {
            color: #b0aec0 !important;
        }
        .simple-lyrics textarea {
            min-height: 160px !important;
        }
        .simple-instrumental {
            width: fit-content !important;
            margin: -0.25rem 0 0.25rem auto !important;
            padding: 0.25rem 0.5rem !important;
        }
        .simple-instrumental label {
            font-size: 0.85rem !important;
        }

        /* ── Navigation Row ── */
        .simple-nav-row {
            margin-top: 1.25rem !important;
            display: flex !important;
            justify-content: space-between !important;
            gap: 0.75rem !important;
        }

        /* ── Buttons ── */
        .simple-random-btn {
            border: 2px solid #e2dff0 !important;
            border-radius: 10px !important;
            padding: 0.5rem 1.25rem !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            color: #1a1a2e !important;
            background: #ffffff !important;
            transition: all 0.15s ease !important;
        }
        .simple-random-btn::before {
            content: "";
            display: inline-block;
            width: 16px;
            height: 16px;
            margin-right: 6px;
            vertical-align: middle;
            background: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNjY3ZWVhIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHJlY3QgeD0iMyIgeT0iMyIgd2lkdGg9IjE4IiBoZWlnaHQ9IjE4IiByeD0iMiIvPjxjaXJjbGUgY3g9IjgiIGN5PSI4IiByPSIxLjUiLz48Y2lyY2xlIGN4PSIxNiIgY3k9IjgiIHI9IjEuNSIvPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjEuNSIvPjxjaXJjbGUgY3g9IjgiIGN5PSIxNiIgcj0iMS41Ii8+PGNpcmNsZSBjeD0iMTYiIGN5PSIxNiIgcj0iMS41Ii8+PC9zdmc+") no-repeat center;
            background-size: contain;
        }
        .simple-random-btn:hover {
            border-color: #667eea !important;
            background: #f8f7ff !important;
        }

        .simple-back-btn {
            border: 2px solid #e2dff0 !important;
            border-radius: 10px !important;
            padding: 0.5rem 1.25rem !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            color: #1a1a2e !important;
            background: #ffffff !important;
            transition: all 0.15s ease !important;
        }
        .simple-back-btn::before {
            content: "";
            display: inline-block;
            width: 16px;
            height: 16px;
            margin-right: 6px;
            vertical-align: middle;
            background: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNjY3ZWVhIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PGxpbmUgeDE9IjE5IiB5MT0iMTIiIHgyPSI1IiB5Mj0iMTIiLz48cG9seWxpbmUgcG9pbnRzPSIxMiAxOSA1IDEyIDEyIDUiLz48L3N2Zz4=") no-repeat center;
            background-size: contain;
        }
        .simple-back-btn:hover {
            border-color: #667eea !important;
            background: #f8f7ff !important;
        }

        .simple-continue-btn {
            border-radius: 10px !important;
            padding: 0.5rem 1.75rem !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            background: linear-gradient(135deg, #667eea, #764ba2) !important;
            border: none !important;
            color: #ffffff !important;
            transition: all 0.15s ease !important;
            box-shadow: 0 2px 6px rgba(102, 126, 234, 0.25) !important;
        }
        .simple-continue-btn:hover {
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.35) !important;
        }
        .simple-continue-btn:active {
            transform: translateY(0) !important;
        }
        .simple-continue-btn::after {
            content: "";
            display: inline-block;
            width: 16px;
            height: 16px;
            margin-left: 6px;
            vertical-align: middle;
            background: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxsaW5lIHgxPSI1IiB5MT0iMTIiIHgyPSIxOSIgeTI9IjEyIi8+PHBvbHlsaW5lIHBvaW50cz0iMTIgNSAxOSAxMiAxMiAxOSIvPjwvc3ZnPg==") no-repeat center;
            background-size: contain;
        }

        /* ── Upload Area (Step 3) ── */
        .simple-upload-label {
            font-size: 0.9rem;
            font-weight: 600;
            color: #1a1a2e;
            margin-bottom: 0.35rem !important;
        }
        .simple-upload-area {
            border: 2px dashed #d0cce8 !important;
            border-radius: 12px !important;
            padding: 0.5rem !important;
            background: #faf9ff !important;
            transition: all 0.2s ease !important;
            text-align: center !important;
            min-height: 0 !important;
        }
        .simple-upload-area > div:first-child {
            min-height: 0 !important;
            padding: 0.25rem 0 !important;
        }
        .simple-upload-area:hover {
            border-color: #667eea !important;
            background: #f4f2ff !important;
        }
        /* Suppress empty child wrappers inside the upload area */
        .simple-upload-area > div:empty,
        .simple-upload-area .gr-box:empty {
            display: none !important;
        }
        /* Hide waveform display before any audio is loaded */
        .simple-upload-area audio,
        .simple-upload-area canvas,
        .simple-upload-area .waveform-container {
            display: none !important;
        }
        /* Hide the record/mic source button — upload only */
        .simple-upload-area button[aria-label*="mic"],
        .simple-upload-area button[aria-label*="record"] {
            display: none !important;
        }

        /* ── Create Button (Step 3) ── */
        #simple-create-btn {
            width: 100% !important;
            padding: 1rem 2rem !important;
            font-size: 1.15rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.01em;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
            border: none !important;
            border-radius: 14px !important;
            color: #ffffff !important;
            box-shadow: 0 4px 14px rgba(102, 126, 234, 0.35) !important;
            transition: transform 0.12s ease, box-shadow 0.12s ease !important;
            cursor: pointer !important;
        }
        #simple-create-btn::before {
            content: "";
            display: inline-block;
            width: 20px;
            height: 20px;
            margin-right: 8px;
            vertical-align: middle;
            background: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiIHN0cm9rZT0ibm9uZSI+PHBvbHlnb24gcG9pbnRzPSI1IDMgMTkgMTIgNSAyMSA1IDMiLz48L3N2Zz4=") no-repeat center;
            background-size: contain;
        }
        #simple-create-btn:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.45) !important;
        }
        #simple-create-btn:active {
            transform: translateY(0) !important;
            box-shadow: 0 3px 10px rgba(102, 126, 234, 0.3) !important;
        }

        /* ── Creating Step (Step 4) ── */
        .simple-creating-icon {
            text-align: center;
            padding: 2rem 0 1rem;
            animation: simplePulse 1.5s ease-in-out infinite;
        }
        @keyframes simplePulse {
            0%, 100% { opacity: 0.6; transform: scale(1); }
            50% { opacity: 1; transform: scale(1.1); }
        }
        .simple-creating-title {
            text-align: center;
            font-size: 1.2rem;
            font-weight: 600;
            color: #1a1a2e;
            margin: 0 0 1.5rem;
        }
        .simple-progress-track {
            width: 100%;
            height: 8px;
            background: #e8e6f0;
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 1rem;
        }
        .simple-progress-bar {
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2, #667eea);
            background-size: 200% 100%;
            border-radius: 4px;
            animation: simpleProgressSlide 1.5s ease-in-out infinite;
        }
        @keyframes simpleProgressSlide {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
        .simple-progress-status {
            text-align: center;
            font-size: 0.9rem;
            color: #8e8ea0;
            padding: 0.5rem 0;
            min-height: 2rem;
        }

        /* ── Results Step (Step 5) ── */
        .simple-divider-wrap {
            flex: 0 0 auto !important;
            min-height: 0 !important;
            width: 100% !important;
        }
        .simple-divider {
            display: flex;
            align-items: center;
            gap: 8px;
            justify-content: center;
            margin: 0 0 0.75rem;
            font-size: 0.9rem;
            font-weight: 600;
            color: #667eea;
        }
        .simple-divider::before,
        .simple-divider::after {
            content: "";
            flex: 1;
            height: 1px;
            background: linear-gradient(90deg, transparent, #d0cce8, transparent);
        }

        .simple-results-row {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            flex: 0 0 auto !important;
            width: 100% !important;
            align-items: stretch !important;
            gap: 0.75rem !important;
            margin-bottom: 0.5rem !important;
        }
        .simple-result-col {
            position: relative;
            width: 100% !important;
            min-width: 0 !important;
            flex-grow: 0 !important;
            min-height: 0 !important;
            gap: 0.25rem !important;
            padding: 0.5rem !important;
        }

        .simple-best-badge {
            display: inline-flex;
            position: absolute;
            top: 0.75rem;
            left: 0.75rem;
            z-index: 2;
            align-items: center;
            gap: 4px;
            background: linear-gradient(135deg, #f6d365 0%, #fda085 100%);
            color: white;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 3px 10px;
            border-radius: 20px;
            margin: 0;
        }

        .simple-audio {
            border-radius: 8px !important;
            overflow: hidden !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
            min-height: 0 !important;
            margin: 0 !important;
        }
        .simple-audio audio {
            height: 36px !important;
        }

        .simple-meta-row {
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            padding: 0.15rem 0 !important;
            gap: 0.5rem !important;
        }
        .simple-metadata {
            font-size: 0.8rem;
            color: #8e8ea0;
        }
        .simple-meta-text {
            white-space: nowrap;
        }

        .simple-save-btn {
            border: 2px solid #e2dff0 !important;
            border-radius: 8px !important;
            padding: 0.35rem 0.75rem !important;
            font-size: 0.8rem !important;
            background: #ffffff !important;
            transition: all 0.15s ease !important;
            min-width: 40px !important;
        }
        .simple-save-btn::before {
            content: "";
            display: inline-block;
            width: 16px;
            height: 16px;
            vertical-align: middle;
            background: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNjY3ZWVhIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTIxIDE1djRhMiAyIDAgMCAxLTIgMkg1YTIgMiAwIDAgMS0yLTJ2LTQiLz48cG9seWxpbmUgcG9pbnRzPSI3IDEwIDEyIDE1IDE3IDEwIi8+PGxpbmUgeDE9IjEyIiB5MT0iMTUiIHgyPSIxMiIgeTI9IjMiLz48L3N2Zz4=") no-repeat center;
            background-size: contain;
        }
        .simple-save-btn:hover {
            border-color: #667eea !important;
            background: #f8f7ff !important;
        }

        .simple-gen-info {
            flex: 0 0 auto !important;
            width: 100% !important;
            margin: 0.35rem 0 0.5rem;
        }
        .simple-gen-status {
            text-align: center;
            padding: 0.4rem 0.75rem;
            border-radius: 10px;
            font-size: 0.85rem;
            font-weight: 500;
        }
        .simple-gen-status.success {
            background: rgba(16, 185, 129, 0.08);
            color: #047857;
        }
        .simple-gen-status.info {
            background: rgba(102, 126, 234, 0.08);
            color: #5b4fc4;
        }

        /* ── Footer Buttons (Step 5) ── */
        .simple-footer-row {
            display: flex !important;
            flex: 0 0 auto !important;
            width: 100% !important;
            gap: 0.75rem !important;
            justify-content: center !important;
            margin-top: 0.25rem !important;
        }
        .simple-retry-btn {
            border: 2px solid #e2dff0 !important;
            border-radius: 10px !important;
            padding: 0.5rem 1.25rem !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            background: #ffffff !important;
            transition: all 0.15s ease !important;
        }
        .simple-retry-btn::before {
            content: "";
            display: inline-block;
            width: 16px;
            height: 16px;
            margin-right: 6px;
            vertical-align: middle;
            background: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNjY3ZWVhIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBvbHlsaW5lIHBvaW50cz0iMjMgNCAyMyAxMCAxNyAxMCIvPjxwb2x5bGluZSBwb2ludHM9IjEgMjAgMSAxNCA3IDE0Ii8+PHBhdGggZD0iTTMuNTEgOWE5IDkgMCAwIDEgMTQuODUtMy4zNkwyMyAxME0xIDE0bDQuNjQgNC4zNkE5IDkgMCAwIDAgMjAuNDkgMTUiLz48L3N2Zz4=") no-repeat center;
            background-size: contain;
        }
        .simple-retry-btn:hover {
            border-color: #667eea !important;
            background: #f8f7ff !important;
        }

        .simple-new-btn {
            border: 2px solid #e2dff0 !important;
            border-radius: 10px !important;
            padding: 0.5rem 1.25rem !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            background: #ffffff !important;
            transition: all 0.15s ease !important;
        }
        .simple-new-btn::before {
            content: "";
            display: inline-block;
            width: 16px;
            height: 16px;
            margin-right: 6px;
            vertical-align: middle;
            background: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNjY3ZWVhIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTkgMThWNWwxMi0ydjEzIi8+PGNpcmNsZSBjeD0iNiIgY3k9IjE4IiByPSIzIi8+PGNpcmNsZSBjeD0iMTgiIGN5PSIxNiIgcj0iMyIvPjwvc3ZnPg==") no-repeat center;
            background-size: contain;
        }
        .simple-new-btn:hover {
            border-color: #667eea !important;
            background: #f8f7ff !important;
        }

        /* ── Collapse hidden containers properly ── */
        .simple-hamburger-menu {
            transition: none !important;
        }
        .simple-hamburger-menu ~ div:empty {
            display: none !important;
        }

        /* ── Responsive ── */
        @media (max-width: 640px) {
            #simple-ui-column {
                padding: 0 0.5rem 2rem;
            }
            .simple-header {
                margin: 0 -0.5rem 1rem;
                padding: 1rem 0.75rem;
            }
            .simple-header-text h2 {
                font-size: 1rem;
            }
            .simple-header-text p {
                font-size: 0.75rem;
            }
            .simple-header-icon svg {
                width: 24px;
                height: 24px;
            }
            .simple-results-row {
                grid-template-columns: minmax(0, 1fr) !important;
            }
            .simple-nav-row {
                flex-direction: row !important;
                gap: 0.5rem !important;
            }
        }

        /* ── Advanced Mode Toggle Row ── */
        .advanced-mode-row {
            align-items: center !important;
            justify-content: space-between !important;
            margin-bottom: 0.5rem !important;
            padding: 0.25rem 0 !important;
        }
        .advanced-mode-label {
            font-size: 1rem;
            font-weight: 600;
            color: var(--body-text-color, #1a1a2e);
        }
        .advanced-mode-switch-btn {
            border: 2px solid #e2dff0 !important;
            border-radius: 8px !important;
            font-size: 0.8rem !important;
            font-weight: 500 !important;
            color: #667eea !important;
            background: #ffffff !important;
            padding: 0.25rem 0.75rem !important;
            transition: all 0.15s ease !important;
            white-space: nowrap !important;
        }
        .advanced-mode-switch-btn:hover {
            border-color: #667eea !important;
            background: #f8f7ff !important;
        }

        /* ── End Simple UI ── */

        /* High-res info icon using SVG, appended to the label text */
        .has-info-container span[data-testid="block-info"]::after,
        .checkbox-container:has(+ div) .label-text::after {
            content: "";
            display: inline-block;
            width: 14px;
            height: 14px;
            margin-left: 8px;
            vertical-align: middle;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%234a9eff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Cline x1='12' y1='16' x2='12' y2='12'/%3E%3Cline x1='12' y1='8' x2='12.01' y2='8'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-size: contain;
            opacity: 0.6;
            transition: opacity 0.2s, transform 0.2s;
            cursor: help;
        }

        /* Hide original Gradio info icon if present */
        .has-info-container span[data-testid="block-info"] svg,
        .has-info-container span[data-testid="block-info"]::before {
            display: none !important;
        }

        .has-info-container span[data-testid="block-info"]:hover::after,
        .checkbox-container:hover .label-text::after {
            opacity: 1;
            transform: scale(1.15);
        }

        /* Cap tooltip height, allow scrolling, and enable pointer events so users
           can hover over and scroll long tooltips without them collapsing */
        .has-info-container span[data-testid="block-info"]:hover + div,
        .has-info-container span[data-testid="block-info"]:hover + span,
        .has-info-container span[data-testid="block-info"] + div:hover,
        .has-info-container span[data-testid="block-info"] + span:hover,
        .checkbox-container:hover + div,
        .checkbox-container + div:hover {
            max-height: 40vh;
            overflow-y: auto;
            pointer-events: auto;
        }

        /* Flip tooltip above when near the bottom of the viewport */
        .has-info-container.tooltip-flip span[data-testid="block-info"] + div,
        .has-info-container.tooltip-flip span[data-testid="block-info"] + span {
            bottom: 100%;
            top: auto;
            margin-top: 0;
            margin-bottom: 6px;
        }

        /* --- Auto-toggle checkbox row --- */
        /* Compact row of Auto checkboxes that mirrors the field row above */
        .auto-toggles-row {
            margin-top: -8px !important;
            margin-bottom: 0 !important;
            padding: 0 !important;
            gap: 16px !important;
            min-height: 0 !important;
        }
        .auto-toggle {
            text-align: center !important;
        }
        .auto-toggle label {
            font-size: 0.8rem !important;
            gap: 4px !important;
            white-space: nowrap !important;
            cursor: pointer !important;
            opacity: 0.5;
            transition: opacity 0.15s;
            justify-content: center !important;
        }
        .auto-toggle:hover label {
            opacity: 1;
        }
        .auto-toggle input[type="checkbox"] {
            width: 13px !important;
            height: 13px !important;
        }
        """ + HELP_MODAL_CSS,
    ) as demo:
        
        # Hidden help button — triggered programmatically from the hamburger menu
        with gr.Column(visible=True, elem_classes="simple-help-container"):
            create_help_button("getting_started")
        
        # Dataset Explorer Section (hidden)
        dataset_section = create_dataset_section(dataset_handler)
        
        # ═══════════════════════════════════════════
        # Simple UI Column (visible when "Simple" selected)
        # ═══════════════════════════════════════════
        simple_section = build_simple_ui()
        
        # Mode state shared between Simple and Advanced toggle buttons
        simple_mode_state = gr.State(value="Simple")

        # ═══════════════════════════════════════════
        # Advanced UI Column (visible when "Advanced" selected)
        # ═══════════════════════════════════════════
        with gr.Column(visible=False) as advanced_column:
            # Compact mode toggle at the top of the Advanced column
            with gr.Row(elem_classes="advanced-mode-row"):
                gr.HTML(
                    '<span class="advanced-mode-label">' + t("app.title") + '</span>'
                )
                advanced_mode_switch = gr.Button(
                    "☰ Simple",
                    size="sm",
                    elem_classes=["advanced-mode-switch-btn"],
                )
            settings_section = create_advanced_settings_section(
                dit_handler, llm_handler, init_params=init_params, language=language
            )

            # Generation results section (shared between both modes)
            results_section = create_results_section(dit_handler)

            # Tabs: Generation | Training
            with gr.Tabs():
                # --- Generation Tab ---
                with gr.Tab(t("generation.tab_title")):
                    gen_section = create_generation_tab_section(
                        dit_handler, llm_handler, init_params=init_params, language=language
                    )
                    # Results Section (inside the Generation tab, wrapped for visibility control)
                    with gr.Column(visible=True) as results_wrapper:
                        gen_section["results_wrapper"] = results_wrapper

                # --- Training Tab ---
                with gr.Tab(t("training.tab_title"), visible=not service_mode):
                    training_section = create_training_section(
                        dit_handler, llm_handler, init_params=init_params
                    )

        # ═══════════════════════════════════════════
        # Merge all generation-related component dicts for event wiring
        # ═══════════════════════════════════════════
        generation_section = {}
        generation_section.update(settings_section)
        generation_section.update(gen_section)

        # Wire compact mode switch (Advanced → Simple)
        from acestep.ui.gradio.events.wiring.simple_ui_wiring import (
            _init_llm_for_simple_ui,
        )

        advanced_mode_switch.click(
            fn=lambda: (
                gr.update(visible=True),        # simple column shown
                gr.update(visible=False),       # advanced column hidden
                "Simple",                        # state = Simple
            ),
            inputs=[],
            outputs=[simple_section["simple_column"], advanced_column, simple_mode_state],
        ).then(
            fn=lambda: _init_llm_for_simple_ui(llm_handler, dit_handler),
            inputs=[],
            outputs=[],
        )

        demo.load(
            fn=lambda: _init_llm_for_simple_ui(llm_handler, dit_handler),
            inputs=[],
            outputs=[],
            show_progress="hidden",
        )

        # Connect event handlers
        setup_event_handlers(
            demo, dit_handler, llm_handler, dataset_handler,
            dataset_section, generation_section, results_section
        )

        # Connect simple UI event handlers
        setup_simple_ui_handlers(
            demo, dit_handler, llm_handler,
            simple_section, results_section,
            advanced_column=advanced_column,
            simple_mode_state=simple_mode_state,
        )

        # Connect training event handlers
        setup_training_event_handlers(demo, dit_handler, llm_handler, training_section)

        # Restore user preferences from browser localStorage on page load.
        wire_preference_restore(demo, generation_section, service_mode=service_mode)

    demo.queue()
    return demo
