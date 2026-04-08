"""Frontend user-preference persistence helpers for the Gradio UI.

Save side:  A ``<script>`` injected via ``Blocks(head=…)`` listens for DOM
changes and writes the current preference values to ``localStorage``.
It also keeps MP3-specific control visibility in sync with the selected
audio format via direct DOM toggling (``syncMp3Row()``), since Gradio
does not fire ``.change()`` for values set at load time.

Restore side:  ``wire_preference_restore`` attaches a ``demo.load()`` handler
whose *js* parameter reads ``localStorage`` on page load and passes the
saved values as a JSON string through a hidden dummy Textbox input.
The Python side deserialises the string and feeds the values into Gradio
component outputs, where Svelte reactivity applies them correctly.
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


def _build_restore_js() -> str:
    """Build the client-side JS that reads localStorage and returns values.

    The returned function is passed as the ``js`` parameter to
    ``demo.load()``.  It reads saved preferences from localStorage,
    serialises them as a JSON string, and returns a single-element array
    ``[json_string]`` so Gradio maps it to the dummy Textbox input.
    The Python side (``restore_preferences``) deserialises the string
    and produces one output value per ``PREF_KEYS`` entry.

    When localStorage has no saved preferences (first visit, cleared
    storage, private browsing), the function returns ``[null]`` so the
    Python side receives a falsy value and emits ``gr.update()`` for
    every output, preserving whatever was already rendered from
    ``init_params``.

    MP3 control visibility is **not** handled here; it is managed by
    ``syncMp3Row()`` in the save-side JS (``user_preferences.js``),
    which toggles the DOM directly on page load and on format changes.
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
    skip_sentinel = "[null]"
    return f"""(_dummy) => {{
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
            return [JSON.stringify(result)];
        }} catch (_e) {{
            return SKIP;
        }}
    }}"""


def restore_preferences(
    *values: Any, _num_outputs: int = 0
) -> tuple[Any, ...]:
    """Map JS restore results into Gradio output values.

    The JS function serialises a ``PREF_KEYS``-ordered array into a JSON
    string and passes it through a hidden dummy Textbox.  This function
    receives that string as ``values[0]``, deserialises it, and returns
    one Gradio-compatible value per output component.

    Individual elements may be ``null`` (when a key was absent from
    localStorage); these become ``gr.update()`` (no-op, preserves
    the current component value).

    When the JS side returns ``[null]`` (no stored preferences) or
    the function is called with no arguments (edge-case Gradio
    versions), ``_num_outputs`` is used to produce the correct number
    of no-op updates so Gradio does not raise a ``ValueError`` about
    mismatched output count.

    MP3 control visibility is handled on the JS side by
    ``syncMp3Row()``; this function only sets component *values*.
    """
    import gradio as gr

    noop = tuple(gr.update() for _ in range(_num_outputs))

    if not values or not values[0]:
        return noop

    try:
        data = json.loads(values[0])
    except (TypeError, ValueError):
        return noop

    if not isinstance(data, list) or all(v is None for v in data):
        return noop

    n_prefs = len(PREF_KEYS)
    results: list[Any] = []
    for i, v in enumerate(data):
        if i >= n_prefs:
            break
        if v is None:
            results.append(gr.update())
        else:
            results.append(v)

    while len(results) < _num_outputs:
        results.append(gr.update())

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

    import gradio as gr

    outputs = []
    for key in PREF_KEYS:
        component = generation_section.get(key)
        if component is None:
            raise KeyError(
                f"wire_preference_restore: missing component {key!r} in "
                f"generation_section (available: {sorted(generation_section)})"
            )
        outputs.append(component)

    # Dummy input — creates a channel for JS → Python
    dummy = gr.Textbox(value="", visible=False, elem_id="acestep-prefs-restore-dummy")

    demo.load(
        fn=partial(restore_preferences, _num_outputs=len(outputs)),
        inputs=[dummy],
        outputs=outputs,
        js=_build_restore_js(),
    )
