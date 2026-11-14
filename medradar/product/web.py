"""Development/production server for the MedRadar workbench.

    python -m medradar web --port 8787 --host 127.0.0.1
    python -m medradar.product.web --open

Serves the JSON API and the built React workbench from the same origin, so there is no CORS
configuration and no second process in normal use.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the MedRadar workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--data-dir", default=None, help="snapshot directory (default: medradar/product/snapshot)")
    parser.add_argument("--web-dir", default=None, help="built UI directory (default: web/dist)")
    parser.add_argument("--open", action="store_true", help="open the browser after start")
    parser.add_argument("--no-reload", action="store_true", help="disable the reload watcher")
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required: pip install 'fastapi' 'uvicorn'", file=sys.stderr)
        return 2

    from .api import create_app

    app = create_app(data_dir=args.data_dir, web_dir=args.web_dir)
    url = "http://" + args.host + ":" + str(args.port)
    print("MedRadar workbench: " + url)
    print("API docs: " + url + "/api/docs")
    if args.open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
