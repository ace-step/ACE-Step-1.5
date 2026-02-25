"""
Gradio UI Components Module
Contains all Gradio interface component definitions and layouts
"""
from pathlib import Path
import gradio as gr
from acestep.ui.gradio.interfaces.theme import AceStepTheme
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

    theme = AceStepTheme()

    main_css_file = Path(__file__).parent / "css" / "main.css"
    main_css = main_css_file.read_text()

    utils_css_file = Path(__file__).parent / "css" / "utils.css"
    utils_css = utils_css_file.read_text()

    with gr.Blocks(
        title=t("app.title"),
        theme=theme,
        css = utils_css + main_css + HELP_MODAL_CSS,
    ) as demo:

        with gr.Row(equal_height=True, elem_classes=["main-header-container"]):
            create_help_button("getting_started")
            gr.HTML(f"""
            <div class="main-header">
                <h1>{t("app.title")}</h1>
                <p>{t("app.subtitle")}</p>
            </div>
            """, elem_classes=["no-grow"])

        # Dataset Explorer Section (hidden)
        dataset_section = create_dataset_section(dataset_handler)

        with gr.Row(elem_classes=["gap-6"]):
            with gr.Column(scale=1):
                # ═══════════════════════════════════════════
                # Sidebar: Settings (contains Service Config + Advanced Settings)
                # ═══════════════════════════════════════════
                settings_section = create_advanced_settings_section(
                    dit_handler, llm_handler, init_params=init_params, language=language
                )
            with gr.Column(scale=9):
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
