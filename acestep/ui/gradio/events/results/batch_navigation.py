"""Batch navigation: previous / next batch with two-step subtitle yields.

Each navigation function uses a two-step yield pattern to avoid
subtitle flickering:

1. First yield — audio + clear LRC (triggers ``.change()`` to clear subtitles).
2. Sleep 50 ms (let audio load).
3. Second yield — skip audio + set actual LRC (triggers ``.change()`` to set subtitles).
"""
import time as time_module

import gradio as gr

from acestep.ui.gradio.i18n import t
from acestep.ui.gradio.events.results.batch_queue import (
    update_batch_indicator,
    update_navigation_buttons,
)


def navigate_to_previous_batch(current_batch_index, batch_queue):
    """Navigate to the previous batch (result view only).

    Yields:
        Two tuples of 48 Gradio component updates each.
    """
    if current_batch_index <= 0:
        gr.Warning(t("messages.at_first_batch"))
        yield tuple([gr.update()] * 48)
        return

    new_idx = current_batch_index - 1
    if new_idx not in batch_queue:
        gr.Warning(t("messages.batch_not_found", n=new_idx + 1))
        yield tuple([gr.update()] * 48)
        return

    batch_data = batch_queue[new_idx]
    audio_paths = batch_data.get("audio_paths", [])
    generation_info_text = batch_data.get("generation_info", "")

    real_audio_paths = [p for p in audio_paths if not p.lower().endswith('.json')]
    audio_updates = [
        gr.update(value=real_audio_paths[i].replace("\\", "/")) if i < len(real_audio_paths)
        else gr.update(value=None)
        for i in range(8)
    ]

    total_batches = len(batch_queue)
    batch_indicator_text = update_batch_indicator(new_idx, total_batches)
    can_prev, can_next = update_navigation_buttons(new_idx, total_batches)

    stored_scores = batch_data.get("scores", [""] * 8) or [""] * 8
    stored_lrcs = batch_data.get("lrcs", [""] * 8) or [""] * 8

    codes_updates, lrc_updates, lrc_clears, accordion_updates = _build_detail_updates(
        batch_data, stored_lrcs,
    )

    # STEP 1: audio + clear LRC
    yield (
        *audio_updates,
        audio_paths, generation_info_text, new_idx, batch_indicator_text,
        gr.update(interactive=can_prev), gr.update(interactive=can_next),
        t("messages.viewing_batch", n=new_idx + 1),
        *stored_scores, *codes_updates, *lrc_clears, *accordion_updates,
        gr.update(interactive=True),
    )

    time_module.sleep(0.05)

    # STEP 2: skip audio + set actual LRC
    skip8 = [gr.skip()] * 8
    yield (
        *skip8,
        gr.skip(), gr.skip(), gr.skip(), gr.skip(),
        gr.skip(), gr.skip(), gr.skip(),
        *skip8, *skip8, *lrc_updates, *skip8,
        gr.skip(),
    )


def navigate_to_next_batch(autogen_enabled, current_batch_index, total_batches, batch_queue):
    """Navigate to the next batch (result view only).

    Yields:
        Two tuples of 49 Gradio component updates each.
    """
    # Derive actual total from batch_queue so we never rely on a stale
    # total_batches state value (the background generator may have added
    # batches after total_batches was last written to the Gradio state).
    total_batches = max(total_batches, len(batch_queue))

    if current_batch_index >= total_batches - 1:
        gr.Warning(t("messages.at_last_batch"))
        yield tuple([gr.update()] * 49)
        return

    new_idx = current_batch_index + 1
    if new_idx not in batch_queue:
        gr.Warning(t("messages.batch_not_found", n=new_idx + 1))
        yield tuple([gr.update()] * 49)
        return

    batch_data = batch_queue[new_idx]
    audio_paths = batch_data.get("audio_paths", [])
    generation_info_text = batch_data.get("generation_info", "")

    real_audio_paths = [p for p in audio_paths if not p.lower().endswith('.json')]
    audio_updates = [
        gr.update(value=real_audio_paths[i].replace("\\", "/")) if i < len(real_audio_paths)
        else gr.update(value=None)
        for i in range(8)
    ]

    batch_indicator_text = update_batch_indicator(new_idx, total_batches)
    can_prev, can_next = update_navigation_buttons(new_idx, total_batches)

    next_batch_status_text = ""
    if autogen_enabled and new_idx == total_batches - 1:
        next_batch_status_text = "🔄 AutoGen will generate next batch in background..."

    stored_scores = batch_data.get("scores", [""] * 8) or [""] * 8
    stored_lrcs = batch_data.get("lrcs", [""] * 8) or [""] * 8

    codes_updates, lrc_updates, lrc_clears, accordion_updates = _build_detail_updates(
        batch_data, stored_lrcs,
    )

    # STEP 1: audio + clear LRC
    yield (
        *audio_updates,
        audio_paths, generation_info_text, new_idx, batch_indicator_text,
        gr.update(interactive=can_prev), gr.update(interactive=can_next),
        t("messages.viewing_batch", n=new_idx + 1), next_batch_status_text,
        *stored_scores, *codes_updates, *lrc_clears, *accordion_updates,
        gr.update(interactive=True),
    )

    time_module.sleep(0.05)

    # STEP 2: skip audio + set actual LRC
    skip8 = [gr.skip()] * 8
    yield (
        *skip8,
        gr.skip(), gr.skip(), gr.skip(), gr.skip(),
        gr.skip(), gr.skip(),
        gr.skip(), gr.skip(),
        *skip8, *skip8, *lrc_updates, *skip8,
        gr.skip(),
    )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _build_detail_updates(batch_data, lrc_displays):
    """Build codes / LRC / accordion Gradio updates for a batch.

    Returns:
        Tuple of four 8-element lists:
        ``(codes_updates, lrc_updates, lrc_clears, accordion_updates)``.
    """
    stored_codes = batch_data.get("codes", "")
    stored_allow_lm_batch = batch_data.get("allow_lm_batch", False)

    codes_updates = []
    lrc_updates = []
    lrc_clears = []
    accordion_updates = []

    for i in range(8):
        if stored_allow_lm_batch and isinstance(stored_codes, list):
            code_str = stored_codes[i] if i < len(stored_codes) else ""
        else:
            code_str = stored_codes if isinstance(stored_codes, str) and i == 0 else ""

        lrc_str = lrc_displays[i] if i < len(lrc_displays) else ""

        codes_updates.append(gr.update(value=code_str, visible=True))
        lrc_updates.append(gr.update(value=lrc_str, visible=True))
        lrc_clears.append(gr.update(value="", visible=True))
        accordion_updates.append(gr.skip())

    return codes_updates, lrc_updates, lrc_clears, accordion_updates
