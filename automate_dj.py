from playwright.sync_api import sync_playwright
import time
import sys

def run(playwright):
    # Launch Brave browser specifically with debugging port and sound enabled
    try:
        browser = playwright.chromium.launch(
            executable_path="/usr/bin/brave",
            headless=False,
            args=[
                "--autoplay-policy=no-user-gesture-required", # Allow autoplaying audio
                "--disable-infobars",
                "--remote-debugging-port=9222" # Allow debugging
            ]
        )
    except Exception as e:
        print(f"Error launching browser: {e}", flush=True)
        sys.exit(1)

    context = browser.new_context()
    page = context.new_page()
    
    print("Opening DJ frontend in Brave...", flush=True)
    page.goto("file:///home/me/ht/forks/ht-ACE-Step-1.5/ui/dj.html")
    
    print("Configuring parameters...", flush=True)
    # Fill Prompts
    page.fill("#prompt", "high energy drum and bass, fast breaks, deep sub bass, rolling rhythm, energetic, club banger")
    page.fill("#negativePrompt", "vocals, slow, ambient, low quality, noise")
    
    # Check Instrumental explicitly (just in case)
    is_instrumental = page.locator("#instrumental").is_checked()
    if not is_instrumental:
        page.check("#instrumental")
    
    # Ensure inference steps is at a safe limit (8 for turbo)
    page.fill("#infSteps", "8")
    page.evaluate("document.getElementById('infSteps').dispatchEvent(new Event('input'))")
    
    # Select LoRA
    print("Selecting LoRA adapter...", flush=True)
    page.select_option("#loraSelect", "loras/acestep15_drumnbass_lora")
    page.click("#loraLoad")
    
    # Wait for LoRA to load (the button text changes back to 'Load' and status updates)
    print("Waiting for LoRA to load...", flush=True)
    try:
        page.wait_for_function("document.getElementById('loraLoad').disabled === false", timeout=60000)
        time.sleep(2) # Give it an extra moment to settle
        print("LoRA loaded.", flush=True)
    except Exception as e:
        print(f"Warning: Timeout waiting for LoRA. Proceeding anyway. {e}", flush=True)
    
    # Click Play
    print("Starting DJ playback...", flush=True)
    page.click("#btnPlay")
    
    # Monitor log console to make sure it's actually doing something
    print("DJ is now running in Brave! Leave this window open to listen.", flush=True)
    
    try:
        # Keep the script alive for an hour
        # Print the last log message every 5 seconds to show it's working
        for _ in range(720): # 720 * 5s = 1 hour
            last_log = page.evaluate("() => { const logs = document.querySelectorAll('.log-console div'); return logs.length > 0 ? logs[logs.length-1].innerText : ''; }")
            np_seg = page.evaluate("() => document.getElementById('npSegNum').innerText")
            print(f"Status - Seg {np_seg}: {last_log}", flush=True)
            time.sleep(5)
    except KeyboardInterrupt:
        print("Stopping...", flush=True)
    
    browser.close()

with sync_playwright() as playwright:
    run(playwright)