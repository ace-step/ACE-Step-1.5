"""Retake + Edit (flow-edit overlay) controls (#1155, #1156).

Two columns inside one ``gr.Accordion`` so each subsystem's panel sits
directly under its own checkbox.  Both available in Custom / Remix /
Repaint modes; outer accordion visibility is controlled by ``mode_ui``.
"""

from typing import Any

import gradio as gr


def build_variation_morph_controls() -> dict[str, Any]:
    """Build the Retake + Edit accordion (two side-by-side panels).

    Layout (collapsed by default)::

      > Retake & Edit
          | [ ] Retake                     | [ ] Edit                          |
          |   variance ── seed ──          |   source caption ──               |
          |                                |   source lyrics  ──               |
          |                                |   n_min  n_max  n_avg             |

    Each checkbox toggles the visibility of the panel directly below it,
    so the two columns can be expanded independently.
    """

    with gr.Accordion("Retake & Edit", open=False) as variation_accordion:
        with gr.Row(equal_height=False):
            # ---- LEFT column: Retake ----
            with gr.Column(scale=1, min_width=200):
                retake_enabled = gr.Checkbox(
                    label="Retake",
                    value=False,
                    info="Mix in extra noise for controllable variation.",
                )
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
                flow_edit_morph = gr.Checkbox(
                    label="Edit",
                    value=False,
                    info="Morph the source toward a new prompt via V_delta integration.",
                )
                with gr.Group(visible=False) as morph_panel:
                    flow_edit_source_caption = gr.Textbox(
                        label="source caption",
                        placeholder="Describe the ORIGINAL audio.",
                        lines=1, max_lines=2,
                    )
                    flow_edit_source_lyrics = gr.Textbox(
                        label="source lyrics",
                        placeholder="Original lyrics; top-level lyrics is the target.",
                        lines=2, max_lines=4,
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
                    gr.HTML(
                        "<small style='opacity:0.65; line-height:1.3;'>"
                        "v1 backend honours Edit only in <b>Custom</b> mode "
                        "(Remix / Repaint will be ignored). Recommended: "
                        "shift=3.0, n_min=0, n_max=1, n_avg=1."
                        "</small>"
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
        "flow_edit_source_caption": flow_edit_source_caption,
        "flow_edit_source_lyrics": flow_edit_source_lyrics,
        "flow_edit_n_min": flow_edit_n_min,
        "flow_edit_n_max": flow_edit_n_max,
        "flow_edit_n_avg": flow_edit_n_avg,
    }
