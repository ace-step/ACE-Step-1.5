# Roadmap for UI Fixes and Improvements

## 1. Fix Browser Refresh & Initialization Issues
**Problem:** Refreshing the browser resets the UI state (showing "not initialized") even if the backend model is already loaded. Clicking "Initialize" again reloads the model unnecessarily, potentially causing errors or delays.
**Solution:**
- [x] Modify `AceStepHandler.initialize_service` and `LLMHandler.initialize` to check if the requested configuration is already loaded. If so, skip loading and return success immediately.
- [x] Implement a `demo.load` event handler in `acestep/gradio_ui/events/__init__.py` to sync the client-side UI state (accordion visibility, button interactivity) with the server-side model state when the page loads.

## 2. Reorganize LoRA & Training UI
**Problem:** LoRA configuration is cluttering the main Generation tab, and Training is on a separate tab. The user wants "all training and lora stuff at the bottom on its own page".
**Solution:**
- [x] Create a new comprehensive "LoRA & Training" tab (or rename existing Training tab).
- [x] Move the "LoRA Adapter" loading/configuration section from the Generation tab to this new tab.
- [x] Ensure the Generation tab can still use the loaded LoRA (via shared handler state) or provide a minimal status indicator.
- [x] Structure the new tab to clearly separate "Load/Use LoRA" and "Train LoRA" (e.g., using sub-tabs or vertical layout).

## 3. Implement History/Library Tab
**Problem:** There is no persistent way to view past generations and reload their settings after the session ends.
**Solution:**
- [x] Create a new "📚 History" (or Library) tab.
- [x] Implement functionality to scan the `gradio_outputs` directory for generated audio files and their corresponding JSON metadata.
- [x] Create a UI to list/grid these files with basic info (filename, timestamp).
- [x] Add a "Load Settings" button for each history item that populates the Generation tab inputs with the parameters from the JSON file.

## 4. Fix Logic Breaks (e.g., Send to Src Audio)
**Problem:** Buttons like "Send to Src Audio" reportedly break.
**Solution:**
- [x] Audit `send_to_src_btn` event wiring. Verify input/output component matching and data types.
- [x] Ensure `send_audio_to_src_with_metadata` handles all edge cases (e.g., None audio, missing metadata) gracefully.
- [ ] Check for other potential logic breaks in event handlers, particularly those involving `gr.State` or complex dependency chains.

## 5. Other UI Cleanup
**Problem:** "The General UI is a mess".
**Solution:**
- [ ] Review the overall layout and spacing.
- [ ] Group related parameters more logically if needed.
- [ ] Improve labels and help text for clarity.
