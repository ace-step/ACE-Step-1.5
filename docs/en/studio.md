# Experimental Studio UI

ACE-Step includes an optional, experimental HTML-based Studio UI for users who want a more structured, DAW-like interface.

This UI:

- Is frontend-only
- Talks to the same REST API (`/release_task`, `/query_result`)
- Does not change model behavior

## How to use

1. Start the ACE-Step API server (e.g. `uv run acestep --enable-api --port 8001` or your usual API launch command).
2. Open `ui/studio.html` in a browser (double-click or `file:///path/to/ACE-Step-1.5/ui/studio.html`).
3. Set the API base URL if needed (default: `http://localhost:8001`).
4. Enter prompt and options, then click **Generate**. The UI will poll for results and display audio when ready.

## Scope

- **Optional:** The default way to use ACE-Step remains the Gradio Web UI.
- **No backend changes:** This UI uses the existing REST API only.
- **Experimental:** Layout and features may change based on community feedback.
