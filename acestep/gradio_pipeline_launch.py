"""Gradio demo launch helper (queue, auth, optional API routes)."""

from __future__ import annotations

import argparse
from typing import Any, Optional

from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler


def launch_gradio_demo(
    demo: Any,
    args: argparse.Namespace,
    *,
    output_dir: str,
    dit_handler: Optional[AceStepHandler],
    llm_handler: Optional[LLMHandler],
) -> None:
    """Queue and launch the Gradio demo, optionally attaching API routes."""
    print("Enabling queue for multi-user support...")
    demo.queue(
        max_size=20,
        status_update_rate="auto",
        default_concurrency_limit=1,
    )
    print(f"Launching server on {args.server_name}:{args.port}...")
    auth = None
    if args.auth_username and args.auth_password:
        auth = (args.auth_username, args.auth_password)
        print("Authentication enabled")

    allowed_paths = [output_dir]
    for path in args.allowed_path:
        if path and path not in allowed_paths:
            allowed_paths.append(path)

    launch_kwargs = {
        "server_name": args.server_name,
        "server_port": args.port,
        "share": args.share,
        "debug": args.debug,
        "show_error": True,
        "inbrowser": False,
        "auth": auth,
        "allowed_paths": allowed_paths,
    }
    if not args.enable_api:
        demo.launch(prevent_thread_lock=False, **launch_kwargs)
        return

    print("Enabling API endpoints...")
    from acestep.ui.gradio.api.api_routes import setup_api_routes

    demo.launch(prevent_thread_lock=True, **launch_kwargs)
    setup_api_routes(demo, dit_handler, llm_handler, api_key=args.api_key)
    if args.api_key:
        print("API authentication enabled")
    print(
        "API endpoints enabled: /health, /v1/models, /release_task, "
        "/query_result, /create_random_sample, /format_lyrics"
    )
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
