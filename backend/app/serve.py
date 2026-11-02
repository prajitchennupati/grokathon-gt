"""Entry point: python -m app.serve [--demo] [--offline] [--port 8000]"""
from __future__ import annotations

import argparse
import os


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the Clearance backend")
    ap.add_argument("--demo", action="store_true", help="demo scenario, fallback mode for all Bots, auto-pause, demo script")
    ap.add_argument("--offline", action="store_true", help="never call the xAI API; use llm/cache then canned fallbacks")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()
    # settings are read at import time, so set the environment before importing the app
    if args.demo:
        os.environ["DEMO_MODE"] = "1"
        os.environ["SCENARIO"] = "atl_arrivals_demo.json"
    if args.offline:
        os.environ["CLEARANCE_OFFLINE"] = "1"

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
