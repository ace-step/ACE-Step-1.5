"""Frontend audio-player preference helpers for the Gradio UI."""


def get_audio_player_preferences_head() -> str:
    """Return head script that persists and syncs HTML audio volume.

    The script keeps a shared preferred volume for Gradio audio players
    (native ``audio`` elements and waveform volume sliders), stores it in
    ``localStorage``, and reapplies it when components are re-rendered.
    """
    return """
<script>
(() => {
    const STORAGE_KEY = "acestep.ui.audio.volume";
    const GENERATE_BUTTON_ID = "acestep-generate-btn";
    const EPSILON = 0.001;
    const STARTUP_RESYNC_WINDOW_MS = 3000;
    const STARTUP_RESYNC_INTERVAL_MS = 120;
    const seenPlayers = new WeakSet();
    const seenVolumeSliders = new WeakSet();
    const sliderSyncSuppressedUntil = new WeakMap();
    const observedRoots = new WeakSet();
    const knownRoots = [];
    const readyForPersistence = new WeakMap();
    const wasReadyBeforeLoad = new WeakMap();
    let scanScheduled = false;
    let preferredVolume = null;
    let startupResyncTimer = null;

    const clampVolume = (value) => {
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) {
            return null;
        }
        if (parsed < 0) {
            return 0;
        }
        if (parsed > 1) {
            return 1;
        }
        return parsed;
    };

    const loadPreferredVolume = () => {
        try {
            return clampVolume(window.localStorage.getItem(STORAGE_KEY));
        } catch (_error) {
            return null;
        }
    };

    const storePreferredVolume = (value) => {
        const clamped = clampVolume(value);
        if (clamped === null) {
            return;
        }
        preferredVolume = clamped;
        try {
            window.localStorage.setItem(STORAGE_KEY, String(clamped));
        } catch (_error) {
            // Ignore storage failures (private mode / blocked storage).
        }
    };

    const isTrustedUserEvent = (event) => Boolean(event && event.isTrusted);

    const applyPreferredVolume = (player) => {
        if (!player || preferredVolume === null) {
            return;
        }
        if (Math.abs(player.volume - preferredVolume) <= EPSILON) {
            return;
        }
        player.volume = preferredVolume;
    };

    const forEachAudioPlayer = (callback) => {
        for (let i = 0; i < knownRoots.length; i += 1) {
            const root = knownRoots[i];
            if (!root || !root.querySelectorAll) {
                continue;
            }
            root.querySelectorAll("audio").forEach((player) => callback(player));
        }
    };

    const forEachVolumeSlider = (callback) => {
        for (let i = 0; i < knownRoots.length; i += 1) {
            const root = knownRoots[i];
            if (!root || !root.querySelectorAll) {
                continue;
            }
            root.querySelectorAll("input.volume-slider[type='range'], input#volume[type='range']").forEach(
                (slider) => callback(slider)
            );
        }
    };

    const applyPreferredVolumeToSlider = (slider) => {
        if (!slider || preferredVolume === null) {
            return;
        }
        const current = clampVolume(slider.value);
        if (current !== null && Math.abs(current - preferredVolume) <= EPSILON) {
            return;
        }
        sliderSyncSuppressedUntil.set(slider, Date.now() + 250);
        slider.value = String(preferredVolume);
        slider.dispatchEvent(new Event("input", { bubbles: true }));
    };

    const syncAllVolumeControlsToPreferred = (sourcePlayer = null, sourceSlider = null) => {
        if (preferredVolume === null) {
            return;
        }
        forEachAudioPlayer((player) => {
            if (!player) {
                return;
            }
            if (sourcePlayer && player !== sourcePlayer) {
                if (Math.abs(player.volume - preferredVolume) > EPSILON) {
                    player.volume = preferredVolume;
                }
                return;
            }
            applyPreferredVolume(player);
        });
        forEachVolumeSlider((slider) => {
            if (!slider || slider === sourceSlider) {
                return;
            }
            applyPreferredVolumeToSlider(slider);
        });
    };

    const stopAndRewindAllPlayers = () => {
        discoverRoots();
        forEachAudioPlayer((player) => {
            if (!player) {
                return;
            }
            try {
                player.pause();
            } catch (_error) {
                // Ignore pause failures from detached or blocked media elements.
            }
            if (player.currentTime > 0) {
                player.currentTime = 0;
            }
            applyPreferredVolume(player);
        });
    };

    const isGenerateButtonClick = (event) => {
        if (!event) {
            return false;
        }
        const selector = `#${GENERATE_BUTTON_ID}`;
        const target = event.target;
        if (target && typeof target.closest === "function" && target.closest(selector)) {
            return true;
        }
        if (typeof event.composedPath !== "function") {
            return false;
        }
        const path = event.composedPath();
        for (let i = 0; i < path.length; i += 1) {
            const node = path[i];
            if (node && node.id === GENERATE_BUTTON_ID) {
                return true;
            }
        }
        return false;
    };

    const handleDocumentClick = (event) => {
        if (!isGenerateButtonClick(event)) {
            return;
        }
        stopAndRewindAllPlayers();
    };

    const stopStartupResync = () => {
        if (startupResyncTimer === null) {
            return;
        }
        window.clearInterval(startupResyncTimer);
        startupResyncTimer = null;
    };

    const beginStartupResync = () => {
        stopStartupResync();
        if (preferredVolume === null) {
            return;
        }

        const startedAt = Date.now();
        startupResyncTimer = window.setInterval(() => {
            scanPlayers();
            syncAllVolumeControlsToPreferred();
            if (Date.now() - startedAt >= STARTUP_RESYNC_WINDOW_MS) {
                stopStartupResync();
            }
        }, STARTUP_RESYNC_INTERVAL_MS);
    };

    const observeRoot = (root) => {
        if (!root || observedRoots.has(root)) {
            return;
        }
        observedRoots.add(root);
        knownRoots.push(root);

        const observeTarget = root === document ? document.documentElement : root;
        if (!observeTarget) {
            return;
        }

        new MutationObserver(() => {
            scheduleScan();
        }).observe(observeTarget, { childList: true, subtree: true });
    };

    const scheduleScan = () => {
        if (scanScheduled) {
            return;
        }
        scanScheduled = true;
        requestAnimationFrame(() => {
            scanScheduled = false;
            scanPlayers();
        });
    };

    const discoverRoots = () => {
        const queue = [document];
        const visited = new WeakSet();

        while (queue.length > 0) {
            const root = queue.pop();
            if (!root || visited.has(root)) {
                continue;
            }
            visited.add(root);
            observeRoot(root);

            if (!root.querySelectorAll) {
                continue;
            }
            root.querySelectorAll("*").forEach((node) => {
                if (node && node.shadowRoot) {
                    queue.push(node.shadowRoot);
                }
            });
        }
    };

    const registerPlayer = (player) => {
        if (!player || seenPlayers.has(player)) {
            return;
        }
        seenPlayers.add(player);
        readyForPersistence.set(player, player.readyState > 0);
        wasReadyBeforeLoad.set(player, false);
        applyPreferredVolume(player);

        player.addEventListener("volumechange", (event) => {
            const next = clampVolume(player.volume);
            if (next === null) {
                return;
            }

            if (!isTrustedUserEvent(event)) {
                applyPreferredVolume(player);
                return;
            }

            if (preferredVolume !== null && Math.abs(next - preferredVolume) <= EPSILON) {
                return;
            }

            if (
                readyForPersistence.get(player) !== true
                && wasReadyBeforeLoad.get(player) !== true
            ) {
                // Ignore mount/load reset events before media metadata is ready.
                applyPreferredVolume(player);
                return;
            }

            storePreferredVolume(next);
            syncAllVolumeControlsToPreferred(player, null);
        }, { passive: true });

        const markReadyForPersistence = () => {
            readyForPersistence.set(player, true);
            wasReadyBeforeLoad.set(player, false);
            applyPreferredVolume(player);
            if (player.currentTime > 0) {
                player.currentTime = 0;
            }
        };

        player.addEventListener("loadedmetadata", () => {
            markReadyForPersistence();
        }, { passive: true });

        player.addEventListener("loadstart", () => {
            wasReadyBeforeLoad.set(player, readyForPersistence.get(player) === true);
            readyForPersistence.set(player, false);
            applyPreferredVolume(player);
            if (player.currentTime > 0) {
                player.currentTime = 0;
            }
        }, { passive: true });

        if (player.readyState > 0) {
            markReadyForPersistence();
        }
    };

    const registerVolumeSlider = (slider) => {
        if (!slider || seenVolumeSliders.has(slider)) {
            return;
        }
        seenVolumeSliders.add(slider);
        applyPreferredVolumeToSlider(slider);

        const onSliderInput = (event) => {
            const suppressedUntil = sliderSyncSuppressedUntil.get(slider) || 0;
            if (Date.now() <= suppressedUntil) {
                return;
            }

            if (!isTrustedUserEvent(event)) {
                applyPreferredVolumeToSlider(slider);
                return;
            }

            const next = clampVolume(slider.value);
            if (next === null) {
                return;
            }
            if (preferredVolume !== null && Math.abs(next - preferredVolume) <= EPSILON) {
                return;
            }
            storePreferredVolume(next);
            syncAllVolumeControlsToPreferred(null, slider);
        };

        slider.addEventListener("input", onSliderInput, { passive: true });
        slider.addEventListener("change", onSliderInput, { passive: true });
    };

    const scanPlayers = () => {
        discoverRoots();
        forEachAudioPlayer(registerPlayer);
        forEachVolumeSlider(registerVolumeSlider);
        syncAllVolumeControlsToPreferred();
    };

    const start = () => {
        preferredVolume = loadPreferredVolume();
        document.addEventListener("click", handleDocumentClick, true);
        scanPlayers();
        beginStartupResync();
        window.addEventListener("beforeunload", () => {
            stopStartupResync();
            document.removeEventListener("click", handleDocumentClick, true);
        }, { once: true });
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
        start();
    }
})();
</script>
""".strip()
