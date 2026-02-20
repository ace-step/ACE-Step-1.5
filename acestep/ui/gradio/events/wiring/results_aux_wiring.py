"""Results auxiliary event wiring helpers.

This module contains results-side helper button wiring that is separate from
core generation and batch navigation orchestration.
"""

from typing import Any, Sequence

from .. import results_handlers as res_h
from .context import GenerationWiringContext


def register_results_aux_handlers(
    context: GenerationWiringContext,
    mode_ui_outputs: Sequence[Any],
) -> None:
    """Register remix/repaint, scoring, LRC, and codes helper handlers."""

    generation_section = context.generation_section
    results_section = context.results_section
    dit_handler = context.dit_handler
    llm_handler = context.llm_handler

    # ========== Send to Remix / Repaint Handlers ==========
    # Mode-UI outputs shared with generation_mode.change â€” applied atomically
    # so we don't rely on a chained .change() event for visibility/label updates.
    for btn_idx in range(1, 9):
        results_section[f"send_to_remix_btn_{btn_idx}"].click(
            fn=lambda audio, lm, ly, cap, cur_mode: res_h.send_audio_to_remix(
                audio, lm, ly, cap, cur_mode, llm_handler
            ),
            inputs=[
                results_section[f"generated_audio_{btn_idx}"],
                results_section["lm_metadata_state"],
                generation_section["lyrics"],
                generation_section["captions"],
                generation_section["generation_mode"],
            ],
            outputs=[
                generation_section["src_audio"],
                generation_section["generation_mode"],
                generation_section["lyrics"],
                generation_section["captions"],
            ]
            + list(mode_ui_outputs),
        )
        results_section[f"send_to_repaint_btn_{btn_idx}"].click(
            fn=lambda audio, lm, ly, cap, cur_mode: res_h.send_audio_to_repaint(
                audio, lm, ly, cap, cur_mode, llm_handler
            ),
            inputs=[
                results_section[f"generated_audio_{btn_idx}"],
                results_section["lm_metadata_state"],
                generation_section["lyrics"],
                generation_section["captions"],
                generation_section["generation_mode"],
            ],
            outputs=[
                generation_section["src_audio"],
                generation_section["generation_mode"],
                generation_section["lyrics"],
                generation_section["captions"],
            ]
            + list(mode_ui_outputs),
        )

    # ========== Score Calculation Handlers ==========
    # Use default argument to capture btn_idx value at definition time.
    def make_score_handler(idx: int):
        """Build a score-click callback bound to a fixed result slot index."""

        return lambda scale, batch_idx, queue: res_h.calculate_score_handler_with_selection(
            dit_handler, llm_handler, idx, scale, batch_idx, queue
        )

    for btn_idx in range(1, 9):
        results_section[f"score_btn_{btn_idx}"].click(
            fn=make_score_handler(btn_idx),
            inputs=[
                generation_section["score_scale"],
                results_section["current_batch_index"],
                results_section["batch_queue"],
            ],
            outputs=[
                results_section[f"score_display_{btn_idx}"],
                results_section[f"details_accordion_{btn_idx}"],
                results_section["batch_queue"],
            ],
        )

    # ========== LRC Timestamp Handlers ==========
    # Use default argument to capture btn_idx value at definition time.
    def make_lrc_handler(idx: int):
        """Build an LRC-generation callback bound to a fixed result slot index."""

        return lambda batch_idx, queue, vocal_lang, infer_steps: res_h.generate_lrc_handler(
            dit_handler, idx, batch_idx, queue, vocal_lang, infer_steps
        )

    for btn_idx in range(1, 9):
        results_section[f"lrc_btn_{btn_idx}"].click(
            fn=make_lrc_handler(btn_idx),
            inputs=[
                results_section["current_batch_index"],
                results_section["batch_queue"],
                generation_section["vocal_language"],
                generation_section["inference_steps"],
            ],
            outputs=[
                results_section[f"lrc_display_{btn_idx}"],
                results_section[f"details_accordion_{btn_idx}"],
                results_section["batch_queue"],
            ],
        )

    # ========== Convert To Codes Handlers ==========
    for btn_idx in range(1, 9):
        results_section[f"convert_to_codes_btn_{btn_idx}"].click(
            fn=lambda audio: res_h.convert_result_audio_to_codes(dit_handler, audio),
            inputs=[results_section[f"generated_audio_{btn_idx}"]],
            outputs=[
                results_section[f"codes_display_{btn_idx}"],
                results_section[f"details_accordion_{btn_idx}"],
            ],
        )

    # ========== Save LRC Handlers ==========
    for btn_idx in range(1, 9):
        results_section[f"save_lrc_btn_{btn_idx}"].click(
            fn=res_h.save_lrc_to_file,
            inputs=[results_section[f"lrc_display_{btn_idx}"]],
            outputs=[results_section[f"lrc_download_file_{btn_idx}"]],
        )
