"""Retake + Edit (flow-edit overlay) controls (#1155, #1156).

Two columns inside one ``gr.Accordion`` so each subsystem's panel sits
directly under its own checkbox.  Both available in Custom / Remix /
Repaint modes; outer accordion visibility is controlled by ``mode_ui``.
The ``Copy from current`` button click handler is wired in
``generation_run_wiring.py`` (kept out of this builder so the captions /
lyrics components only exist in the wiring scope).
"""

from typing import Any

import gradio as gr

from acestep.ui.gradio.help_content import create_help_button


def build_variation_morph_controls() -> dict[str, Any]:
    """Build the Retake + Edit accordion.

    Layout (collapsed by default)::

      > Retake & Edit
          | [ ] Retake (?)                | [ ] Edit (?)                      |
          |   variance ── seed ──         |   [Copy from current]             |
          |                               |   source caption ──               |
          |                               |   source lyrics  ──               |
          |                               |   n_min  n_max  n_avg             |

    Each checkbox toggles the visibility of the panel directly below it,
    so the two columns can be expanded independently.  The (?) buttons
    open modal tutorials for each subsystem.
    """

    with gr.Accordion("Retake & Edit", open=False) as variation_accordion:
        with gr.Row(equal_height=False):
            # ---- LEFT column: Retake ----
            with gr.Column(scale=1, min_width=200):
                with gr.Row():
                    retake_enabled = gr.Checkbox(
                        label="Retake", value=False, scale=8,
                        info="Mix in extra noise for controllable variation.",
                    )
                    create_help_button("generation_retake")
                with gr.Group(visible=False) as retake_panel:
                    with gr.Row():
                        retake_variance = gr.Slider(
                            minimum=0.0, maximum=1.0, step=0.01, value=0.0,
                            label="variance", scale=2,
                            info="0=baseline; 0.05–0.15 subtle; 0.5+ strong.",
                        )
                        retake_seed = gr.Textbox(
                            label="seed", value="", scale=1,
                            placeholder="empty=random",
                        )
            # ---- RIGHT column: Edit ----
            with gr.Column(scale=1, min_width=200):
                with gr.Row():
                    flow_edit_morph = gr.Checkbox(
                        label="Edit", value=False, scale=8,
                        info="Morph the source toward a new prompt via V_delta integration.",
                    )
                    create_help_button("generation_edit")
                with gr.Group(visible=False) as morph_panel:
                    with gr.Row():
                        flow_edit_copy_from_current_btn = gr.Button(
                            "Copy current → source",
                            size="sm", scale=0, min_width=180,
                        )
                    with gr.Row(equal_height=False):
                        flow_edit_source_caption = gr.Textbox(
                            label="source caption",
                            placeholder="Describe the ORIGINAL audio.",
                            lines=4, max_lines=8, scale=1,
                        )
                        flow_edit_source_lyrics = gr.Textbox(
                            label="source lyrics",
                            placeholder="Original lyrics; top-level lyrics is the target.",
                            lines=4, max_lines=8, scale=1,
                        )
                    with gr.Row():
                        flow_edit_n_min = gr.Slider(
                            minimum=0.0, maximum=1.0, value=0.0, step=0.05,
                            label="n_min",
                        )
                        flow_edit_n_max = gr.Slider(
                            minimum=0.0, maximum=1.0, value=1.0, step=0.05,
                            label="n_max",
                        )
                        flow_edit_n_avg = gr.Slider(
                            minimum=1, maximum=8, value=1, step=1,
                            label="n_avg",
                        )
        # Visibility chains.
        retake_enabled.change(
            lambda v: gr.update(visible=bool(v)),
            inputs=[retake_enabled], outputs=[retake_panel],
        )
        flow_edit_morph.change(
            lambda v: gr.update(visible=bool(v)),
            inputs=[flow_edit_morph], outputs=[morph_panel],
        )
    return {
        "variation_accordion": variation_accordion,
        "retake_enabled": retake_enabled,
        "retake_panel": retake_panel,
        "retake_variance": retake_variance,
        "retake_seed": retake_seed,
        "flow_edit_morph": flow_edit_morph,
        "morph_panel": morph_panel,
        "flow_edit_copy_from_current_btn": flow_edit_copy_from_current_btn,
        "flow_edit_source_caption": flow_edit_source_caption,
        "flow_edit_source_lyrics": flow_edit_source_lyrics,
        "flow_edit_n_min": flow_edit_n_min,
        "flow_edit_n_max": flow_edit_n_max,
        "flow_edit_n_avg": flow_edit_n_avg,
    }
