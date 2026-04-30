"""Variation + Smooth-Morph controls (Retake #1155 + Flow-edit #1156).

Combined into a single ``gr.Accordion`` so both knobs share screen real
estate and are discoverable in the same place.  Both are available in
``Custom`` / ``Remix`` / ``Repaint`` modes; the outer accordion's
visibility is controlled by ``mode_ui``.
"""

from typing import Any

import gradio as gr


_RETAKE_INFO = (
    "Retake mixes a fresh independent noise draw into the seeded initial "
    "noise (variance-preserving sin/cos blend).  variance=0 is a no-op; "
    "0.05–0.15 = subtle variation; 0.5+ = strong drift.  retake_seed is "
    "an independent reproducibility seed, recorded in metadata when "
    "variance > 0."
)

_MORPH_INFO = (
    "Smooth morph layers V_delta = V_tar − V_src integration on top of "
    "text2music dispatch.  Upload a source audio + describe it in "
    "‘source caption / lyrics’; the top-level caption / lyrics become "
    "the target.  Recommended: shift=3.0, n_min=0, n_max=1, n_avg=1.  "
    "v1: backend honours morph only in <b>Custom</b> mode; selecting "
    "morph in Remix / Repaint is ignored (paired-CFG for those task "
    "shapes is the follow-up PR)."
)


def build_variation_morph_controls() -> dict[str, Any]:
    """Create the combined Variation/Morph accordion.

    Layout (collapsed by default):

      > Variation & Smooth Morph
          [Retake]  [Smooth morph]
          --- retake panel (visible when Retake checked) ---
          [variance ────] [seed ────────]
          --- morph panel (visible when Smooth morph checked) ---
          [source caption ────────]
          [source lyrics  ────────]
          [n_min] [n_max] [n_avg]
    """

    with gr.Accordion("Variation & Smooth Morph", open=False) as variation_accordion:
        with gr.Row():
            retake_enabled = gr.Checkbox(
                label="Retake (variation)",
                value=False,
                info="Mix in extra noise for controllable variation.",
                scale=1,
            )
            flow_edit_morph = gr.Checkbox(
                label="Smooth morph (flow-edit)",
                value=False,
                info="Morph the source toward a new prompt via V_delta integration.",
                scale=1,
            )
        # --- Retake panel ---
        with gr.Group(visible=False) as retake_panel:
            with gr.Row():
                retake_variance = gr.Slider(
                    minimum=0.0, maximum=1.0, step=0.01, value=0.0,
                    label="Retake variance",
                    info="0=baseline; 0.05–0.15 subtle; 0.5+ strong.",
                    scale=2,
                )
                retake_seed = gr.Textbox(
                    label="Retake seed",
                    value="",
                    placeholder="empty=random; integer=reproduce",
                    info="Independent seed; recorded in metadata when variance>0.",
                    scale=1,
                )
            gr.Markdown(f"<small style='opacity:0.7;'>{_RETAKE_INFO}</small>")
        # --- Morph panel ---
        with gr.Group(visible=False) as morph_panel:
            flow_edit_source_caption = gr.Textbox(
                label="Source caption (V_src condition)",
                placeholder="Describe the ORIGINAL audio.",
                lines=1, max_lines=3,
            )
            flow_edit_source_lyrics = gr.Textbox(
                label="Source lyrics (V_src condition)",
                placeholder="Original lyrics. Top-level lyrics field is the target.",
                lines=2, max_lines=6,
            )
            with gr.Row():
                flow_edit_n_min = gr.Slider(
                    minimum=0.0, maximum=1.0, value=0.0, step=0.05,
                    label="n_min", info="Edit window start (0=schedule start).",
                )
                flow_edit_n_max = gr.Slider(
                    minimum=0.0, maximum=1.0, value=1.0, step=0.05,
                    label="n_max", info="Edit window end (1=schedule end).",
                )
                flow_edit_n_avg = gr.Slider(
                    minimum=1, maximum=8, value=1, step=1,
                    label="n_avg", info="MC samples / step (higher = stabler, slower).",
                )
            gr.Markdown(f"<small style='opacity:0.7;'>{_MORPH_INFO}</small>")
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
