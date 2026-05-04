"""Library tab: browse, preview, rate, and delete generated songs."""

from typing import Any

import gradio as gr

from acestep.ui.gradio.events.library_handlers import (
    delete_song,
    get_library_rows,
    scan_library,
    set_rating,
)

_SORT_CHOICES = [("Newest First", "date"), ("Name A–Z", "name"), ("Top Rated", "rating")]
_FILTER_CHOICES = [
    ("All", 0), ("★+", 1), ("★★+", 2), ("★★★+", 3), ("★★★★+", 4), ("★★★★★", 5)
]
_RATING_CHOICES = [("★", 1), ("★★", 2), ("★★★", 3), ("★★★★", 4), ("★★★★★", 5)]
_TABLE_HEADERS = ["Name", "Date", "Rating"]
_TABLE_TYPES = ["str", "str", "str"]


# ── UI builder ────────────────────────────────────────────────────────────────

def create_library_section() -> dict[str, Any]:
    """Build the Library tab UI and wire all internal events.

    Returns:
        Component map (all keys prefixed with ``lib_``).
    """
    with gr.Column():

        # ── Toolbar ──────────────────────────────────────────────────────────
        with gr.Row():
            lib_refresh_btn = gr.Button("🔄 Refresh", variant="secondary", scale=0, min_width=110)
            lib_sort = gr.Dropdown(
                choices=_SORT_CHOICES, value="date", label="Sort by", scale=1,
            )
            lib_filter = gr.Dropdown(
                choices=_FILTER_CHOICES, value=0, label="Min Rating", scale=1,
            )
            with gr.Column(scale=3):
                lib_count = gr.Markdown("")

        # ── Song table ────────────────────────────────────────────────────────
        lib_table = gr.Dataframe(
            headers=_TABLE_HEADERS,
            datatype=_TABLE_TYPES,
            value=[],
            label="Generated Songs — click any row to preview",
            interactive=False,
            wrap=True,
            column_widths=["60%", "25%", "15%"],
        )

        # State: full list of song dicts returned by scan_library()
        lib_songs_state = gr.State([])

        # ── Selected song panel ───────────────────────────────────────────────
        with gr.Group(visible=False, elem_id="lib-selected-panel") as lib_selected_panel:
            gr.Markdown("---")
            with gr.Row():
                with gr.Column(scale=3):
                    lib_audio = gr.Audio(
                        label="Preview",
                        type="filepath",
                        interactive=False,
                    )
                with gr.Column(scale=2):
                    lib_selected_name = gr.Markdown("")
                    gr.Markdown("**Rating**")
                    lib_rating = gr.Radio(
                        choices=_RATING_CHOICES,
                        value=None,
                        label="",
                        container=False,
                    )
                    with gr.Row():
                        lib_delete_btn = gr.Button("🗑️ Delete", variant="stop", scale=1)
                    lib_status = gr.Markdown("")

            with gr.Accordion("Generation Details", open=True):
                lib_caption = gr.Textbox(label="Caption", interactive=False, lines=3)
                with gr.Row():
                    lib_bpm_field    = gr.Textbox(label="BPM",       interactive=False, scale=1, visible=False)
                    lib_key_field    = gr.Textbox(label="Key",        interactive=False, scale=1)
                    lib_seed_field   = gr.Textbox(label="Seed",       interactive=False, scale=1)
                    lib_dur_field    = gr.Textbox(label="Duration",   interactive=False, scale=1)
                lib_lyrics = gr.Textbox(label="Lyrics", interactive=False, lines=12, max_lines=50)

        # State: path of the currently selected audio file
        lib_selected_path = gr.State(None)

    # ── Internal event wiring ─────────────────────────────────────────────────

    def _do_refresh(sort_by, min_rating):
        songs = scan_library(sort_by=sort_by, min_rating=int(min_rating or 0))
        rows = get_library_rows(songs)
        n = len(songs)
        count_md = f"**{n}** song{'s' if n != 1 else ''} found"
        return rows, songs, count_md

    def _select_song(songs, sort_by, min_rating, evt: gr.SelectData):
        """Populate the selected-song panel when a table row is clicked."""
        # If state is empty (race condition on first load), scan now
        if not songs:
            songs = scan_library(sort_by=sort_by, min_rating=int(min_rating or 0))
        if not songs or evt.index[0] >= len(songs):
            return (
                gr.update(visible=False), None, "", None,
                "", "", "", "", "", "", "", None,
            )
        song = songs[evt.index[0]]
        path = song["path"]
        meta = song["metadata"]

        rating_val = int(song["rating"]) if song["rating"] else None
        name_md = f"### {song['stem']}\n_{song['date_str']}_"

        bpm = song.get("bpm") or "auto"

        key  = meta.get("keyscale") or meta.get("cot_keyscale") or ""

        seed = str(meta.get("seed", "") or "")

        raw_dur = meta.get("duration", -1)
        if raw_dur is None or raw_dur == -1:
            raw_dur = meta.get("cot_duration")
        try:
            secs = int(raw_dur) if (raw_dur and raw_dur != -1) else None
        except (ValueError, TypeError):
            secs = None
        dur = f"{secs // 60}:{secs % 60:02d}" if secs is not None else "auto"
        caption = meta.get("caption", "") or ""
        lyrics  = meta.get("lyrics", "") or ""

        return (
            gr.update(visible=True),  # panel
            path,                      # audio
            name_md,                   # name
            rating_val,                # rating radio
            "",                        # status
            caption,
            bpm,
            key,
            seed,
            dur,
            lyrics,
            path,                      # selected_path state
        )

    def _save_rating(audio_path, rating_val, songs, sort_by, min_rating):
        """Persist rating and refresh the table in place."""
        if audio_path:
            set_rating(audio_path, rating_val)
        songs_refreshed = scan_library(sort_by=sort_by, min_rating=int(min_rating or 0))
        rows = get_library_rows(songs_refreshed)
        n = len(songs_refreshed)
        count_md = f"**{n}** song{'s' if n != 1 else ''} found"
        return rows, songs_refreshed, count_md

    def _delete(audio_path, sort_by, min_rating):
        """Delete the selected song then refresh the table."""
        if not audio_path:
            return (
                gr.update(), gr.update(), "**No song selected.**",
                gr.update(visible=False), None, "", None, "",
                "", "", "", "", "", None,
                None,
            )
        _ok, msg = delete_song(audio_path)
        songs_refreshed = scan_library(sort_by=sort_by, min_rating=int(min_rating or 0))
        rows = get_library_rows(songs_refreshed)
        n = len(songs_refreshed)
        count_md = f"**{n}** song{'s' if n != 1 else ''} found"
        if _ok:
            return (
                rows,
                songs_refreshed,
                count_md,
                gr.update(visible=False),  # hide panel on success
                None,                       # clear audio
                "",                         # clear name
                None,                       # clear rating
                msg,                        # status
                "",                         # caption
                "",                         # bpm
                "",                         # key
                "",                         # seed
                "",                         # dur
                "",                         # lyrics
                None,                       # clear path state
            )
        # On failure: keep panel visible, show error in status, leave fields intact
        return (
            rows,
            songs_refreshed,
            count_md,
            gr.update(visible=True),   # keep panel open
            gr.update(),               # leave audio unchanged
            gr.update(),               # leave name unchanged
            gr.update(),               # leave rating unchanged
            msg,                       # show error in status
            gr.update(),               # leave caption unchanged
            gr.update(),               # leave bpm unchanged
            gr.update(),               # leave key unchanged
            gr.update(),               # leave seed unchanged
            gr.update(),               # leave dur unchanged
            gr.update(),               # leave lyrics unchanged
            audio_path,                # keep path state
        )

    # Refresh / Sort / Filter
    for trigger in [lib_refresh_btn, lib_sort, lib_filter]:
        trigger.click(
            fn=_do_refresh,
            inputs=[lib_sort, lib_filter],
            outputs=[lib_table, lib_songs_state, lib_count],
        ) if trigger is lib_refresh_btn else trigger.change(
            fn=_do_refresh,
            inputs=[lib_sort, lib_filter],
            outputs=[lib_table, lib_songs_state, lib_count],
        )

    # Row select
    lib_table.select(
        fn=_select_song,
        inputs=[lib_songs_state, lib_sort, lib_filter],
        outputs=[
            lib_selected_panel,
            lib_audio,
            lib_selected_name,
            lib_rating,
            lib_status,
            lib_caption,
            lib_bpm_field,
            lib_key_field,
            lib_seed_field,
            lib_dur_field,
            lib_lyrics,
            lib_selected_path,
        ],
    )

    # Rating change → auto-save (use .input so programmatic updates from _select_song don't trigger a spurious re-scan)
    lib_rating.input(
        fn=_save_rating,
        inputs=[lib_selected_path, lib_rating, lib_songs_state, lib_sort, lib_filter],
        outputs=[lib_table, lib_songs_state, lib_count],
    )

    # Delete
    lib_delete_btn.click(
        fn=_delete,
        inputs=[lib_selected_path, lib_sort, lib_filter],
        outputs=[
            lib_table,
            lib_songs_state,
            lib_count,
            lib_selected_panel,
            lib_audio,
            lib_selected_name,
            lib_rating,
            lib_status,
            lib_caption,
            lib_bpm_field,
            lib_key_field,
            lib_seed_field,
            lib_dur_field,
            lib_lyrics,
            lib_selected_path,
        ],
    )

    return {
        "lib_refresh_btn":    lib_refresh_btn,
        "lib_sort":           lib_sort,
        "lib_filter":         lib_filter,
        "lib_count":          lib_count,
        "lib_table":          lib_table,
        "lib_songs_state":    lib_songs_state,
        "lib_selected_panel": lib_selected_panel,
        "lib_audio":          lib_audio,
        "lib_selected_name":  lib_selected_name,
        "lib_rating":         lib_rating,
        "lib_delete_btn":     lib_delete_btn,
        "lib_status":         lib_status,
        "lib_caption":        lib_caption,
        "lib_bpm_field":      lib_bpm_field,
        "lib_key_field":      lib_key_field,
        "lib_seed_field":     lib_seed_field,
        "lib_dur_field":      lib_dur_field,
        "lib_lyrics":         lib_lyrics,
        "lib_selected_path":  lib_selected_path,
    }
