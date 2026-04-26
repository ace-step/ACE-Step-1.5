"""Frontend user-preference persistence helpers for the Gradio UI.

Save side:  A ``<script>`` injected via ``Blocks(head=…)`` listens for DOM
changes and writes the current preference values to ``localStorage``.

Restore side:  ``wire_preference_restore`` attaches a ``demo.load()`` handler
whose *js* parameter reads ``localStorage`` on page load and feeds the saved
values straight into the Gradio component outputs.  Because Gradio itself
applies the updates through its own Svelte reactivity, every component type
(dropdown, slider, checkbox, number) is updated correctly—no fragile DOM
hacking required.
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Any


_ASSET_FILENAME = "user_preferences.js"
_STORAGE_KEY = "acestep.ui.user_preferences"
_SCHEMA_VERSION = 1

# Ordered list of preference keys.  The order here MUST match the order of
# *outputs* passed to ``demo.load()`` in ``wire_preference_restore``.
PREF_KEYS: list[str] = [
    "audio_format",
    "mp3_bitrate",
    "mp3_sample_rate",
    "score_scale",
    "enable_normalization",
    "normalization_db",
    "fade_in_duration",
    "fade_out_duration",
    "latent_shift",
    "latent_rescale",
    "lm_batch_chunk_size",
]

# Default values used when localStorage is empty or the schema version has
# changed.  Keys must match ``PREF_KEYS``.
_DEFAULTS: dict[str, Any] = {
    "audio_format": "mp3",
    "mp3_bitrate": "128k",
    "mp3_sample_rate": 48000,
    "score_scale": 0.5,
    "enable_normalization": True,
    "normalization_db": -1.0,
    "fade_in_duration": 0.0,
    "fade_out_duration": 0.0,
    "latent_shift": 0.0,
    "latent_rescale": 1.0,
    "lm_batch_chunk_size": 8,
}


# ── Save-side: head script injection ────────────────────────────────────


def _load_preferences_script() -> str:
    """Load the external save-preferences JavaScript asset."""
    asset_path = Path(__file__).with_name(_ASSET_FILENAME)
    return asset_path.read_text(encoding="utf-8").strip()


def get_user_preferences_head() -> str:
    """Return Gradio head HTML that injects save-side preference persistence."""
    script_source = _load_preferences_script()
    return f"<script>\n{script_source}\n</script>"


# ── Restore-side: Gradio .load() wiring ─────────────────────────────────


def _build_restore_js(num_outputs: int) -> str:
    """Build the client-side JS that reads localStorage and returns values.

    The returned function is passed as the ``js`` parameter to
    ``demo.load()``.  It returns an array whose element order matches
    ``PREF_KEYS`` (and therefore the *outputs* list).

    When localStorage has no saved preferences (first visit, cleared
    storage, private browsing), the function returns an array of ``null``
    sentinels so the Python side can skip the update and preserve whatever
    values were already rendered from ``init_params``.

    Args:
        num_outputs: Total number of output components (preference keys
            plus any extra outputs like ``mp3_controls_row``).
    """
    keys_json = json.dumps(PREF_KEYS)
    # Build a type map so the restore JS can validate each value.
    type_map: dict[str, str] = {}
    for k in PREF_KEYS:
        v = _DEFAULTS[k]
        if isinstance(v, bool):
            type_map[k] = "boolean"
        elif isinstance(v, (int, float)):
            type_map[k] = "number"
        else:
            type_map[k] = "string"
    type_map_json = json.dumps(type_map, ensure_ascii=False)
    # Keys whose Gradio Dropdown choices are integers stored as strings in
    # localStorage.  Only actual dropdown keys with numeric defaults need
    # coercion; sliders/numbers are already stored as numbers.
    numeric_dropdown_keys_json = json.dumps(["mp3_sample_rate"])
    # Sentinel array returned when there is nothing to restore.  Using null
    # lets the Python fn detect "no stored prefs" and return gr.update()
    # for every output, preserving the values already rendered on the page.
    skip_sentinel = f"new Array({num_outputs}).fill(null)"
    return f"""() => {{
        const STORAGE_KEY = {json.dumps(_STORAGE_KEY)};
        const SCHEMA_VERSION = {_SCHEMA_VERSION};
        const KEYS = {keys_json};
        const TYPE_MAP = {type_map_json};
        const NUMERIC_COERCE_KEYS = new Set({numeric_dropdown_keys_json});
        const SKIP = {skip_sentinel};
        try {{
            const raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) return SKIP;
            const prefs = JSON.parse(raw);
            // Only reset on downgrade; forward-compatible additions of new
            // keys are handled by skipping (preserving init_params).
            if (typeof prefs._version === "number" && prefs._version > SCHEMA_VERSION) {{
                return SKIP;
            }}
            const result = KEYS.map(k => {{
                if (!(k in prefs)) return null;
                let v = prefs[k];
                // Type-check: fall back to null (skip) if the stored type
                // does not match what the Gradio component expects.
                const expected = TYPE_MAP[k];
                if (expected && typeof v !== expected) {{
                    // Allow stringified numbers for dropdown coercion below.
                    if (!(NUMERIC_COERCE_KEYS.has(k) && typeof v === "string")) {{
                        return null;
                    }}
                }}
                // Coerce stringified numbers back for Dropdown choices that
                // expect integers (e.g. mp3_sample_rate: 48000 not "48000").
                if (NUMERIC_COERCE_KEYS.has(k) && typeof v === "string") {{
                    const n = Number(v);
                    if (Number.isFinite(n)) v = n;
                    else return null;
                }}
                return v;
            }});
            // If none of the keys had stored values, skip entirely.
            if (result.every(v => v === null)) return SKIP;
            // Compute mp3 control visibility from audio_format (index 0).
            // Push 3 extra values: mp3_controls_row, mp3_bitrate, mp3_sample_rate
            // matching the outputs of _update_mp3_control_visibility().
            // When audioFormat is null (no stored value), push nulls so Python
            // emits gr.update() and preserves whatever init_params set.
            const audioFormat = result[0];
            const mp3 = audioFormat === null ? null : audioFormat === "mp3";
            result.push(mp3, mp3, mp3);
            return result;
        }} catch (_e) {{
            return SKIP;
        }}
    }}"""


def restore_preferences(
    *values: Any, _num_outputs: int = 0
) -> tuple[Any, ...]:
    """Map JS restore results into Gradio output values.

    The JS function reads localStorage and produces an array:
      - First ``len(PREF_KEYS)`` elements are preference values (or null).
      - Next 3 elements are mp3 visibility booleans (or null):
        [mp3_controls_row, mp3_bitrate, mp3_sample_rate].

    ``None`` (JSON ``null``) → ``gr.update()`` (no-op, preserves current).
    Booleans beyond PREF_KEYS → visibility/interactivity updates matching
    ``_update_mp3_control_visibility()`` from the output controls module.

    When the JS side returns no values (e.g. certain Gradio versions do not
    forward the JS return value to the Python ``fn`` when ``inputs=None``),
    ``_num_outputs`` is used to produce the correct number of no-op updates
    so Gradio does not raise a ``ValueError`` about mismatched output count.
    """
    import gradio as gr

    if not values:
        return tuple(gr.update() for _ in range(_num_outputs))

    n_prefs = len(PREF_KEYS)
    results: list[Any] = []
    for i, v in enumerate(values):
        if v is None:
            results.append(gr.update())
        elif i == n_prefs and isinstance(v, bool):
            # mp3_controls_row: visibility only.
            results.append(gr.update(visible=v))
        elif i > n_prefs and isinstance(v, bool):
            # mp3_bitrate, mp3_sample_rate: visibility + interactivity.
            results.append(gr.update(visible=v, interactive=v))
        else:
            results.append(v)
    return tuple(results)


def wire_preference_restore(
    demo: Any,
    generation_section: dict[str, Any],
    *,
    service_mode: bool = False,
) -> None:
    """Attach a ``demo.load()`` handler that restores saved preferences.

    Must be called **inside** the ``with gr.Blocks() as demo:`` context,
    after all generation components have been created.

    In service mode the function is a no-op: service-mode sessions use
    server-side ``init_params`` and controls are locked
    (``interactive=False``), so localStorage values must not override them.

    Args:
        demo: The ``gr.Blocks`` instance.
        generation_section: Merged component dict that includes the output
            control components (``audio_format``, ``mp3_bitrate``, etc.).
        service_mode: When ``True``, skip wiring entirely so that
            localStorage cannot override server-configured values.
    """
    if service_mode:
        return

    outputs = []
    for key in PREF_KEYS:
        component = generation_section.get(key)
        if component is None:
            raise KeyError(
                f"wire_preference_restore: missing component {key!r} in "
                f"generation_section (available: {sorted(generation_section)})"
            )
        outputs.append(component)

    # Also update mp3 control visibility so it stays in sync when the
    # restored audio_format differs from the server-rendered default.
    # Gradio does not fire .change() for load-time value assignments, so
    # without this the MP3 row and its children could be visible/hidden
    # incorrectly.  The three extra outputs mirror the return of
    # _update_mp3_control_visibility(): [row, bitrate, sample_rate].
    for mp3_key in ("mp3_controls_row", "mp3_bitrate", "mp3_sample_rate"):
        comp = generation_section.get(mp3_key)
        if comp is not None:
            outputs.append(comp)

    demo.load(
        fn=partial(restore_preferences, _num_outputs=len(outputs)),
        inputs=None,
        outputs=outputs,
        js=_build_restore_js(num_outputs=len(outputs)),
    )
