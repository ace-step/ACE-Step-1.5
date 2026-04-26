/**
 * User preferences persistence – SAVE side only.
 *
 * Listens for user changes on Gradio UI controls and persists the current
 * values to browser localStorage.  Restoration is handled on the Python side
 * via ``gr.Blocks.load()`` so Gradio's own Svelte reactivity updates every
 * component correctly.
 *
 * Storage schema:
 *   key   = "acestep.ui.user_preferences"
 *   value = JSON  { _version: 1, audio_format: "flac", … }
 */
(() => {
    const STORAGE_KEY = "acestep.ui.user_preferences";
    const SCHEMA_VERSION = 1;
    const DEBOUNCE_MS = 500;

    /**
     * Map of preference key → { elemId, type }.
     *   elemId : the HTML elem_id set in Gradio
     *   type   : "dropdown" | "slider" | "checkbox" | "number"
     */
    const PREFS = {
        audio_format:        { elemId: "acestep-audio-format",        type: "dropdown" },
        mp3_bitrate:         { elemId: "acestep-mp3-bitrate",         type: "dropdown" },
        mp3_sample_rate:     { elemId: "acestep-mp3-sample-rate",     type: "dropdown" },
        score_scale:         { elemId: "acestep-score-scale",         type: "slider"   },
        enable_normalization:{ elemId: "acestep-enable-normalization", type: "checkbox" },
        normalization_db:    { elemId: "acestep-normalization-db",     type: "slider"   },
        fade_in_duration:    { elemId: "acestep-fade-in-duration",    type: "slider"   },
        fade_out_duration:   { elemId: "acestep-fade-out-duration",   type: "slider"   },
        latent_shift:        { elemId: "acestep-latent-shift",        type: "slider"   },
        latent_rescale:      { elemId: "acestep-latent-rescale",      type: "slider"   },
        lm_batch_chunk_size: { elemId: "acestep-lm-batch-chunk-size", type: "number"   },
    };

    let saveTimer = null;
    const wiredElements = new WeakSet();

    // ── Storage helpers ──────────────────────────────────────────────

    const saveAll = (prefs) => {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
        } catch (_e) {
            // Private browsing or quota exceeded – silently ignore.
        }
    };

    // ── DOM helpers ──────────────────────────────────────────────────

    const findInput = (elemId, type) => {
        const wrapper = document.getElementById(elemId);
        if (!wrapper) return null;

        if (type === "dropdown") {
            return wrapper.querySelector("input");
        }
        if (type === "slider") {
            return wrapper.querySelector("input[type='range']")
                || wrapper.querySelector("input[type='number']");
        }
        if (type === "checkbox") {
            return wrapper.querySelector("input[type='checkbox']");
        }
        if (type === "number") {
            return wrapper.querySelector("input[type='number']");
        }
        return null;
    };

    const readValue = (key) => {
        const spec = PREFS[key];
        if (!spec) return undefined;
        const el = findInput(spec.elemId, spec.type);
        if (!el) return undefined;

        if (spec.type === "checkbox") return el.checked;
        if (spec.type === "slider" || spec.type === "number") {
            const v = Number(el.value);
            return Number.isFinite(v) ? v : undefined;
        }
        return el.value || undefined;
    };

    // ── Save (debounced) ─────────────────────────────────────────────

    const scheduleSave = () => {
        if (saveTimer !== null) {
            clearTimeout(saveTimer);
        }
        saveTimer = setTimeout(() => {
            saveTimer = null;
            const prefs = { _version: SCHEMA_VERSION };
            for (const key of Object.keys(PREFS)) {
                const v = readValue(key);
                if (v !== undefined) {
                    prefs[key] = v;
                }
            }
            saveAll(prefs);
        }, DEBOUNCE_MS);
    };

    // ── Wire listeners (re-entrant – safe to call on re-renders) ─────

    const wireListeners = () => {
        for (const key of Object.keys(PREFS)) {
            const spec = PREFS[key];
            const el = findInput(spec.elemId, spec.type);
            if (!el || wiredElements.has(el)) continue;
            wiredElements.add(el);
            el.addEventListener("input", scheduleSave, { passive: true });
            el.addEventListener("change", scheduleSave, { passive: true });
        }
    };

    // ── MutationObserver – re-wire after Gradio re-renders ───────────

    const startObserver = () => {
        const target = document.getElementById("acestep-audio-format")
            || document.body;
        const root = target.closest(".gradio-container") || document.body;

        let rafPending = false;
        new MutationObserver(() => {
            if (rafPending) return;
            rafPending = true;
            requestAnimationFrame(() => {
                rafPending = false;
                wireListeners();
            });
        }).observe(root, { childList: true, subtree: true });
    };

    // ── Boot ─────────────────────────────────────────────────────────

    const BOOT_POLL_MS = 200;
    const BOOT_TIMEOUT_MS = 10000;

    const boot = () => {
        const started = Date.now();
        const poll = () => {
            const probe = document.getElementById(
                PREFS.audio_format.elemId
            );
            if (!probe) {
                if (Date.now() - started < BOOT_TIMEOUT_MS) {
                    setTimeout(poll, BOOT_POLL_MS);
                }
                return;
            }
            wireListeners();
            startObserver();
        };
        poll();
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
        boot();
    }
})();
