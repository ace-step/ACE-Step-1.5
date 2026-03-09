"""Command-line entrypoint for serving the AceFlow ASGI application locally."""

import argparse

import uvicorn

from .app import create_app


def main():
    """Parse CLI options, create the AceFlow app, and run the Uvicorn server.

    Args:
        None: Arguments are read from the process command line.

    Returns:
        None: This function blocks until the Uvicorn server stops.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7861)
    args = ap.parse_args()

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
