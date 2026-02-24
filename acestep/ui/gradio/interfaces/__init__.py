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
from acestep.ui.gradio.interfaces.result import create_results_section
from acestep.ui.gradio.interfaces.training import create_training_section
from acestep.ui.gradio.events import setup_event_handlers, setup_training_event_handlers
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
    # Initialize i18n with selected language
    i18n = get_i18n(language)
    
    # Check if running in service mode (hide training tab)
    service_mode = init_params is not None and init_params.get('service_mode', False)
    
    with gr.Blocks(
        title=t("app.title"),
        theme=gr.themes.Soft(),
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
           In Gradio 6, info is often a div following the span[data-testid="block-info"]. */
        .has-info-container span[data-testid="block-info"] + div,
        .has-info-container span[data-testid="block-info"] + span,
        .checkbox-container + div {
            display: none;
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

        /* Show tooltips on hover of the label area or the icon */
        .has-info-container span[data-testid="block-info"]:hover + div,
        .has-info-container span[data-testid="block-info"]:hover + span,
        .checkbox-container:hover + div {
            display: block !important;
        }

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
        
        gr.HTML(f"""
        <div class="main-header">
            <h1>{t("app.title")}</h1>
            <p>{t("app.subtitle")}</p>
        </div>
        """)
        create_help_button("getting_started")
        
        # Dataset Explorer Section (hidden)
        dataset_section = create_dataset_section(dataset_handler)
        
        # ═══════════════════════════════════════════
        # Top-level: Settings (contains Service Config + Advanced Settings)
        # ═══════════════════════════════════════════
        settings_section = create_advanced_settings_section(
            dit_handler, llm_handler, init_params=init_params, language=language
        )
        
        # ═══════════════════════════════════════════
        # Tabs: Generation | Training
        # ═══════════════════════════════════════════
        with gr.Tabs():
            # --- Generation Tab ---
            with gr.Tab(t("generation.tab_title")):
                gen_section = create_generation_tab_section(
                    dit_handler, llm_handler, init_params=init_params, language=language
                )
                
                # Results Section (inside the Generation tab, wrapped for visibility control)
                with gr.Column(visible=True) as results_wrapper:
                    results_section = create_results_section(dit_handler)
                # Store the wrapper in gen_section so event handlers can toggle it
                gen_section["results_wrapper"] = results_wrapper
            
            # --- Training Tab ---
            with gr.Tab(t("training.tab_title"), visible=not service_mode):
                training_section = create_training_section(
                    dit_handler, llm_handler, init_params=init_params
                )
        
        # ═══════════════════════════════════════════
        # Merge all generation-related component dicts for event wiring
        # ═══════════════════════════════════════════
        # The event handlers expect a single "generation_section" dict with all
        # components from settings (service config + advanced) and generation tab.
        generation_section = {}
        generation_section.update(settings_section)
        generation_section.update(gen_section)
        
        # Connect event handlers
        setup_event_handlers(
            demo, dit_handler, llm_handler, dataset_handler,
            dataset_section, generation_section, results_section
        )
        
        # Connect training event handlers
        setup_training_event_handlers(demo, dit_handler, llm_handler, training_section)
    
    return demo
